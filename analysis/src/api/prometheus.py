"""
Prometheus-compatible Metrics API
Scrapes /metrics endpoints and stores in ClickHouse
Replaces Prometheus + Grafana
"""
import asyncio
import logging
import re
import json
from uuid import UUID
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl
import httpx

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Global scraper task reference
_scraper_task: Optional[asyncio.Task] = None

# Shared HTTP client for scraping (properly managed connection pool)
_http_client: Optional[httpx.AsyncClient] = None

# Semaphore to limit concurrent scrapes (prevents file descriptor exhaustion)
_scrape_semaphore: Optional[asyncio.Semaphore] = None
MAX_CONCURRENT_SCRAPES = 10  # Maximum simultaneous scrape requests

async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client with connection pooling"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # Use limits to prevent connection exhaustion
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=50,
            keepalive_expiry=30.0
        )
        _http_client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True
        )
    return _http_client

async def close_http_client():
    """Close the shared HTTP client"""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# ============================================
# Models
# ============================================

class TargetCreate(BaseModel):
    name: str
    url: str
    scrape_interval: int = 15
    timeout: int = 10
    labels: Dict[str, str] = {}
    enabled: bool = True


class TargetUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    scrape_interval: Optional[int] = None
    timeout: Optional[int] = None
    labels: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None


class Target(BaseModel):
    id: str
    name: str
    url: str
    scrape_interval: int
    timeout: int
    labels: Dict[str, str]
    enabled: bool
    last_scrape: Optional[str]
    last_status: str
    last_error: str
    metrics_count: int
    created_at: str


class MetricQuery(BaseModel):
    target_id: Optional[str] = None
    metric_name: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int = 1000


# ============================================
# Target CRUD Endpoints
# ============================================

@router.get("/targets", response_model=List[Target])
async def list_targets():
    """List all metric scrape targets"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        query = """
            SELECT 
                toString(id) as id,
                name, url, scrape_interval, timeout,
                labels, enabled,
                toString(last_scrape) as last_scrape,
                last_status, last_error, metrics_count,
                toString(created_at) as created_at
            FROM metric_targets
            FINAL
            ORDER BY name
        """
        result = client.client.execute(query)
        
        targets = []
        for row in result:
            labels = {}
            try:
                if row[5]:
                    labels = json.loads(row[5])
            except:
                pass
            
            targets.append(Target(
                id=row[0],
                name=row[1],
                url=row[2],
                scrape_interval=row[3],
                timeout=row[4],
                labels=labels,
                enabled=row[6],
                last_scrape=row[7],
                last_status=row[8],
                last_error=row[9],
                metrics_count=row[10],
                created_at=row[11]
            ))
        
        return targets
    except Exception as e:
        logger.error(f"Failed to list targets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/targets", response_model=Target)
async def create_target(target: TargetCreate, background_tasks: BackgroundTasks):
    """Create a new metric scrape target"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Insert new target
        labels_json = json.dumps(target.labels)
        query = """
            INSERT INTO metric_targets 
            (name, url, scrape_interval, timeout, labels, enabled)
            VALUES
        """
        insert_sql = f"""
            INSERT INTO metric_targets 
            (name, url, scrape_interval, timeout, labels, enabled)
            VALUES ('{target.name}', '{target.url}', {target.scrape_interval}, {target.timeout}, '{labels_json}', {1 if target.enabled else 0})
        """
        client.client.execute(insert_sql)
        
        # Fetch the created target
        fetch_query = """
            SELECT 
                toString(id) as id,
                name, url, scrape_interval, timeout,
                labels, enabled,
                toString(last_scrape) as last_scrape,
                last_status, last_error, metrics_count,
                toString(created_at) as created_at
            FROM metric_targets
            FINAL
            WHERE name = %(name)s
            ORDER BY created_at DESC
            LIMIT 1
        """
        result = client.client.execute(fetch_query % {"name": "'" + target.name + "'"})
        
        if result:
            row = result[0]
            labels = {}
            try:
                if row[5]:
                    labels = json.loads(row[5])
            except:
                pass
            
            # Trigger immediate scrape in background
            background_tasks.add_task(scrape_target_by_id, row[0])
            
            return Target(
                id=row[0],
                name=row[1],
                url=row[2],
                scrape_interval=row[3],
                timeout=row[4],
                labels=labels,
                enabled=row[6],
                last_scrape=row[7],
                last_status=row[8],
                last_error=row[9],
                metrics_count=row[10],
                created_at=row[11]
            )
        
        raise HTTPException(status_code=500, detail="Target created but not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/targets/{target_id}", response_model=Target)
