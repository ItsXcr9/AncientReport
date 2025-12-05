"""
Security Scanning API - Phase 5
Provides endpoints for security vulnerability scanning, file integrity monitoring, and runtime security checks.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
import asyncio
import random

router = APIRouter(prefix="/api/v3/security/scanning")

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

# Mock data store
scan_results: List[SecurityScanResult] = []
file_events: List[FileIntegrityEvent] = []
runtime_events: List[RuntimeSecurityEvent] = []

def generate_mock_scan(target: str) -> SecurityScanResult:
    """Generate a mock security scan result."""
    vulns = []
    if random.random() > 0.5:
        vulns.append(Vulnerability(
            id=f"vuln-{random.randint(1000, 9999)}",
            cve_id="CVE-2023-44487",
            severity="high",
            package="nginx",
            version="1.24.0",
            fixed_version="1.25.3",
            description="HTTP/2 Rapid Reset vulnerability",
            link="https://nvd.nist.gov/vuln/detail/CVE-2023-44487"
        ))
    
    return SecurityScanResult(
        id=f"scan-{random.randint(10000, 99999)}",
        target=target,
        scan_type="vulnerability",
        status="completed",
        started_at=datetime.utcnow().isoformat(),
        completed_at=datetime.utcnow().isoformat(),
        vulnerabilities=vulns,
        score=random.randint(60, 100)
    )

@router.post("/trigger")
async def trigger_scan(target: str, scan_type: str = "vulnerability"):
    """Trigger a new security scan."""
    # In a real implementation, this would dispatch a job to the agent
    scan = generate_mock_scan(target)
    scan_results.append(scan)
    return scan

@router.get("/results")
async def get_scan_results(limit: int = 10) -> List[SecurityScanResult]:
    """Get recent security scan results."""
    if not scan_results:
        # Seed some data if empty
        scan_results.append(generate_mock_scan("ancientreport-ui"))
        scan_results.append(generate_mock_scan("ancientreport-analysis"))
    return sorted(scan_results, key=lambda x: x.started_at, reverse=True)[:limit]

@router.get("/file-integrity")
async def get_file_integrity_events(limit: int = 20) -> List[FileIntegrityEvent]:
    """Get file integrity monitoring events."""
    if not file_events:
        file_events.append(FileIntegrityEvent(
            id="fim-1",
            path="/etc/passwd",
            event_type="modified",
            severity="critical",
            timestamp=datetime.utcnow().isoformat(),
            user="root",
            process="vim",
            diff="root:x:0:0:root:/root:/bin/bash -> root:x:0:0:root:/root:/bin/zsh"
        ))
    return file_events

@router.get("/runtime")
async def get_runtime_events(limit: int = 20) -> List[RuntimeSecurityEvent]:
    """Get runtime security events (eBPF detected)."""
    if not runtime_events:
        runtime_events.append(RuntimeSecurityEvent(
            id="run-1",
            rule_name="Reverse Shell Detected",
            severity="critical",
            container_id="ancientreport-ui",
            process_name="nc",
            pid=12345,
            timestamp=datetime.utcnow().isoformat(),
            details="Process 'nc' initiated connection to external IP 45.33.22.11:4444"
        ))
    return runtime_events

@router.get("/stats")
async def get_security_stats():
    """Get aggregate security statistics."""
    return {
        "vulnerabilities_total": sum(len(s.vulnerabilities) for s in scan_results),
        "critical_vulns": sum(1 for s in scan_results for v in s.vulnerabilities if v.severity == "critical"),
        "scans_last_24h": len(scan_results),
        "runtime_incidents": len(runtime_events),
        "fim_events": len(file_events)
    }
