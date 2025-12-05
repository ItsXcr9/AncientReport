"""
Security Scanning API - Phase 5
Provides endpoints for security vulnerability scanning, file integrity monitoring, 
runtime security checks, and SCHEDULED daily scans at 2 AM.
Uses Trivy for real vulnerability scanning and NVD API for CVE lookups.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import subprocess
import json
import logging
import os
import socket
import asyncio
import httpx
from collections import defaultdict

# APScheduler for daily scans
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/security/scanning")

# ClickHouse configuration
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "AncientReport")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

# Global scheduler instance
scheduler = None
_scans_initialized = False

# Scan execution history
scan_history: List[Dict[str, Any]] = []
last_scheduled_scan: Optional[str] = None
last_scheduled_scan_status: Optional[str] = None  # success, failed, running

# CVE cache to reduce API calls
cve_cache: Dict[str, Dict[str, Any]] = {}
CVE_CACHE_TTL = timedelta(hours=24)

class Vulnerability(BaseModel):
    id: str
    cve_id: Optional[str]
    severity: str  # critical, high, medium, low
    package: str
    version: str
    fixed_version: Optional[str]
    description: str
    link: Optional[str]

class SecurityScanResult(BaseModel):
    id: str
    target: str  # container_id or host
    scan_type: str  # vulnerability, config, secret, malware
    status: str  # pending, running, completed, failed
    started_at: str
    completed_at: Optional[str]
    vulnerabilities: List[Vulnerability]
    score: int  # 0-100 security score
    error: Optional[str] = None
    hostname: str = ""  # Server where the container runs

class FileIntegrityEvent(BaseModel):
    id: str
    path: str
    event_type: str  # modified, created, deleted, attribute_changed
    severity: str
    timestamp: str
    user: Optional[str]
    process: Optional[str]
    diff: Optional[str]

class RuntimeSecurityEvent(BaseModel):
    id: str
    rule_name: str
    severity: str
    container_id: Optional[str]
    process_name: Optional[str]
    pid: Optional[int]
    timestamp: str
    details: str

class ScheduleInfo(BaseModel):
    enabled: bool
    next_run: Optional[str]
    last_run: Optional[str]
    last_run_status: Optional[str]
    cron_expression: str

class HealthStatus(BaseModel):
    status: str  # healthy, degraded, unhealthy
    scheduler_enabled: bool
    scheduler_next_run: Optional[str]
    trivy_available: bool
    nvd_api_available: bool
    last_scan_status: Optional[str]
    last_scan_time: Optional[str]
    components: Dict[str, Any]

# Data stores (loaded from ClickHouse on startup)
scan_results: List[SecurityScanResult] = []
file_events: List[FileIntegrityEvent] = []
runtime_events: List[RuntimeSecurityEvent] = []


# ClickHouse helper functions
async def clickhouse_query(query: str) -> Optional[str]:
    """Execute a ClickHouse query and return result."""
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/"
    params = {"database": CLICKHOUSE_DB, "query": query}
    if CLICKHOUSE_USER:
        params["user"] = CLICKHOUSE_USER
    if CLICKHOUSE_PASSWORD:
        params["password"] = CLICKHOUSE_PASSWORD
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"ClickHouse query failed: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.error(f"ClickHouse connection error: {e}")
        return None


async def clickhouse_insert(query: str) -> bool:
    """Execute a ClickHouse insert query."""
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/"
    params = {"database": CLICKHOUSE_DB, "query": query}
    if CLICKHOUSE_USER:
        params["user"] = CLICKHOUSE_USER
    if CLICKHOUSE_PASSWORD:
        params["password"] = CLICKHOUSE_PASSWORD
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, params=params)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"ClickHouse insert failed: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"ClickHouse connection error: {e}")
        return False


async def start_nats_subscriber():
    """Subscribe to NATS for remote container scan results from agents."""
    nats_url = os.getenv("NATS_URL", "")
    if not nats_url:
        logger.info("NATS URL not configured, remote container scan subscription disabled")
        return
    
    try:
        from nats.aio.client import Client as NATS
        
        nc = NATS()
        await nc.connect(servers=[nats_url])
        logger.info(f"Connected to NATS at {nats_url} for container scan subscription")
        
        async def handle_container_scan(msg):
            """Process incoming container scan from remote agent."""
            try:
                data = json.loads(msg.data.decode())
                logger.info(f"Received container scan from {data.get('hostname', 'unknown')}: {data.get('target', 'unknown')}")
                
                # Convert to SecurityScanResult
                vulns = []
                for v in data.get('vulnerabilities', []):
                    vulns.append(Vulnerability(
                        id=v.get('id', ''),
                        cve_id=v.get('cve_id'),
                        severity=v.get('severity', 'low'),
                        package=v.get('package', ''),
                        version=v.get('version', ''),
                        fixed_version=v.get('fixed_version'),
                        description=v.get('description', '')[:500] if v.get('description') else '',
                        link=v.get('link')
                    ))
                
                scan_result = SecurityScanResult(
                    id=data.get('id', f"remote-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"),
                    target=data.get('target', ''),
                    scan_type=data.get('scan_type', 'vulnerability'),
                    status=data.get('status', 'completed'),
                    started_at=data.get('started_at', datetime.utcnow().isoformat()),
                    completed_at=data.get('completed_at'),
                    vulnerabilities=vulns,
                    score=data.get('score', 100),
                    error=data.get('error'),
                    hostname=data.get('hostname', '')
                )
                
                # Add to in-memory list
                scan_results.insert(0, scan_result)
                scan_results[:] = scan_results[:100]  # Keep last 100
                
                # Persist to ClickHouse
                await save_scan_to_clickhouse(scan_result)
                logger.info(f"✓ Saved remote scan for {scan_result.target} from {scan_result.hostname}")
                
            except Exception as e:
                logger.error(f"Error processing remote container scan: {e}", exc_info=True)
        
        # Subscribe to container scan topic
        await nc.subscribe("security.container_scan", cb=handle_container_scan)
        logger.info("✓ Subscribed to security.container_scan for remote agent scans")
        
        # Keep connection alive
        while True:
            await asyncio.sleep(60)
            
    except Exception as e:
        logger.error(f"NATS subscriber error: {e}", exc_info=True)


async def load_scans_from_clickhouse():
    """Load recent security scans from ClickHouse into memory."""
    global scan_results, _scans_initialized
    
    query = """
    SELECT id, target, scan_type, status, started_at, completed_at, vulnerabilities, score, error, hostname
    FROM security_scan_results
    ORDER BY started_at DESC
    LIMIT 50
    FORMAT JSONEachRow
    """
    
    logger.info(f"Loading security scans from ClickHouse ({CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB})...")
    result = await clickhouse_query(query)
    
    if result:
        logger.info(f"ClickHouse query returned {len(result)} bytes of data")
        loaded = []
        parse_errors = 0
        
        for line in result.strip().split('\n'):
            if line:
                try:
                    # Sanitize the JSON line to handle invalid escape sequences
                    # Replace invalid \' with ' and fix other common issues
                    sanitized_line = line.replace("\\'", "'").replace("\\n", " ").replace("\\r", " ")
                    
                    row = json.loads(sanitized_line)
                    vulns_data = row.get('vulnerabilities', '[]')
                    
                    # Parse vulnerabilities with error handling
                    if isinstance(vulns_data, str):
                        try:
                            # Sanitize vulnerability JSON too
                            vulns_sanitized = vulns_data.replace("\\'", "'").replace("\\n", " ")
                            vulns_data = json.loads(vulns_sanitized)
                        except json.JSONDecodeError:
                            vulns_data = []
                            logger.warning(f"Could not parse vulnerabilities for scan {row.get('id', 'unknown')}")
                    
                    vulnerabilities = []
                    if isinstance(vulns_data, list):
                        for v in vulns_data:
                            if isinstance(v, dict):
                                vulnerabilities.append(Vulnerability(
                                    id=str(v.get('id', '')),
                                    cve_id=v.get('cve_id'),
                                    severity=v.get('severity', 'low'),
                                    package=str(v.get('package', '')),
                                    version=str(v.get('version', '')),
                                    fixed_version=v.get('fixed_version'),
                                    description=str(v.get('description', ''))[:500],
                                    link=v.get('link')
                                ))
                    
                    scan = SecurityScanResult(
                        id=row['id'],
                        target=row['target'],
                        scan_type=row['scan_type'],
                        status=row['status'],
                        started_at=row['started_at'],
                        completed_at=row.get('completed_at'),
                        vulnerabilities=vulnerabilities,
                        score=row.get('score', 100),
                        error=row.get('error'),
                        hostname=row.get('hostname', '')
                    )
                    loaded.append(scan)
                except Exception as e:
                    parse_errors += 1
                    logger.error(f"Failed to parse scan row: {e}")
        
        scan_results = loaded
        if parse_errors > 0:
            logger.warning(f"⚠ {parse_errors} scan rows failed to parse (corrupted data)")
        logger.info(f"✓ Loaded {len(scan_results)} security scans from ClickHouse")
    else:
        logger.warning("No security scans loaded from ClickHouse (query returned empty result or table doesn't exist)")
    
    _scans_initialized = True


async def save_scan_to_clickhouse(scan: SecurityScanResult) -> bool:
    """Save a security scan result to ClickHouse."""
    
    def clean_string(s: str) -> str:
        """Clean a string by removing control characters."""
        if not s:
            return ""
        # Remove control characters only - let json.dumps handle escaping
        s = s.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        return s[:500]  # Limit length
    
    def sql_escape(s: str) -> str:
        """Escape a string for SQL insertion (after JSON serialization)."""
        return s.replace("'", "''")  # Double single quotes for SQL
    
    # Build vulnerabilities list with cleaned strings
    vulns_list = []
    for v in scan.vulnerabilities:
        vulns_list.append({
            "id": clean_string(v.id) if v.id else "",
            "cve_id": clean_string(v.cve_id) if v.cve_id else "",
            "severity": v.severity if v.severity else "low",
            "package": clean_string(v.package) if v.package else "",
            "version": clean_string(v.version) if v.version else "",
            "fixed_version": clean_string(v.fixed_version) if v.fixed_version else "",
            "description": clean_string(v.description) if v.description else "",
            "link": clean_string(v.link) if v.link else ""
        })
    
    # First serialize to JSON (handles escaping), then escape for SQL
    vulns_json = sql_escape(json.dumps(vulns_list))
    
    completed_at = f"'{scan.completed_at}'" if scan.completed_at else "NULL"
    error_str = sql_escape(clean_string(scan.error)) if scan.error else ""
    hostname_str = sql_escape(clean_string(scan.hostname)) if scan.hostname else ""
    
    query = f"""
    INSERT INTO security_scan_results (id, target, scan_type, status, started_at, completed_at, vulnerabilities, score, error, hostname)
    VALUES (
        '{sql_escape(clean_string(scan.id))}',
        '{sql_escape(clean_string(scan.target))}',
        '{scan.scan_type}',
        '{scan.status}',
        '{scan.started_at}',
        {completed_at},
        '{vulns_json}',
        {scan.score},
        '{error_str}',
        '{hostname_str}'
    )
    """
    
    return await clickhouse_insert(query)


async def ensure_scans_initialized():
    """Ensure scans are loaded from ClickHouse."""
    global _scans_initialized
    if not _scans_initialized:
        await load_scans_from_clickhouse()

def run_docker_command(args: List[str], timeout: int = 30) -> tuple[bool, str]:
    """Run a Docker command and return success status and output."""
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)

def run_trivy_command(args: List[str], timeout: int = 300) -> tuple[bool, str, Optional[Dict]]:
    """Run Trivy command and return success status, output, and parsed JSON if available."""
    try:
        result = subprocess.run(
            ["trivy"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip() or result.stderr.strip()
        success = result.returncode == 0
        
        # Try to parse JSON output
        json_data = None
        if success and output:
            try:
                json_data = json.loads(output)
            except json.JSONDecodeError:
                pass
        
        return success, output, json_data
    except subprocess.TimeoutExpired:
        return False, "Trivy command timed out", None
    except FileNotFoundError:
        return False, "Trivy not found. Please ensure Trivy is installed.", None
    except Exception as e:
        return False, str(e), None

def check_trivy_available() -> bool:
    """Check if Trivy is available."""
    success, _, _ = run_trivy_command(["--version"], timeout=10)
    return success

async def fetch_cve_from_nvd(cve_id: str) -> Optional[Dict[str, Any]]:
    """Fetch CVE details from NVD API."""
    # Check cache first
    if cve_id in cve_cache:
        cached = cve_cache[cve_id]
        if datetime.utcnow() - cached.get("cached_at", datetime.utcnow()) < CVE_CACHE_TTL:
            return cached.get("data")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # NVD API v2.0 endpoint
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0"
            params = {"cveId": cve_id}
            
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                
                # Extract CVE details
                if data.get("vulnerabilities") and len(data["vulnerabilities"]) > 0:
                    cve_data = data["vulnerabilities"][0]["cve"]
                    
                    # Cache the result
                    cve_cache[cve_id] = {
                        "data": cve_data,
                        "cached_at": datetime.utcnow()
                    }
                    
                    return cve_data
            elif response.status_code == 403:
                logger.warning("NVD API rate limit reached. Using cached data if available.")
                return None
    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching CVE {cve_id} from NVD API")
        return None
    except Exception as e:
        logger.warning(f"Error fetching CVE {cve_id} from NVD API: {e}")
        return None
    
    return None

async def enrich_vulnerability_with_nvd(vuln_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich vulnerability data with NVD API information."""
    cve_id = vuln_data.get("VulnerabilityID") or vuln_data.get("cve_id")
    if not cve_id:
        return vuln_data
    
    nvd_data = await fetch_cve_from_nvd(cve_id)
    if nvd_data:
        descriptions = nvd_data.get("descriptions", [])
        if descriptions:
            # Prefer English description
            for desc in descriptions:
                if desc.get("lang") == "en":
                    vuln_data["description"] = desc.get("value", vuln_data.get("Description", ""))
                    break
        
        # Get CVSS score if available
        metrics = nvd_data.get("metrics", {})
        if "cvssMetricV31" in metrics and len(metrics["cvssMetricV31"]) > 0:
            cvss = metrics["cvssMetricV31"][0].get("cvssData", {})
            vuln_data["cvss_score"] = cvss.get("baseScore")
        
        # Add NVD link
        vuln_data["link"] = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
    
    return vuln_data