async def update_target(target_id: str, update: TargetUpdate):
    """Update a metric scrape target"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Build update fields
        updates = []
        params = {"id": target_id}
        
        if update.name is not None:
            updates.append("name = %(name)s")
            params["name"] = update.name
        if update.url is not None:
            updates.append("url = %(url)s")
            params["url"] = update.url
        if update.scrape_interval is not None:
            updates.append("scrape_interval = %(interval)s")
            params["interval"] = update.scrape_interval
        if update.timeout is not None:
            updates.append("timeout = %(timeout)s")
            params["timeout"] = update.timeout
        if update.labels is not None:
            updates.append("labels = %(labels)s")
            params["labels"] = json.dumps(update.labels)
        if update.enabled is not None:
            updates.append("enabled = %(enabled)s")
            params["enabled"] = update.enabled
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updates.append("updated_at = now()")
        
        # Build final query with string interpolation
        update_str = ', '.join(updates)
        for k, v in params.items():
            if k == 'id':
                continue
            if isinstance(v, str):
                update_str = update_str.replace(f"%({k})s", f"'{v}'")
            elif isinstance(v, bool):
                update_str = update_str.replace(f"%({k})s", str(int(v)))
            else:
                update_str = update_str.replace(f"%({k})s", str(v))
        
        query = f"""
            ALTER TABLE metric_targets
            UPDATE {update_str}
            WHERE id = toUUID('{target_id}')
        """
        client.client.execute(query)
        
        # Fetch updated target
        return await get_target(target_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/targets/{target_id}")
async def delete_target(target_id: str):
    """Delete a metric scrape target"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Delete target
        query = f"ALTER TABLE metric_targets DELETE WHERE id = toUUID('{target_id}')"
        client.client.execute(query)
        
        # Also delete associated metrics
        metrics_query = f"ALTER TABLE scraped_metrics DELETE WHERE target_id = toUUID('{target_id}')"
        client.client.execute(metrics_query)
        
        return {"status": "deleted", "id": target_id}
    except Exception as e:
        logger.error(f"Failed to delete target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/targets/{target_id}", response_model=Target)
