"""
Security API for AncientReport V3
Port scanning, security events, and threat detection
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

router = APIRouter(prefix="/api/v3/security", tags=["Security"])


class ScanType(str, Enum):
    PORT = "port"
    NETWORK = "network"
    CONTAINER = "container"
    FILE = "file"


class SecuritySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SecurityEventType(str, Enum):
    PORT_OPENED = "port_opened"
    SUSPICIOUS_CONNECTION = "suspicious_connection"
    FILE_CHANGED = "file_changed"
    PROCESS_SUSPICIOUS = "process_suspicious"
    CONTAINER_PRIVILEGED = "container_privileged"
    THREAT_DETECTED = "threat_detected"


class OpenPort(BaseModel):
    """Open port information"""
    port: int
    protocol: str
    service: Optional[str] = None
    state: str
    is_risky: bool
    risk_reason: Optional[str] = None


class ScanResult(BaseModel):
    """Security scan result"""
    hostname: str
    target: str
    scan_type: ScanType
    timestamp: str
    open_ports: List[OpenPort]
    risky_ports: List[OpenPort]
    risk_score: int = Field(ge=0, le=100)


class SecurityEvent(BaseModel):
    """Security event"""
    timestamp: str
    hostname: str
    event_type: SecurityEventType
    severity: SecuritySeverity
    source: str
    description: str
    details: Dict[str, Any]
    resolved: bool = False


class SecurityDashboard(BaseModel):
    """Security dashboard summary"""
    overall_score: int = Field(ge=0, le=100)
    hosts_scanned: int
    total_open_ports: int
    risky_ports_count: int
    active_threats: int
    recent_events: List[SecurityEvent]


class TriggerScanRequest(BaseModel):
    """Request to trigger a security scan"""
    hostname: Optional[str] = None
    scan_type: ScanType = ScanType.PORT
    target: str = "127.0.0.1"
    port_range: Optional[str] = None  # e.g., "1-1000"


import subprocess


def get_real_open_ports_count() -> int:
    """Get real count of listening ports from the HOST system via /host/proc."""
    count = 0
    
    # Read from /host/proc/net/tcp (host's network stack)
    for tcp_file in ['/host/proc/net/tcp', '/host/proc/net/tcp6', '/proc/net/tcp', '/proc/net/tcp6']:
        try:
            with open(tcp_file, 'r') as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) > 3 and parts[3].upper() == '0A':  # 0A = LISTEN state
                        count += 1
        except FileNotFoundError:
            continue
        except Exception as e:
            continue
    
    # Fallback to ss command if no /host/proc files found
    if count == 0:
        try:
            result = subprocess.run(
                ['ss', '-tuln'],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split('\n')
            count = max(0, len(lines) - 1)
        except Exception:
            pass
    
    return count


def get_real_tcp_connections_count() -> int:
    """Get real count of active TCP connections."""
    try:
        result = subprocess.run(
            ['ss', '-tun'],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split('\n')
        return max(0, len(lines) - 1)
    except Exception:
        return 0


def get_real_process_count() -> int:
    """Get real count of running processes."""
    try:
        for proc_path in ['/host/proc', '/proc']:
            count = 0
            import os
            for entry in os.listdir(proc_path):
                if entry.isdigit():
                    count += 1
            if count > 0:
                return count
    except:
        pass
    return 0


@router.get("/dashboard", response_model=SecurityDashboard)
async def get_security_dashboard(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname")
):
    """Get security dashboard summary with REAL data."""
    open_ports = get_real_open_ports_count()
    tcp_connections = get_real_tcp_connections_count()
    
    # Calculate a simple security score based on open ports and connections
    # More open ports = slightly lower score (but still secure baseline)
    score = 90
    if open_ports > 50:
        score -= 10
    elif open_ports > 30:
        score -= 5
    
    return SecurityDashboard(
        overall_score=score,
        hosts_scanned=1,
        total_open_ports=open_ports,
        risky_ports_count=0,  # Would need proper scanning
        active_threats=0,
        recent_events=[]
    )


@router.get("/scans", response_model=List[ScanResult])
async def get_scan_results(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname"),
    scan_type: Optional[ScanType] = Query(default=None, description="Filter by scan type"),
    start: Optional[str] = Query(default=None, description="Start time ISO format"),
    end: Optional[str] = Query(default=None, description="End time ISO format"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results")
):
    """Get security scan history"""
    # TODO: Query ClickHouse for real data
    return []


@router.get("/scans/latest", response_model=Optional[ScanResult])
async def get_latest_scan(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname")
):
    """Get the most recent security scan result"""
    # TODO: Query ClickHouse for real data
    return None


@router.post("/scans/trigger", response_model=Dict[str, str])
async def trigger_scan(request: TriggerScanRequest):
    """Trigger a new security scan"""
    # TODO: Send request to agent via NATS or API
    return {
        "status": "scheduled",
        "message": f"Security scan scheduled for {request.target}",
        "scan_type": request.scan_type
    }


@router.get("/events", response_model=List[SecurityEvent])
async def get_security_events(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname"),
    severity: Optional[SecuritySeverity] = Query(default=None, description="Filter by severity"),
    event_type: Optional[SecurityEventType] = Query(default=None, description="Filter by event type"),
    resolved: Optional[bool] = Query(default=None, description="Filter by resolved status"),
    start: Optional[str] = Query(default=None, description="Start time ISO format"),
    end: Optional[str] = Query(default=None, description="End time ISO format"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results")
):
    """Get security events"""
    # TODO: Query ClickHouse for real data
    return []


@router.post("/events/{event_id}/resolve")
async def resolve_event(event_id: str):
    """Mark a security event as resolved"""
    # TODO: Update in ClickHouse
    return {"status": "resolved", "id": event_id}


@router.get("/ports/risky")
async def get_risky_ports(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname")
):
    """Get list of risky open ports across all hosts"""
    # TODO: Query ClickHouse for real data
    return {
        "risky_ports": [],
        "hosts_affected": 0
    }


@router.get("/threats/active")
async def get_active_threats(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname")
):
    """Get active security threats"""
    # TODO: Query ClickHouse for real data
    return {
        "threats": [],
        "severity_breakdown": {
            "critical": 0,
            "warning": 0,
            "info": 0
        }
    }


@router.get("/fim/changes")
async def get_file_integrity_changes(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname"),
    start: Optional[str] = Query(default=None, description="Start time ISO format"),
    limit: int = Query(default=50, ge=1, le=500, description="Max results")
):
    """Get file integrity monitoring changes"""
    # TODO: Query ClickHouse for real data
    return []


@router.get("/report")
async def get_security_report(
    hostname: Optional[str] = Query(default=None, description="Filter by hostname"),
    period: str = Query(default="24h", description="Report period: 1h, 24h, 7d, 30d")
):
    """Generate security report for the specified period"""
    # TODO: Generate comprehensive security report
    return {
        "period": period,
        "hostname": hostname or "all",
        "summary": {
            "scans_performed": 0,
            "new_ports_discovered": 0,
            "ports_closed": 0,
            "security_events": 0,
            "threats_detected": 0,
            "threats_resolved": 0
        },
        "risk_trend": [],
        "recommendations": []
    }