def get_running_containers() -> List[str]:
    """Get list of running container names."""
    success, output = run_docker_command(["ps", "--format", "{{.Names}}"])
    if success and output:
        return [c.strip() for c in output.strip().split("\n") if c.strip()]
    return []

async def scan_container_with_trivy(container_name: str) -> SecurityScanResult:
    """Perform a real security scan on a container using Trivy."""
    vulnerabilities = []
    score = 100
    error = None
    
    scan_id = f"scan-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{container_name[:20]}"
    started_at = datetime.utcnow().isoformat()
    
    # Get container image
    success, image_info = run_docker_command([
        "inspect", "--format", "{{.Config.Image}}", container_name
    ])
    
    if not success:
        error = f"Failed to get container image: {image_info}"
        logger.error(error)
        return SecurityScanResult(
            id=scan_id,
            target=container_name,
            scan_type="vulnerability",
            status="failed",
            started_at=started_at,
            completed_at=datetime.utcnow().isoformat(),
            vulnerabilities=[],
            score=0,
            error=error,
            hostname=os.getenv('SERVER_HOSTNAME', socket.gethostname())
        )
    
    image_name = image_info.strip()
    logger.info(f"Scanning container {container_name} (image: {image_name}) with Trivy...")
    
    # Run Trivy scan on container
    # Use JSON format for structured output
    success, output, json_data = run_trivy_command([
        "container",
        "--format", "json",
        "--no-progress",
        "--quiet",
        container_name
    ], timeout=600)
    
    if not success:
        error = f"Trivy scan failed: {output}"
        logger.error(error)
        # Fallback: try scanning the image directly
        logger.info(f"Attempting to scan image {image_name} directly...")
        success, output, json_data = run_trivy_command([
            "image",
            "--format", "json",
            "--no-progress",
            "--quiet",
            image_name
        ], timeout=600)
        
        if not success:
            return SecurityScanResult(
                id=scan_id,
                target=container_name,
                scan_type="vulnerability",
                status="failed",
                started_at=started_at,
                completed_at=datetime.utcnow().isoformat(),
                vulnerabilities=[],
                score=0,
                error=error
            )
    
    # Parse Trivy JSON output
    if json_data and "Results" in json_data:
        for result in json_data.get("Results", []):
            for vuln in result.get("Vulnerabilities", []):
                # Map Trivy severity to our format
                trivy_severity = vuln.get("Severity", "UNKNOWN").lower()
                severity_map = {
                    "critical": "critical",
                    "high": "high",
                    "medium": "medium",
                    "low": "low",
                    "unknown": "low"
                }
                severity = severity_map.get(trivy_severity, "low")
                
                # Enrich with NVD data
                enriched_vuln = await enrich_vulnerability_with_nvd(vuln)
                
                vuln_obj = Vulnerability(
                    id=f"vuln-{vuln.get('VulnerabilityID', 'unknown')}-{len(vulnerabilities)}",
                    cve_id=vuln.get("VulnerabilityID"),
                    severity=severity,
                    package=vuln.get("PkgName", "unknown"),
                    version=vuln.get("InstalledVersion", "unknown"),
                    fixed_version=vuln.get("FixedVersion"),
                    description=enriched_vuln.get("description", vuln.get("Description", "No description available")),
                    link=enriched_vuln.get("link", f"https://nvd.nist.gov/vuln/detail/{vuln.get('VulnerabilityID', '')}" if vuln.get("VulnerabilityID") else "")
                )
                vulnerabilities.append(vuln_obj)
                
                # Calculate score penalty
                if severity == "critical":
                    score -= 25
                elif severity == "high":
                    score -= 15
                elif severity == "medium":
                    score -= 5
                elif severity == "low":
                    score -= 2
    
    score = max(0, score)
    
    logger.info(f"Trivy scan complete for {container_name}: {len(vulnerabilities)} vulnerabilities found, score: {score}")
    
    # Get local hostname for multi-server support (use SERVER_HOSTNAME env var from docker-compose)
    local_hostname = os.getenv('SERVER_HOSTNAME', socket.gethostname())
    
    result = SecurityScanResult(
        id=scan_id,
        target=container_name,
        scan_type="vulnerability",
        status="completed",
        started_at=started_at,
        completed_at=datetime.utcnow().isoformat(),
        vulnerabilities=vulnerabilities,
        score=score,
        error=error,
        hostname=local_hostname
    )
    
    return result

