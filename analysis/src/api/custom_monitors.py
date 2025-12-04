"""
Custom Monitors API for AncientReport V3
Manage port, HTTP, process, and script monitors
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/v3/monitors", tags=["Custom Monitors"])

# In-memory storage (will be replaced with ClickHouse)
monitors_db: Dict[str, dict] = {}


class MonitorType(str, Enum):
    PORT = "port"
    HTTP = "http"
    PROCESS = "process"
    SCRIPT = "script"
    METRIC = "metric"


class MonitorStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class PortMonitorConfig(BaseModel):
    """Configuration for port monitoring"""
    host: str = Field(..., description="Host to monitor")
    port: int = Field(..., ge=1, le=65535, description="Port number")
    timeout_ms: int = Field(default=5000, description="Timeout in milliseconds")
    expected_response: Optional[str] = Field(default=None, description="Expected response string")
    send_data: Optional[str] = Field(default=None, description="Data to send after connecting")


class HttpMonitorConfig(BaseModel):
    """Configuration for HTTP monitoring"""
    url: str = Field(..., description="URL to monitor")
    method: str = Field(default="GET", description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Custom headers")
    body: Optional[str] = Field(default=None, description="Request body")
    timeout_ms: int = Field(default=5000, description="Timeout in milliseconds")
    expected_status: Optional[int] = Field(default=None, description="Expected status code")
    expected_body_contains: Optional[str] = Field(default=None, description="Expected body content")


class ProcessMonitorConfig(BaseModel):
    """Configuration for process monitoring"""
    process_match: str = Field(..., description="Process name pattern (regex)")
    expected_count: int = Field(default=1, ge=1, description="Expected process count")
    cpu_threshold_percent: Optional[float] = Field(default=None, description="CPU alert threshold")
    memory_threshold_mb: Optional[int] = Field(default=None, description="Memory alert threshold")


class ScriptMonitorConfig(BaseModel):
    """Configuration for script monitoring"""
    command: str = Field(..., description="Command to execute")
    args: List[str] = Field(default=[], description="Command arguments")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds")
    expected_exit_code: Optional[int] = Field(default=0, description="Expected exit code")
    expected_output_contains: Optional[str] = Field(default=None, description="Expected output content")


class CreateMonitorRequest(BaseModel):
    """Request to create a custom monitor"""
    name: str = Field(..., min_length=1, max_length=100, description="Monitor name")
    type: MonitorType = Field(..., description="Monitor type")
    config: Dict[str, Any] = Field(..., description="Type-specific configuration")
    interval_seconds: int = Field(default=60, ge=10, le=3600, description="Check interval")
    enabled: bool = Field(default=True, description="Whether monitor is enabled")


class MonitorResponse(BaseModel):
    """Monitor details response"""
    id: str
    name: str
    type: MonitorType
    config: Dict[str, Any]
    interval_seconds: int
    enabled: bool
    created_at: str
    updated_at: str


class MonitorResult(BaseModel):
    """Single monitor result"""
    timestamp: str
    status: MonitorStatus
    latency_ms: float
    response: Optional[str] = None
    error: Optional[str] = None


@router.post("", response_model=MonitorResponse)
async def create_monitor(request: CreateMonitorRequest):
    """Create a new custom monitor"""
    monitor_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    monitor = {
        "id": monitor_id,
        "name": request.name,
        "type": request.type,
        "config": request.config,
        "interval_seconds": request.interval_seconds,
        "enabled": request.enabled,
        "created_at": now,
        "updated_at": now,
    }
    
    monitors_db[monitor_id] = monitor
    
    # TODO: Store in ClickHouse
    # await store_monitor_config(monitor)
    
    return MonitorResponse(**monitor)


@router.get("", response_model=List[MonitorResponse])
async def list_monitors(
    enabled_only: bool = Query(default=False, description="Only return enabled monitors"),
    type: Optional[MonitorType] = Query(default=None, description="Filter by type")
):
    """List all custom monitors"""
    monitors = list(monitors_db.values())
    
    if enabled_only:
        monitors = [m for m in monitors if m["enabled"]]
    
    if type:
        monitors = [m for m in monitors if m["type"] == type]
    
    return [MonitorResponse(**m) for m in monitors]


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(monitor_id: str):
    """Get a specific monitor by ID"""
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    return MonitorResponse(**monitors_db[monitor_id])


@router.put("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(monitor_id: str, request: CreateMonitorRequest):
    """Update an existing monitor"""
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    monitor = monitors_db[monitor_id]
    monitor.update({
        "name": request.name,
        "type": request.type,
        "config": request.config,
        "interval_seconds": request.interval_seconds,
        "enabled": request.enabled,
        "updated_at": datetime.utcnow().isoformat(),
    })
    
    return MonitorResponse(**monitor)


@router.delete("/{monitor_id}")
async def delete_monitor(monitor_id: str):
    """Delete a monitor"""
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    del monitors_db[monitor_id]
    return {"status": "deleted", "id": monitor_id}


@router.post("/{monitor_id}/toggle")
async def toggle_monitor(monitor_id: str):
    """Toggle a monitor's enabled state"""
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    monitor = monitors_db[monitor_id]
    monitor["enabled"] = not monitor["enabled"]
    monitor["updated_at"] = datetime.utcnow().isoformat()
    
    return {"id": monitor_id, "enabled": monitor["enabled"]}


@router.get("/{monitor_id}/results", response_model=List[MonitorResult])
async def get_monitor_results(
    monitor_id: str,
    start: Optional[str] = Query(default=None, description="Start time ISO format"),
    end: Optional[str] = Query(default=None, description="End time ISO format"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results")
):
    """Get monitor check results"""
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    # TODO: Query ClickHouse for results
    # For now, return empty list
    return []


# Convenience endpoints for common monitor types

@router.post("/port", response_model=MonitorResponse)
async def create_port_monitor(
    name: str,
    config: PortMonitorConfig,
    interval_seconds: int = 60,
    enabled: bool = True
):
    """Create a port monitor (convenience endpoint)"""
    request = CreateMonitorRequest(
        name=name,
        type=MonitorType.PORT,
        config=config.model_dump(),
        interval_seconds=interval_seconds,
        enabled=enabled
    )
    return await create_monitor(request)


@router.post("/http", response_model=MonitorResponse)
async def create_http_monitor(
    name: str,
    config: HttpMonitorConfig,
    interval_seconds: int = 60,
    enabled: bool = True
):
    """Create an HTTP monitor (convenience endpoint)"""
    request = CreateMonitorRequest(
        name=name,
        type=MonitorType.HTTP,
        config=config.model_dump(),
        interval_seconds=interval_seconds,
        enabled=enabled
    )
    return await create_monitor(request)