async def get_target(target_id: str):
    """Get a single target by ID"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        query = """
            SELECT 
                toString(id) as id,
                name, url, scrape_interval, timeout,
                labels, enabled,
                toString(last_scrape) as last_scrape,
                last_status, last_error, metrics_count,
                toString(created_at) as created_at
            FROM metric_targets
            FINAL
            WHERE id = toUUID('{target_id}')
        """
        result = client.client.execute(query)
        
        if not result:
            raise HTTPException(status_code=404, detail="Target not found")
        
        row = result[0]
        labels = {}
        try:
            if row[5]:
                labels = json.loads(row[5])
        except:
            pass
        
        return Target(
            id=row[0],
            name=row[1],
            url=row[2],
            scrape_interval=row[3],
            timeout=row[4],
            labels=labels,
            enabled=row[6],
            last_scrape=row[7],
            last_status=row[8],
            last_error=row[9],
            metrics_count=row[10],
            created_at=row[11]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/targets/{target_id}/test")
async def test_target(target_id: str):
    """Test connection to a scrape target"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Get target URL
        query = f"""
            SELECT url, timeout FROM metric_targets FINAL
            WHERE id = toUUID('{target_id}')
        """
        result = client.client.execute(query)
        
        if not result:
            raise HTTPException(status_code=404, detail="Target not found")
        
        url, timeout = result[0]
        
        # Test connection
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            start = datetime.now()
            response = await http_client.get(url)
            latency_ms = (datetime.now() - start).total_seconds() * 1000
            
            if response.status_code == 200:
                # Count metrics
                metrics = parse_prometheus_text(response.text)
                return {
                    "status": "success",
                    "latency_ms": round(latency_ms, 2),
                    "metrics_count": len(metrics),
                    "content_length": len(response.text)
                }
            else:
                return {
                    "status": "error",
                    "error": f"HTTP {response.status_code}",
                    "latency_ms": round(latency_ms, 2)
                }
    except httpx.RequestError as e:
        return {
            "status": "error",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Failed to test target: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Metrics Query Endpoints
# ============================================

@router.get("/scraped")
async def query_scraped_metrics(
    target_id: Optional[str] = None,
    metric_name: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 500
):
    """Query scraped metrics with filters"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        conditions = []
        params = {}
        
        if target_id:
            conditions.append("target_id = toUUID(%(target_id)s)")
            params["target_id"] = target_id
        
        if metric_name:
            conditions.append("metric_name = %(metric_name)s")
            params["metric_name"] = metric_name
        
        if start:
            conditions.append("timestamp >= toDateTime(%(start)s)")
            params["start"] = start
        
        if end:
            conditions.append("timestamp <= toDateTime(%(end)s)")
            params["end"] = end
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT 
                toString(timestamp) as timestamp,
                toString(target_id) as target_id,
                target_name,
                metric_name,
                labels,
                value
            FROM scraped_metrics
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT {min(limit, 10000)}
        """
        
        # Build query with string interpolation for parameters
        final_query = query
        for k, v in params.items():
            if isinstance(v, str):
                final_query = final_query.replace(f"%({k})s", f"'{v}'")
            else:
                final_query = final_query.replace(f"%({k})s", str(v))
        
        result = client.client.execute(final_query)
        
        data = []
        for row in result:
            labels = {}
            try:
                if row[4]:
                    labels = json.loads(row[4])
            except:
                pass
            
            data.append({
                "timestamp": row[0],
                "target_id": row[1],
                "target_name": row[2],
                "metric_name": row[3],
                "labels": labels,
                "value": row[5]
            })
        
        return {"data": data, "count": len(data)}
    except Exception as e:
        logger.error(f"Failed to query metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scraped/labels")
async def get_metric_labels(
    target_id: str,
    metric_name: str
):
    """Get unique label keys and values for a metric"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Query to get all unique labels for this metric
        query = f"""
            SELECT 
                labels
            FROM scraped_metrics
            WHERE target_id = toUUID('{target_id}')
              AND metric_name = '{metric_name}'
              AND timestamp > now() - INTERVAL 1 HOUR
            GROUP BY labels
            LIMIT 1000
        """
        
        result = client.client.execute(query)
        
        # Aggregate all unique label keys and their values
        label_values: Dict[str, set] = {}
        
        for row in result:
            try:
                if row[0]:
                    labels = json.loads(row[0])
                    for key, value in labels.items():
                        if key not in label_values:
                            label_values[key] = set()
                        label_values[key].add(value)
            except:
                pass
        
        # Convert sets to sorted lists
        labels_response = {}
        for key, values in label_values.items():
            labels_response[key] = sorted(list(values))
        
        return {"labels": labels_response, "metric_name": metric_name, "target_id": target_id}
    except Exception as e:
        logger.error(f"Failed to get labels: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scraped/series")
async def get_metric_series(
    target_id: str,
    metric_name: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    step: str = "1m",
    labels: Optional[str] = None,  # JSON string of label filters e.g. {"topic": "my-topic"}
    aggregation: str = "avg"  # none, sum, avg, max, min
):
    """Get time series data for charting with optional label filtering and aggregation"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Helper to convert ISO datetime to ClickHouse format with timezone conversion
        def to_clickhouse_datetime(dt_str: str) -> str:
            """Convert various datetime formats to ClickHouse-compatible format (server local time)"""
            if not dt_str:
                return None
            try:
                # Handle ISO format with timezone (2025-12-14T01:10:49.270368Z)
                if 'T' in dt_str:
                    from datetime import timezone
                    import time
                    
                    # Get server's UTC offset dynamically
                    server_offset_seconds = -time.timezone if time.daylight == 0 else -time.altzone
                    server_offset = timedelta(seconds=server_offset_seconds)
                    
                    # Remove Z and replace with +00:00 for parsing
                    clean = dt_str
                    if clean.endswith('Z'):
                        clean = clean[:-1] + '+00:00'
                    
                    # Handle microseconds - keep timezone part after
                    if '.' in clean and '+' in clean:
                        parts = clean.split('.')
                        tz_start = parts[1].find('+') if '+' in parts[1] else parts[1].find('-')
                        if tz_start != -1:
                            clean = parts[0] + parts[1][tz_start:]
                        else:
                            clean = parts[0]
                    elif '.' in clean:
                        clean = clean.split('.')[0]
                    
                    # Parse the datetime
                    dt = datetime.fromisoformat(clean)
                    
                    # Convert to server local time
                    # If datetime has timezone info, convert. Otherwise assume it's already local
                    if dt.tzinfo is not None:
                        # Convert from incoming timezone to UTC, then to local
                        utc_dt = dt.astimezone(timezone.utc)
                        local_dt = utc_dt + server_offset
                        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                return dt_str
            except Exception as e:
                logger.warning(f"Failed to parse datetime {dt_str}: {e}")
                return dt_str
        
        # Default time range: last hour
        if not end:
            end = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            end = to_clickhouse_datetime(end)
            
        if not start:
            start = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        else:
            start = to_clickhouse_datetime(start)
        
        # Map step to ClickHouse interval
        step_map = {
            "15s": "toStartOfFifteenSeconds(timestamp)",
            "1m": "toStartOfMinute(timestamp)",
            "5m": "toStartOfFiveMinutes(timestamp)",
            "15m": "toStartOfFifteenMinutes(timestamp)",
            "1h": "toStartOfHour(timestamp)"
        }
        time_bucket = step_map.get(step, "toStartOfMinute(timestamp)")
        
        # Build label filter conditions
        label_conditions = ""
        if labels:
            try:
                label_filters = json.loads(labels)
                for key, value in label_filters.items():
                    # Escape single quotes in values
                    safe_value = str(value).replace("'", "\\'")
                    label_conditions += f" AND JSONExtractString(labels, '{key}') = '{safe_value}'"
            except json.JSONDecodeError:
                logger.warning(f"Invalid labels JSON: {labels}")
        
        # Determine aggregation function
        agg_func = aggregation.lower() if aggregation else "avg"
        if agg_func not in ("sum", "avg", "max", "min", "none"):
            agg_func = "avg"
        
        if agg_func == "none":
            # No aggregation - return raw values (but still grouped by time)
            agg_select = "avg(value)"
        else:
            agg_select = f"{agg_func}(value)"
        
        query = f"""
            SELECT 
                toString({time_bucket}) as ts,
                {agg_select} as agg_value,
                min(value) as min_value,
                max(value) as max_value
            FROM scraped_metrics
            WHERE target_id = toUUID('{target_id}')
              AND metric_name = '{metric_name}'
              AND timestamp >= toDateTime('{start}')
              AND timestamp <= toDateTime('{end}')
              {label_conditions}
            GROUP BY ts
            ORDER BY ts
        """
        
        result = client.client.execute(query)
        
        data = []
        for row in result:
            data.append({
                "timestamp": row[0],
                "value": row[1],
                "min": row[2],
                "max": row[3]
            })
        
        return {
            "data": data, 
            "metric_name": metric_name, 
            "target_id": target_id,
            "aggregation": agg_func,
            "labels_filter": labels
        }
    except Exception as e:
        logger.error(f"Failed to get series: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/scraped/metrics")
async def list_available_metrics(target_id: Optional[str] = None):
    """List all available metric names"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        params = {}
        where_clause = "1=1"
        
        if target_id:
            where_clause = "target_id = toUUID(%(target_id)s)"
            params["target_id"] = target_id
        
        query = f"""
            SELECT 
                metric_name,
                count() as sample_count,
                max(timestamp) as last_seen
            FROM scraped_metrics
            WHERE {where_clause}
              AND timestamp > now() - INTERVAL 1 DAY
            GROUP BY metric_name
            ORDER BY sample_count DESC
            LIMIT 500
        """
        
        # Build query with string interpolation
        final_query = query
        for k, v in params.items():
            final_query = final_query.replace(f"%({k})s", f"'{v}'")
        
        result = client.client.execute(final_query)
        
        metrics = []
        for row in result:
            metrics.append({
                "name": row[0],
                "sample_count": row[1],
                "last_seen": str(row[2])
            })
        
        return {"metrics": metrics, "count": len(metrics)}
    except Exception as e:
        logger.error(f"Failed to list metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Prometheus Text Parser
# ============================================

def parse_prometheus_text(text: str) -> List[Dict]:
    """Parse Prometheus exposition format text into metrics"""
    metrics = []
    
    for line in text.split('\n'):
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue
        
        try:
            # Parse metric line: metric_name{labels} value [timestamp]
            # Example: http_requests_total{method="get",code="200"} 1234
            
            # Check if there are labels
            if '{' in line:
                match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+([^\s]+)', line)
                if match:
                    name = match.group(1)
                    labels_str = match.group(2)
                    value_str = match.group(3)
                    
                    # Parse labels
                    labels = {}
                    for label_match in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"', labels_str):
                        labels[label_match.group(1)] = label_match.group(2)
                    
                    # Parse value
                    try:
                        value = float(value_str)
                    except:
                        continue
                    
                    metrics.append({
                        "name": name,
                        "labels": labels,
                        "value": value
                    })
            else:
                # No labels
                match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\s+([^\s]+)', line)
                if match:
                    name = match.group(1)
                    value_str = match.group(2)
                    
                    try:
                        value = float(value_str)
                    except:
                        continue
                    
                    metrics.append({
                        "name": name,
                        "labels": {},
                        "value": value
                    })
        except Exception as e:
            logger.debug(f"Failed to parse metric line: {line}, error: {e}")
            continue
    
    return metrics


# ============================================
# Background Scraper
# ============================================

async def scrape_target_by_id(target_id: str):
    """Scrape a single target by ID"""
    client = get_clickhouse_client()
    if not client:
        return
    
    try:
        # Get target details
        query = f"""
            SELECT url, timeout, name, labels FROM metric_targets FINAL
            WHERE id = toUUID('{target_id}') AND enabled = true
        """
        result = client.client.execute(query)
        
        if not result:
            return
        
        url, timeout, name, static_labels_str = result[0]
        
        # Parse static labels
        static_labels = {}
        try:
            if static_labels_str:
                static_labels = json.loads(static_labels_str)
        except:
            pass
        
        await _scrape_url(client, target_id, name, url, timeout, static_labels)
    except Exception as e:
        logger.error(f"Failed to scrape target {target_id}: {e}")


async def _scrape_url(client, target_id: str, target_name: str, url: str, timeout: int, static_labels: Dict):
    """Scrape a URL and store metrics"""
    global _scrape_semaphore
    
    # Initialize semaphore if needed
    if _scrape_semaphore is None:
        _scrape_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)
    
    status = "success"
    error = ""
    metrics_count = 0
    
    # Use semaphore to limit concurrent scrapes
    async with _scrape_semaphore:
        try:
            http_client = await get_http_client()
            response = await http_client.get(url, timeout=timeout)
            
            if response.status_code != 200:
                status = "error"
                error = f"HTTP {response.status_code}"
            else:
                # Parse metrics
                metrics = parse_prometheus_text(response.text)
                metrics_count = len(metrics)
                
                if metrics:
                    # Batch insert metrics
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    values = []
                    
                    for m in metrics:
                        # Merge static labels
                        all_labels = {**static_labels, **m["labels"]}
                        labels_json = json.dumps(all_labels)
                        
                        values.append(f"('{now}', toUUID('{target_id}'), '{target_name}', '{m['name']}', '{labels_json}', {m['value']})")
                    
                    # Insert in batches of 1000
                    for i in range(0, len(values), 1000):
                        batch = values[i:i+1000]
                        insert_query = f"""
                            INSERT INTO scraped_metrics 
                            (timestamp, target_id, target_name, metric_name, labels, value)
                            VALUES {', '.join(batch)}
                        """
                        client.client.execute(insert_query)
    
        except httpx.RequestError as e:
            status = "error"
            error = str(e)
        except Exception as e:
            status = "error"
            error = str(e)
            logger.error(f"Scrape error for {url}: {e}")
    
    # Update target status using INSERT (ReplacingMergeTree will dedupe by updated_at)
    try:
        # First get the existing target data
        fetch_query = f"""
            SELECT name, url, scrape_interval, timeout, labels, enabled, created_at
            FROM metric_targets FINAL
            WHERE id = toUUID('{target_id}')
        """
        existing = client.client.execute(fetch_query)
        
        if existing:
            row = existing[0]
            safe_error = error.replace("'", "''")
            # Insert new row - ReplacingMergeTree will keep latest by updated_at
            insert_query = f"""
                INSERT INTO metric_targets 
                (id, name, url, scrape_interval, timeout, labels, enabled, 
                 last_scrape, last_status, last_error, metrics_count, created_at, updated_at)
                VALUES (
                    toUUID('{target_id}'), '{row[0]}', '{row[1]}', {row[2]}, {row[3]}, 
                    '{row[4] if row[4] else '{}'}', {1 if row[5] else 0},
                    now(), '{status}', '{safe_error}', {metrics_count}, 
                    '{row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else 'now()'}', now()
                )
            """
            client.client.execute(insert_query)
            logger.info(f"Updated target {target_id} status: {status}, metrics: {metrics_count}")
    except Exception as e:
        logger.error(f"Failed to update target status: {e}")


async def run_scraper_loop():
    """Background loop that scrapes all enabled targets"""
    logger.info("Starting metrics scraper loop")
    
    while True:
        try:
            client = get_clickhouse_client()
            if not client:
                await asyncio.sleep(5)
                continue
            
            # Get all enabled targets
            query = """
                SELECT 
                    toString(id) as id,
                    url, timeout, name, labels, scrape_interval,
                    last_scrape
                FROM metric_targets
                FINAL
                WHERE enabled = true
            """
            result = client.client.execute(query)
            
            for row in result:
                target_id, url, timeout, name, labels_str, interval, last_scrape = row
                
                # Check if it's time to scrape
                if last_scrape:
                    elapsed = (datetime.now() - last_scrape).total_seconds()
                    if elapsed < interval:
                        continue
                
                # Parse labels
                static_labels = {}
                try:
                    if labels_str:
                        static_labels = json.loads(labels_str)
                except:
                    pass
                
                # Scrape in background
                asyncio.create_task(_scrape_url(client, target_id, name, url, timeout, static_labels))
            
            await asyncio.sleep(5)  # Check every 5 seconds
        except Exception as e:
            logger.error(f"Scraper loop error: {e}")
            await asyncio.sleep(10)


def start_scraper():
    """Start the background scraper task"""
    global _scraper_task
    if _scraper_task is None or _scraper_task.done():
        _scraper_task = asyncio.create_task(run_scraper_loop())
        logger.info("Metrics scraper started")


def stop_scraper():
    """Stop the background scraper task"""
    global _scraper_task
    if _scraper_task and not _scraper_task.done():
        _scraper_task.cancel()
        logger.info("Metrics scraper stopped")
