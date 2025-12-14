"""
Synthetic Monitoring API - Proactive HTTP Endpoint Checks
Periodically checks URL endpoints and records latency/availability
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import asyncio
import uuid
import json
import httpx

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/synthetics", tags=["Synthetic Monitoring"])

# Shared HTTP client for synthetic checks
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Get shared HTTP client"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True
        )
    return _http_client


# ============================================
# Models
# ============================================

class MonitorCreate(BaseModel):
    name: str
    description: str = ""
    url: str
    method: str = "GET"
    headers: dict = {}
    body: str = ""
    expected_status: int = 200
    expected_body_contains: str = ""
    timeout_ms: int = 10000
    interval_seconds: int = 60


class MonitorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    expected_status: Optional[int] = None
    expected_body_contains: Optional[str] = None
    timeout_ms: Optional[int] = None
    interval_seconds: Optional[int] = None
    enabled: Optional[bool] = None


class Monitor(BaseModel):
    id: str
    name: str
    description: str
    url: str
    method: str
    expected_status: int
    timeout_ms: int
    interval_seconds: int
    enabled: bool
    last_check: Optional[str]
    last_status: str
    last_latency_ms: float
    consecutive_failures: int
    created_at: str


class CheckResult(BaseModel):
    id: str
    monitor_id: str
    monitor_name: str
    timestamp: str
    success: bool
    status_code: int
    latency_ms: float
    error_message: str


# ============================================
# HTTP Check Execution
# ============================================

async def run_http_check(
    url: str,
    method: str = "GET",
    headers: dict = None,
    body: str = "",
    expected_status: int = 200,
    expected_body_contains: str = "",
    timeout_ms: int = 10000
) -> dict:
    """Execute an HTTP check and return results"""
    
    result = {
        "success": False,
        "status_code": 0,
        "latency_ms": 0,
        "error_message": "",
        "response_size": 0
    }
    
    try:
        http_client = await get_http_client()
        timeout = timeout_ms / 1000.0
        
        start_time = datetime.now()
        
        if method.upper() == "POST":
            response = await http_client.post(
                url,
                headers=headers or {},
                content=body,
                timeout=timeout
            )
        elif method.upper() == "PUT":
            response = await http_client.put(
                url,
                headers=headers or {},
                content=body,
                timeout=timeout
            )
        elif method.upper() == "DELETE":
            response = await http_client.delete(
                url,
                headers=headers or {},
                timeout=timeout
            )
        else:  # GET
            response = await http_client.get(
                url,
                headers=headers or {},
                timeout=timeout
            )
        
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        result["status_code"] = response.status_code
        result["latency_ms"] = latency
        result["response_size"] = len(response.content)
        
        # Check status code
        status_ok = response.status_code == expected_status
        
        # Check body content if specified
        body_ok = True
        if expected_body_contains:
            body_ok = expected_body_contains in response.text
            if not body_ok:
                result["error_message"] = f"Response body does not contain '{expected_body_contains}'"
        
        result["success"] = status_ok and body_ok
        
        if not status_ok:
            result["error_message"] = f"Expected status {expected_status}, got {response.status_code}"
    
    except httpx.TimeoutException:
        result["error_message"] = "Request timed out"
        result["latency_ms"] = timeout_ms
    except httpx.ConnectError as e:
        result["error_message"] = f"Connection failed: {str(e)}"
    except Exception as e:
        result["error_message"] = str(e)
    
    return result


# ============================================
# API Endpoints
# ============================================

@router.get("/monitors", response_model=List[Monitor])
async def list_monitors():
    """List all synthetic monitors"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = """
            SELECT 
                toString(id), name, description, url, method, expected_status,
                timeout_ms, interval_seconds, enabled, 
                toString(last_check), last_status, last_latency_ms,
                consecutive_failures, toString(created_at)
            FROM synthetic_monitors FINAL
            ORDER BY name
        """
        rows = client.client.execute(query)
        
        return [
            Monitor(
                id=row[0],
                name=row[1],
                description=row[2],
                url=row[3],
                method=row[4],
                expected_status=row[5],
                timeout_ms=row[6],
                interval_seconds=row[7],
                enabled=bool(row[8]),
                last_check=row[9] if row[9] != "1970-01-01 00:00:00" else None,
                last_status=row[10],
                last_latency_ms=row[11],
                consecutive_failures=row[12],
                created_at=row[13]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list monitors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitors", response_model=Monitor)
async def create_monitor(data: MonitorCreate):
    """Create a new synthetic monitor"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        monitor_id = str(uuid.uuid4())
        headers_json = json.dumps(data.headers)
        
        query = f"""
            INSERT INTO synthetic_monitors (
                id, name, description, url, method, headers, body,
                expected_status, expected_body_contains, timeout_ms, interval_seconds
            ) VALUES (
                toUUID('{monitor_id}'),
                '{data.name.replace("'", "''")}',
                '{data.description.replace("'", "''")}',
                '{data.url.replace("'", "''")}',
                '{data.method}',
                '{headers_json.replace("'", "''")}',
                '{data.body.replace("'", "''")}',
                {data.expected_status},
                '{data.expected_body_contains.replace("'", "''")}',
                {data.timeout_ms},
                {data.interval_seconds}
            )
        """
        client.client.execute(query)
        
        return Monitor(
            id=monitor_id,
            name=data.name,
            description=data.description,
            url=data.url,
            method=data.method,
            expected_status=data.expected_status,
            timeout_ms=data.timeout_ms,
            interval_seconds=data.interval_seconds,
            enabled=True,
            last_check=None,
            last_status="unknown",
            last_latency_ms=0,
            consecutive_failures=0,
            created_at=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to create monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitors/{monitor_id}")
async def get_monitor(monitor_id: str):
    """Get a specific monitor with recent results"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            SELECT 
                toString(id), name, description, url, method, headers, body,
                expected_status, expected_body_contains, timeout_ms, interval_seconds,
                enabled, toString(last_check), last_status, last_latency_ms,
                consecutive_failures, toString(created_at)
            FROM synthetic_monitors FINAL
            WHERE id = toUUID('{monitor_id}')
        """
        rows = client.client.execute(query)
        
        if not rows:
            raise HTTPException(status_code=404, detail="Monitor not found")
        
        row = rows[0]
        
        # Get recent results
        results_query = f"""
            SELECT toString(id), toString(timestamp), success, status_code, latency_ms, error_message
            FROM synthetic_results
            WHERE monitor_id = toUUID('{monitor_id}')
            ORDER BY timestamp DESC
            LIMIT 20
        """
        results = client.client.execute(results_query)
        
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "url": row[3],
            "method": row[4],
            "headers": json.loads(row[5]) if row[5] else {},
            "body": row[6],
            "expected_status": row[7],
            "expected_body_contains": row[8],
            "timeout_ms": row[9],
            "interval_seconds": row[10],
            "enabled": bool(row[11]),
            "last_check": row[12] if row[12] != "1970-01-01 00:00:00" else None,
            "last_status": row[13],
            "last_latency_ms": row[14],
            "consecutive_failures": row[15],
            "created_at": row[16],
            "recent_results": [
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "success": bool(r[2]),
                    "status_code": r[3],
                    "latency_ms": r[4],
                    "error_message": r[5]
                }
                for r in results
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitors/{monitor_id}/check")
async def trigger_check(monitor_id: str):
    """Manually trigger a check for a monitor"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Get monitor config
        query = f"""
            SELECT url, method, headers, body, expected_status, 
                   expected_body_contains, timeout_ms, name
            FROM synthetic_monitors FINAL
            WHERE id = toUUID('{monitor_id}')
        """
        rows = client.client.execute(query)
        
        if not rows:
            raise HTTPException(status_code=404, detail="Monitor not found")
        
        row = rows[0]
        url = row[0]
        method = row[1]
        headers = json.loads(row[2]) if row[2] else {}
        body = row[3]
        expected_status = row[4]
        expected_body = row[5]
        timeout_ms = row[6]
        name = row[7]
        
        # Run check
        result = await run_http_check(
            url=url,
            method=method,
            headers=headers,
            body=body,
            expected_status=expected_status,
            expected_body_contains=expected_body,
            timeout_ms=timeout_ms
        )
        
        # Store result
        await store_check_result(client, monitor_id, name, result)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/monitors/{monitor_id}")
async def delete_monitor(monitor_id: str):
    """Delete a synthetic monitor"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        client.client.execute(f"ALTER TABLE synthetic_monitors DELETE WHERE id = toUUID('{monitor_id}')")
        client.client.execute(f"ALTER TABLE synthetic_results DELETE WHERE monitor_id = toUUID('{monitor_id}')")
        return {"status": "deleted", "id": monitor_id}
    except Exception as e:
        logger.error(f"Failed to delete monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitors/{monitor_id}/results", response_model=List[CheckResult])
async def get_monitor_results(monitor_id: str, hours: int = 24, limit: int = 100):
    """Get check results for a monitor"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            SELECT 
                toString(id), toString(monitor_id), monitor_name,
                toString(timestamp), success, status_code, latency_ms, error_message
            FROM synthetic_results
            WHERE monitor_id = toUUID('{monitor_id}')
              AND timestamp >= now() - INTERVAL {hours} HOUR
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        rows = client.client.execute(query)
        
        return [
            CheckResult(
                id=row[0],
                monitor_id=row[1],
                monitor_name=row[2],
                timestamp=row[3],
                success=bool(row[4]),
                status_code=row[5],
                latency_ms=row[6],
                error_message=row[7]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to get results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_synthetics_stats():
    """Get overall synthetic monitoring stats"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Overall availability in last 24h
        query = """
            SELECT 
                count() as total,
                countIf(success = 1) as successful,
                avg(latency_ms) as avg_latency,
                max(latency_ms) as max_latency
            FROM synthetic_results
            WHERE timestamp >= now() - INTERVAL 24 HOUR
        """
        stats = client.client.execute(query)
        
        total = stats[0][0] if stats else 0
        successful = stats[0][1] if stats else 0
        availability = (successful / total * 100) if total > 0 else 100
        
        # Count monitors by status
        monitors_query = """
            SELECT last_status, count() as cnt
            FROM synthetic_monitors FINAL
            WHERE enabled = 1
            GROUP BY last_status
        """
        monitors = client.client.execute(monitors_query)
        
        return {
            "total_checks_24h": total,
            "successful_checks_24h": successful,
            "availability_24h": round(availability, 2),
            "avg_latency_ms": round(stats[0][2], 2) if stats and stats[0][2] else 0,
            "max_latency_ms": round(stats[0][3], 2) if stats and stats[0][3] else 0,
            "monitors_by_status": {row[0]: row[1] for row in monitors}
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Background Tasks
# ============================================

async def store_check_result(client, monitor_id: str, monitor_name: str, result: dict):
    """Store a check result and update monitor status"""
    try:
        # Insert result
        error_msg = result["error_message"].replace("'", "''")
        insert_query = f"""
            INSERT INTO synthetic_results (
                monitor_id, monitor_name, success, status_code, latency_ms, 
                error_message, response_size
            ) VALUES (
                toUUID('{monitor_id}'),
                '{monitor_name.replace("'", "''")}',
                {1 if result["success"] else 0},
                {result["status_code"]},
                {result["latency_ms"]},
                '{error_msg}',
                {result["response_size"]}
            )
        """
        client.client.execute(insert_query)
        
        # Update monitor status
        status = "success" if result["success"] else "failure"
        
        # Get current consecutive failures
        count_query = f"""
            SELECT consecutive_failures FROM synthetic_monitors FINAL
            WHERE id = toUUID('{monitor_id}')
        """
        count_result = client.client.execute(count_query)
        current_failures = count_result[0][0] if count_result else 0
        
        new_failures = 0 if result["success"] else current_failures + 1
        
        update_query = f"""
            ALTER TABLE synthetic_monitors UPDATE
            last_check = now(),
            last_status = '{status}',
            last_latency_ms = {result["latency_ms"]},
            consecutive_failures = {new_failures}
            WHERE id = toUUID('{monitor_id}')
        """
        client.client.execute(update_query)
        
    except Exception as e:
        logger.error(f"Failed to store check result: {e}")


async def run_scheduled_checks():
    """Run all enabled monitors that are due for checking"""
    client = get_clickhouse_client()
    if not client:
        return
    
    try:
        # Get monitors due for check
        query = """
            SELECT 
                toString(id), name, url, method, headers, body,
                expected_status, expected_body_contains, timeout_ms, interval_seconds,
                last_check
            FROM synthetic_monitors FINAL
            WHERE enabled = 1
        """
        monitors = client.client.execute(query)
        
        now = datetime.now()
        
        for monitor in monitors:
            monitor_id = monitor[0]
            name = monitor[1]
            url = monitor[2]
            method = monitor[3]
            headers = json.loads(monitor[4]) if monitor[4] else {}
            body = monitor[5]
            expected_status = monitor[6]
            expected_body = monitor[7]
            timeout_ms = monitor[8]
            interval = monitor[9]
            last_check = monitor[10]
            
            # Check if due
            if last_check and last_check.year > 1970:
                elapsed = (now - last_check).total_seconds()
                if elapsed < interval:
                    continue
            
            # Run check
            logger.debug(f"Running synthetic check: {name}")
            result = await run_http_check(
                url=url,
                method=method,
                headers=headers,
                body=body,
                expected_status=expected_status,
                expected_body_contains=expected_body,
                timeout_ms=timeout_ms
            )
            
            # Store result
            await store_check_result(client, monitor_id, name, result)
            
            if not result["success"]:
                logger.warning(f"Synthetic check failed: {name} - {result['error_message']}")
    
    except Exception as e:
        logger.error(f"Scheduled checks failed: {e}")


async def synthetic_check_loop():
    """Background loop for synthetic checks"""
    logger.info("Starting synthetic monitoring loop")
    while True:
        try:
            await run_scheduled_checks()
        except Exception as e:
            logger.error(f"Synthetic check loop error: {e}")
        await asyncio.sleep(10)  # Check every 10 seconds
