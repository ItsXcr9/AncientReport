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
        result = client.query(query)
        
        targets = []
        for row in result.result_rows:
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
        client.command(
            query + " (%(name)s, %(url)s, %(interval)s, %(timeout)s, %(labels)s, %(enabled)s)",
            parameters={
                "name": target.name,
                "url": target.url,
                "interval": target.scrape_interval,
                "timeout": target.timeout,
                "labels": labels_json,
                "enabled": target.enabled
            }
        )
        
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
        result = client.query(fetch_query, parameters={"name": target.name})
        
        if result.result_rows:
            row = result.result_rows[0]
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
        
        query = f"""
            ALTER TABLE metric_targets
            UPDATE {', '.join(updates)}
            WHERE id = toUUID(%(id)s)
        """
        client.command(query, parameters=params)
        
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
        query = "ALTER TABLE metric_targets DELETE WHERE id = toUUID(%(id)s)"
        client.command(query, parameters={"id": target_id})
        
        # Also delete associated metrics
        metrics_query = "ALTER TABLE scraped_metrics DELETE WHERE target_id = toUUID(%(id)s)"
        client.command(metrics_query, parameters={"id": target_id})
        
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
            WHERE id = toUUID(%(id)s)
        """
        result = client.query(query, parameters={"id": target_id})
        
        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Target not found")
        
        row = result.result_rows[0]
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
        query = """
            SELECT url, timeout FROM metric_targets FINAL
            WHERE id = toUUID(%(id)s)
        """
        result = client.query(query, parameters={"id": target_id})
        
        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Target not found")
        
        url, timeout = result.result_rows[0]
        
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
        
        result = client.query(query, parameters=params)
        
        data = []
        for row in result.result_rows:
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


@router.get("/scraped/series")
async def get_metric_series(
    target_id: str,
    metric_name: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    step: str = "1m"
):
    """Get time series data for charting"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Default time range: last hour
        if not end:
            end = datetime.now().isoformat()
        if not start:
            start = (datetime.now() - timedelta(hours=1)).isoformat()
        
        # Map step to ClickHouse interval
        step_map = {
            "15s": "toStartOfFifteenSeconds(timestamp)",
            "1m": "toStartOfMinute(timestamp)",
            "5m": "toStartOfFiveMinutes(timestamp)",
            "15m": "toStartOfFifteenMinutes(timestamp)",
            "1h": "toStartOfHour(timestamp)"
        }
        time_bucket = step_map.get(step, "toStartOfMinute(timestamp)")
        
        query = f"""
            SELECT 
                toString({time_bucket}) as ts,
                avg(value) as avg_value,
                min(value) as min_value,
                max(value) as max_value
            FROM scraped_metrics
            WHERE target_id = toUUID(%(target_id)s)
              AND metric_name = %(metric_name)s
              AND timestamp >= toDateTime(%(start)s)
              AND timestamp <= toDateTime(%(end)s)
            GROUP BY ts
            ORDER BY ts
        """
        
        result = client.query(query, parameters={
            "target_id": target_id,
            "metric_name": metric_name,
            "start": start,
            "end": end
        })
        
        data = []
        for row in result.result_rows:
            data.append({
                "timestamp": row[0],
                "value": row[1],
                "min": row[2],
                "max": row[3]
            })
        
        return {"data": data, "metric_name": metric_name, "target_id": target_id}
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
        
        result = client.query(query, parameters=params)
        
        metrics = []
        for row in result.result_rows:
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
        query = """
            SELECT url, timeout, name, labels FROM metric_targets FINAL
            WHERE id = toUUID(%(id)s) AND enabled = true
        """
        result = client.query(query, parameters={"id": target_id})
        
        if not result.result_rows:
            return
        
        url, timeout, name, static_labels_str = result.result_rows[0]
        
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
    status = "success"
    error = ""
    metrics_count = 0
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            response = await http_client.get(url)
            
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
                        client.command(insert_query)
    
    except httpx.RequestError as e:
        status = "error"
        error = str(e)
    except Exception as e:
        status = "error"
        error = str(e)
        logger.error(f"Scrape error for {url}: {e}")
    
    # Update target status
    try:
        update_query = """
            ALTER TABLE metric_targets
            UPDATE 
                last_scrape = now(),
                last_status = %(status)s,
                last_error = %(error)s,
                metrics_count = %(count)s,
                updated_at = now()
            WHERE id = toUUID(%(id)s)
        """
        client.command(update_query, parameters={
            "id": target_id,
            "status": status,
            "error": error,
            "count": metrics_count
        })
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
            result = client.query(query)
            
            for row in result.result_rows:
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