async def run_scheduled_scan():
    """Run scheduled daily vulnerability scan on all containers."""
    global last_scheduled_scan, last_scheduled_scan_status
    
    logger.info("=" * 60)
    logger.info("Starting scheduled security scan at 2:00 AM...")
    logger.info("=" * 60)
    
    last_scheduled_scan = datetime.utcnow().isoformat()
    last_scheduled_scan_status = "running"
    
    try:
        containers = get_running_containers()
        scanned_count = 0
        failed_count = 0
        
        if containers:
            logger.info(f"Found {len(containers)} running containers to scan")
            for container in containers:
                try:
                    logger.info(f"Scanning container: {container}")
                    result = await scan_container_with_trivy(container)
                    scan_results.insert(0, result)
                    await save_scan_to_clickhouse(result)  # Persist to ClickHouse
                    scanned_count += 1
                    
                    if result.status == "failed":
                        failed_count += 1
                        logger.error(f"Scan failed for {container}: {result.error}")
                    else:
                        logger.info(f"Scan completed for {container}: {len(result.vulnerabilities)} vulnerabilities, score: {result.score}")
                except Exception as e:
                    logger.error(f"Error scanning container {container}: {e}", exc_info=True)
                    failed_count += 1
            
            # Keep only last 50 scan results
            scan_results[:] = scan_results[:50]
            
            logger.info("=" * 60)
            logger.info(f"Scheduled scan complete. Scanned {scanned_count} containers, {failed_count} failed.")
            logger.info("=" * 60)
            
            last_scheduled_scan_status = "success" if failed_count == 0 else "degraded"
        else:
            # Fallback to known containers
            logger.warning("No running containers found, using fallback list")
            for name in ["AncientReport-ui", "AncientReport-analysis", "AncientReport-agent"]:
                try:
                    logger.info(f"Scanning fallback container: {name}")
                    result = await scan_container_with_trivy(name)
                    scan_results.insert(0, result)
                    await save_scan_to_clickhouse(result)  # Persist to ClickHouse
                    scanned_count += 1
                except Exception as e:
                    logger.error(f"Error scanning container {name}: {e}", exc_info=True)
                    failed_count += 1
            
            scan_results[:] = scan_results[:50]
            logger.info(f"Scheduled scan complete (fallback mode). Scanned {scanned_count} containers, {failed_count} failed.")
            last_scheduled_scan_status = "success" if failed_count == 0 else "degraded"
        
        # Record in history
        scan_history.append({
            "timestamp": last_scheduled_scan,
            "status": last_scheduled_scan_status,
            "containers_scanned": scanned_count,
            "containers_failed": failed_count,
            "total_vulnerabilities": sum(len(r.vulnerabilities) for r in scan_results[:scanned_count])
        })
        
        # Keep only last 30 history entries
        scan_history[:] = scan_history[-30:]
        
    except Exception as e:
        logger.error(f"Fatal error in scheduled scan: {e}", exc_info=True)
        last_scheduled_scan_status = "failed"

