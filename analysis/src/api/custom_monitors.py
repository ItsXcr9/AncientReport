"""
Custom Monitors API for AncientReport V3
Manage port, HTTP, process, and script monitors
Persisted to ClickHouse for durability
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import uuid
import json
import httpx
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/monitors", tags=["Custom Monitors"])

# ClickHouse configuration
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "AncientReport")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

# In-memory cache (loaded from ClickHouse on startup)
monitors_db: Dict[str, dict] = {}
_initialized = False


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


async def load_monitors_from_clickhouse():
    """Load all monitors from ClickHouse into memory."""
    global monitors_db, _initialized
    
    query = """
    SELECT id, name, type, config, interval_seconds, enabled, created_at, updated_at 
    FROM custom_monitors 
    FINAL 
    FORMAT JSONEachRow
    """
    
    logger.info(f"Loading custom monitors from ClickHouse ({CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/{CLICKHOUSE_DB})...")
    result = await clickhouse_query(query)
    
    if result:
        logger.info(f"ClickHouse query returned {len(result)} bytes of data")
        monitors_db.clear()
        for line in result.strip().split('\n'):
            if line:
                try:
                    row = json.loads(line)
                    monitor_id = str(row['id'])
                    # Parse config JSON string
                    config = row['config']
                    if isinstance(config, str):
                        config = json.loads(config)
                    
                    monitors_db[monitor_id] = {
                        "id": monitor_id,
                        "name": row['name'],
                        "type": row['type'],
                        "config": config,
                        "interval_seconds": row['interval_seconds'],
                        "enabled": bool(row['enabled']),
                        "created_at": row['created_at'],
                        "updated_at": row['updated_at'],
                    }
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse monitor row: {e}")
        logger.info(f"✓ Loaded {len(monitors_db)} custom monitors from ClickHouse")
    else:
        logger.warning("No custom monitors loaded from ClickHouse (query returned empty result or table doesn't exist)")
    
    _initialized = True


async def save_monitor_to_clickhouse(monitor: dict) -> bool:
    """Save a monitor to ClickHouse."""
    config_json = json.dumps(monitor['config']).replace("'", "\\'")
    
    # Convert updated_at to ClickHouse DateTime format (YYYY-MM-DD HH:MM:SS)
    updated_at = monitor['updated_at']
    if 'T' in updated_at:
        updated_at = updated_at.replace('T', ' ')[:19]
    
    query = f"""
    INSERT INTO custom_monitors (id, name, type, config, interval_seconds, enabled, created_at, updated_at)
    VALUES (
        '{monitor['id']}',
        '{monitor['name'].replace("'", "\\'")}',
        '{monitor['type']}',
        '{config_json}',
        {monitor['interval_seconds']},
        {1 if monitor['enabled'] else 0},
        '{monitor['created_at']}',
        '{updated_at}'
    )
    """
    
    return await clickhouse_insert(query)


async def delete_monitor_from_clickhouse(monitor_id: str) -> bool:
    """Delete a monitor from ClickHouse."""
    query = f"ALTER TABLE custom_monitors DELETE WHERE id = '{monitor_id}'"
    return await clickhouse_insert(query)


async def ensure_initialized():
    """Ensure monitors are loaded from ClickHouse."""
    global _initialized
    if not _initialized:
        await load_monitors_from_clickhouse()


@router.post("", response_model=MonitorResponse)
async def create_monitor(request: CreateMonitorRequest):
    """Create a new custom monitor"""
    await ensure_initialized()
    
    monitor_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    monitor = {
        "id": monitor_id,
        "name": request.name,
        "type": request.type.value,
        "config": request.config,
        "interval_seconds": request.interval_seconds,
        "enabled": request.enabled,
        "created_at": now,
        "updated_at": now,
    }
    
    # Save to ClickHouse
    saved = await save_monitor_to_clickhouse(monitor)
    if not saved:
        logger.warning(f"Failed to persist monitor {monitor_id} to ClickHouse, keeping in memory only")
    
    # Add to in-memory cache
    monitors_db[monitor_id] = monitor
    
    return MonitorResponse(**monitor)


@router.get("", response_model=List[MonitorResponse])
async def list_monitors(
    enabled_only: bool = Query(default=False, description="Only return enabled monitors"),
    type: Optional[MonitorType] = Query(default=None, description="Filter by type"),
    hostname: Optional[str] = Query(default=None, description="Filter by hostname (optional - monitors are global)")
):
    """List all custom monitors. Monitors are global, hostname filter is optional."""
    await ensure_initialized()
    
    logger.info(f"List monitors request: {len(monitors_db)} monitors in memory, enabled_only={enabled_only}, type={type}, hostname={hostname}")
    
    monitors = list(monitors_db.values())
    
    if enabled_only:
        monitors = [m for m in monitors if m["enabled"]]
    
    if type:
        monitors = [m for m in monitors if m["type"] == type.value]
    
    # Note: hostname filtering is optional - monitors are global
    # Only filter if both hostname is specified AND monitor config has a host
    if hostname:
        filtered = [m for m in monitors if 
                   hostname.lower() in m.get("name", "").lower() or
                   hostname.lower() in str(m.get("config", {}).get("host", "")).lower()]
        # If filtering removes all monitors, return all (monitors are global)
        if len(filtered) == 0:
            logger.info(f"Hostname filter '{hostname}' matched 0 monitors, returning all {len(monitors)} monitors (monitors are global)")
        else:
            monitors = filtered
            logger.info(f"Hostname filter '{hostname}' matched {len(monitors)} monitors")
    
    logger.info(f"Returning {len(monitors)} monitors")
    return [MonitorResponse(**m) for m in monitors]


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(monitor_id: str):
    """Get a specific monitor by ID"""
    await ensure_initialized()
    
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    return MonitorResponse(**monitors_db[monitor_id])


@router.put("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(monitor_id: str, request: CreateMonitorRequest):
    """Update an existing monitor"""
    await ensure_initialized()
    
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    monitor = monitors_db[monitor_id]
    monitor.update({
        "name": request.name,
        "type": request.type.value,
        "config": request.config,
        "interval_seconds": request.interval_seconds,
        "enabled": request.enabled,
        "updated_at": datetime.utcnow().isoformat(),
    })
    
    # Save to ClickHouse (ReplacingMergeTree will handle the update)
    await save_monitor_to_clickhouse(monitor)
    
    return MonitorResponse(**monitor)


@router.delete("/{monitor_id}")
async def delete_monitor(monitor_id: str):
    """Delete a monitor"""
    await ensure_initialized()
    
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    # Delete from ClickHouse
    await delete_monitor_from_clickhouse(monitor_id)
    
    # Remove from in-memory cache
    del monitors_db[monitor_id]
    return {"status": "deleted", "id": monitor_id}


@router.post("/{monitor_id}/toggle")
async def toggle_monitor(monitor_id: str):
    """Toggle a monitor's enabled state"""
    await ensure_initialized()
    
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    monitor = monitors_db[monitor_id]
    monitor["enabled"] = not monitor["enabled"]
    monitor["updated_at"] = datetime.utcnow().isoformat()
    
    # Save to ClickHouse
    await save_monitor_to_clickhouse(monitor)
    
    return {"id": monitor_id, "enabled": monitor["enabled"]}


