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

# Global scheduler instance
scheduler = None

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

# Data stores
scan_results: List[SecurityScanResult] = []
file_events: List[FileIntegrityEvent] = []
runtime_events: List[RuntimeSecurityEvent] = []

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
            error=error
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
    
    result = SecurityScanResult(
        id=scan_id,
        target=container_name,
        scan_type="vulnerability",
        status="completed",
        started_at=started_at,
        completed_at=datetime.utcnow().isoformat(),
        vulnerabilities=vulnerabilities,
        score=score,
        error=error
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
                    result = await scan_container_with_trivy(name)
                    scan_results.insert(0, result)
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
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("https://services.nvd.nist.gov/rest/json/cves/2.0", params={"cveId": "CVE-2023-38545"})
            nvd_api_available = response.status_code in [200, 403]  # 403 means rate limit but API is working
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
            results.append(result)
            if result.status == "failed":
                failed += 1
    else:
        for name in ["AncientReport-ui", "AncientReport-analysis"]:
            result = await scan_container_with_trivy(name)
            scan_results.insert(0, result)
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
async def get_scan_results(limit: int = 10) -> List[SecurityScanResult]:
    """Get recent security scan results."""
    return scan_results[:limit]

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
async def get_security_stats():
    """Get aggregate security statistics."""
    critical_count = sum(
        1 for s in scan_results 
        for v in s.vulnerabilities 
        if v.severity == "critical"
    )
    high_count = sum(
        1 for s in scan_results 
        for v in s.vulnerabilities 
        if v.severity == "high"
    )
    
    return {
        "vulnerabilities_total": sum(len(s.vulnerabilities) for s in scan_results),
        "critical_vulns": critical_count,
        "high_vulns": high_count,
        "scans_last_24h": len([s for s in scan_results if s.started_at and (datetime.utcnow() - datetime.fromisoformat(s.started_at.replace('Z', '+00:00') if s.started_at.endswith('Z') else s.started_at)).total_seconds() < 86400]),
        "runtime_incidents": len(runtime_events),
        "fim_events": len(file_events),
        "average_score": int(sum(s.score for s in scan_results) / max(len(scan_results), 1)) if scan_results else 100,
        "scheduled_scan_enabled": scheduler is not None,
        "last_scheduled_scan": last_scheduled_scan,
        "last_scheduled_scan_status": last_scheduled_scan_status
    }