def init_scheduler():
    """Initialize the APScheduler for daily 2 AM scans."""
    global scheduler
    
    if not SCHEDULER_AVAILABLE:
        logger.warning("APScheduler not available, daily scans disabled")
        return
    
    if scheduler is not None:
        return
    
    scheduler = AsyncIOScheduler()
    
    # Schedule daily scan at 2:00 AM
    scheduler.add_job(
        run_scheduled_scan,
        CronTrigger(hour=2, minute=0),
        id="daily_security_scan",
        name="Daily Security Vulnerability Scan",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✓ Security scan scheduler started - Daily scan at 2:00 AM")

# Initialize scheduler on module load
init_scheduler()

@router.get("/health", response_model=HealthStatus)
async def get_health_status():
    """Get comprehensive health status of security scanning system."""
    components = {}
    overall_status = "healthy"
    
    # Check scheduler
    scheduler_enabled = scheduler is not None and SCHEDULER_AVAILABLE
    scheduler_next_run = None
    if scheduler and SCHEDULER_AVAILABLE:
        job = scheduler.get_job("daily_security_scan")
        if job and job.next_run_time:
            scheduler_next_run = job.next_run_time.isoformat()
        components["scheduler"] = {
            "status": "healthy",
            "next_run": scheduler_next_run
        }
    else:
        components["scheduler"] = {"status": "unhealthy", "reason": "Scheduler not available"}
        overall_status = "degraded"
    
    # Check Trivy
    trivy_available = check_trivy_available()
    components["trivy"] = {
        "status": "healthy" if trivy_available else "unhealthy",
        "available": trivy_available
    }
    if not trivy_available:
        overall_status = "unhealthy"
    
    # Check NVD API
    nvd_api_available = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://services.nvd.nist.gov/rest/json/cves/2.0", params={"cveId": "CVE-2023-38545"})
            # 200 = success, 403/429 = rate limit but API is working
            nvd_api_available = response.status_code in [200, 403, 429]
    except Exception as e:
        logger.warning(f"NVD API health check failed: {e}")
    
    components["nvd_api"] = {
        "status": "healthy" if nvd_api_available else "degraded",
        "available": nvd_api_available
    }
    if not nvd_api_available:
        if overall_status == "healthy":
            overall_status = "degraded"
    
    # Check last scan
    components["last_scan"] = {
        "status": last_scheduled_scan_status or "unknown",
        "timestamp": last_scheduled_scan
    }
    
    return HealthStatus(
        status=overall_status,
        scheduler_enabled=scheduler_enabled,
        scheduler_next_run=scheduler_next_run,
        trivy_available=trivy_available,
        nvd_api_available=nvd_api_available,
        last_scan_status=last_scheduled_scan_status,
        last_scan_time=last_scheduled_scan,
        components=components
    )

@router.post("/trigger")
async def trigger_scan(target: str, scan_type: str = "vulnerability"):
    """Trigger a new security scan on a specific target."""
    global last_scheduled_scan, last_scheduled_scan_status
    
    last_scheduled_scan = datetime.utcnow().isoformat()
    last_scheduled_scan_status = "running"
    
    result = await scan_container_with_trivy(target)
    scan_results.insert(0, result)
    await save_scan_to_clickhouse(result)  # Persist to ClickHouse
    scan_results[:] = scan_results[:50]
    
    last_scheduled_scan_status = "success" if result.status == "completed" else "failed"
    return result

@router.post("/trigger-all")
async def trigger_full_scan():
    """Trigger a full scan on all running containers."""
    global last_scheduled_scan, last_scheduled_scan_status
    
    last_scheduled_scan = datetime.utcnow().isoformat()
    last_scheduled_scan_status = "running"
    
    containers = get_running_containers()
    results = []
    failed = 0
    
    if containers:
        for container in containers:
            result = await scan_container_with_trivy(container)
            scan_results.insert(0, result)
            await save_scan_to_clickhouse(result)  # Persist to ClickHouse
            results.append(result)
            if result.status == "failed":
                failed += 1
    else:
        for name in ["AncientReport-ui", "AncientReport-analysis"]:
            result = await scan_container_with_trivy(name)
            scan_results.insert(0, result)
            await save_scan_to_clickhouse(result)  # Persist to ClickHouse
            results.append(result)
            if result.status == "failed":
                failed += 1
    
    scan_results[:] = scan_results[:50]
    
    last_scheduled_scan_status = "success" if failed == 0 else "degraded"
    
    return {
        "message": f"Scanned {len(results)} containers",
        "results": results
    }

@router.get("/results")
async def get_scan_results(limit: int = 50, hostname: Optional[str] = None) -> List[SecurityScanResult]:
    """Get recent security scan results. Optionally filter by hostname."""
    await ensure_scans_initialized()  # Load from ClickHouse if not already loaded
    logger.info(f"Security scan results request: {len(scan_results)} scans in memory, limit={limit}, hostname={hostname}")
    results = scan_results
    
    if hostname:
        # Filter by the scan's hostname field (server where container runs)
        filtered = [s for s in results if s.hostname.lower() == hostname.lower()]
        
        if filtered:
            results = filtered
            logger.info(f"Hostname filter '{hostname}' matched {len(results)} scans")
        else:
            # No scans from this hostname - might be a server with no containers
            logger.info(f"Hostname filter '{hostname}' matched 0 scans (no containers on this server)")
            results = []
    
    logger.info(f"Returning {len(results[:limit])} scan results")
    return results[:limit]

@router.get("/schedule")
async def get_schedule_info() -> ScheduleInfo:
    """Get information about scheduled scans."""
    next_run = None
    
    if scheduler and SCHEDULER_AVAILABLE:
        job = scheduler.get_job("daily_security_scan")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    
    return ScheduleInfo(
        enabled=scheduler is not None and SCHEDULER_AVAILABLE,
        next_run=next_run,
        last_run=last_scheduled_scan,
        last_run_status=last_scheduled_scan_status,
        cron_expression="0 2 * * *"
    )

@router.post("/schedule/run-now")
async def run_scheduled_scan_now():
    """Manually trigger the scheduled scan."""
    await run_scheduled_scan()
    return {"message": "Scheduled scan triggered", "last_run": last_scheduled_scan, "status": last_scheduled_scan_status}

@router.get("/history")
async def get_scan_history(limit: int = 30):
    """Get scan execution history."""
    return {"history": scan_history[-limit:]}

@router.get("/file-integrity")
async def get_file_integrity_events(limit: int = 20) -> List[FileIntegrityEvent]:
    """Get file integrity monitoring events."""
    return file_events[:limit]

@router.get("/runtime")
async def get_runtime_events(limit: int = 20) -> List[RuntimeSecurityEvent]:
    """Get runtime security events (eBPF detected)."""
    return runtime_events[:limit]

@router.get("/stats")
async def get_security_stats(hostname: Optional[str] = None):
    """Get aggregate security statistics. Optionally filter by hostname."""
    await ensure_scans_initialized()  # Load from ClickHouse if not already loaded
    results = scan_results
    if hostname:
        # Filter by the scan's hostname field
        filtered = [s for s in results if s.hostname.lower() == hostname.lower()]
        if filtered:
            results = filtered
        else:
            results = []  # No scans from this server
    
    critical_count = sum(
        1 for s in results 
        for v in s.vulnerabilities 
        if v.severity == "critical"
    )
    high_count = sum(
        1 for s in results 
        for v in s.vulnerabilities 
        if v.severity == "high"
    )
    
    return {
        "vulnerabilities_total": sum(len(s.vulnerabilities) for s in results),
        "critical_vulns": critical_count,
        "high_vulns": high_count,
        "scans_last_24h": len([s for s in results if s.started_at and (datetime.utcnow() - datetime.fromisoformat(s.started_at.replace('Z', '+00:00') if s.started_at.endswith('Z') else s.started_at)).total_seconds() < 86400]),
        "runtime_incidents": len(runtime_events),
        "fim_events": len(file_events),
        "average_score": int(sum(s.score for s in results) / max(len(results), 1)) if results else 100,
        "scheduled_scan_enabled": scheduler is not None,
        "last_scheduled_scan": last_scheduled_scan,
        "last_scheduled_scan_status": last_scheduled_scan_status
    }