@router.get("/{monitor_id}/results", response_model=List[MonitorResult])
async def get_monitor_results(
    monitor_id: str,
    start: Optional[str] = Query(default=None, description="Start time ISO format"),
    end: Optional[str] = Query(default=None, description="End time ISO format"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results")
):
    """Get monitor check results"""
    await ensure_initialized()
    
    if monitor_id not in monitors_db:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    # Query ClickHouse for results
    query = f"""
    SELECT timestamp, status, latency_ms, response, error
    FROM custom_monitor_results
    WHERE monitor_id = '{monitor_id}'
    """
    if start:
        query += f" AND timestamp >= '{start}'"
    if end:
        query += f" AND timestamp <= '{end}'"
    query += f" ORDER BY timestamp DESC LIMIT {limit} FORMAT JSONEachRow"
    
    result = await clickhouse_query(query)
    if result:
        results = []
        for line in result.strip().split('\n'):
            if line:
                try:
                    row = json.loads(line)
                    results.append(MonitorResult(
                        timestamp=row['timestamp'],
                        status=row['status'],
                        latency_ms=row['latency_ms'],
                        response=row.get('response'),
                        error=row.get('error')
                    ))
                except json.JSONDecodeError:
                    pass
        return results
    
    return []


@router.post("/reload")
async def reload_monitors():
    """Reload monitors from ClickHouse"""
    global _initialized
    _initialized = False
    await load_monitors_from_clickhouse()
    return {"status": "reloaded", "count": len(monitors_db)}


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
