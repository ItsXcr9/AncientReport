"""
Container Application Monitoring API for AncientReport V3
Endpoints for Kafka, Redis, and PostgreSQL metrics
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
import httpx
import logging

router = APIRouter(prefix="/api/container-apps", tags=["Container Apps Monitoring"])

# ClickHouse configuration
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = os.getenv("CLICKHOUSE_PORT", "8123")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "AncientReport")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

logger = logging.getLogger(__name__)


async def clickhouse_query(query: str) -> List[Dict]:
    """Execute a ClickHouse query and return results as list of dicts."""
    url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/"
    params = {
        "database": CLICKHOUSE_DB,
        "user": CLICKHOUSE_USER,
        "password": CLICKHOUSE_PASSWORD,
        "default_format": "JSONEachRow"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, content=query, timeout=30.0)
            if response.status_code != 200:
                logger.error(f"ClickHouse query failed: {response.text}")
                return []
            
            lines = response.text.strip().split('\n')
            import json
            return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:
        logger.error(f"ClickHouse query error: {e}")
        return []


async def ensure_container_app_tables():
    """Create ClickHouse tables for container apps if they don't exist."""
    
    # Kafka Metrics
    await clickhouse_query("""
        CREATE TABLE IF NOT EXISTS kafka_metrics (
            timestamp DateTime64(3),
            hostname String,
            container_name String,
            container_id String,
            metric_name String,
            value Float64,
            broker_id Nullable(String),
            consumer_group Nullable(String),
            topic Nullable(String),
            partition Nullable(Int32)
        ) ENGINE = MergeTree()
        ORDER BY (hostname, timestamp)
        TTL timestamp + INTERVAL 7 DAY
    """)

    # Redis Metrics
    await clickhouse_query("""
        CREATE TABLE IF NOT EXISTS redis_metrics (
            timestamp DateTime64(3),
            hostname String,
            container_name String,
            container_id String,
            metric_name String,
            value Float64,
            db String
        ) ENGINE = MergeTree()
        ORDER BY (hostname, timestamp)
        TTL timestamp + INTERVAL 7 DAY
    """)

    # PostgreSQL Metrics
    await clickhouse_query("""
        CREATE TABLE IF NOT EXISTS postgres_metrics (
            timestamp DateTime64(3),
            hostname String,
            container_name String,
            container_id String,
            metric_name String,
            value Float64,
            database String
        ) ENGINE = MergeTree()
        ORDER BY (hostname, timestamp)
        TTL timestamp + INTERVAL 7 DAY
    """)

    # NGINX Metrics
    await clickhouse_query("""
        CREATE TABLE IF NOT EXISTS nginx_metrics (
            timestamp DateTime64(3),
            hostname String,
            container_name String,
            container_id String,
            metric_name String,
            value Float64
        ) ENGINE = MergeTree()
        ORDER BY (hostname, timestamp)
        TTL timestamp + INTERVAL 7 DAY
    """)

    # MongoDB Metrics
    await clickhouse_query("""
        CREATE TABLE IF NOT EXISTS mongo_metrics (
            timestamp DateTime64(3),
            hostname String,
            container_name String,
            container_id String,
            metric_name String,
            value Float64
        ) ENGINE = MergeTree()
        ORDER BY (hostname, timestamp)
        TTL timestamp + INTERVAL 7 DAY
    """)

    # ClickHouse Metrics (monitoring ClickHouse itself)
    await clickhouse_query("""
        CREATE TABLE IF NOT EXISTS clickhouse_metrics (
            timestamp DateTime64(3),
            hostname String,
            container_name String,
            container_id String,
            metric_name String,
            value Float64
        ) ENGINE = MergeTree()
        ORDER BY (hostname, timestamp)
        TTL timestamp + INTERVAL 7 DAY
    """)
    
    logger.info("✓ Container application metrics tables initialized")


# ============================================
# Kafka Endpoints
# ============================================

@router.get("/kafka/metrics")
async def get_kafka_metrics(
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    container_name: Optional[str] = Query(None, description="Filter by container name"),
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    start: Optional[str] = Query(None, description="Start time (ISO format)"),
    end: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(1000, description="Max results")
):
    """Get Kafka metrics with optional filtering."""
    where_clauses = ["1=1"]
    
    if hostname:
        where_clauses.append(f"hostname = '{hostname}'")
    if container_name:
        where_clauses.append(f"container_name = '{container_name}'")
    if metric_name:
        where_clauses.append(f"metric_name = '{metric_name}'")
    if start:
        where_clauses.append(f"timestamp >= parseDateTimeBestEffort('{start}')")
    if end:
        where_clauses.append(f"timestamp <= parseDateTimeBestEffort('{end}')")
    
    where_clause = " AND ".join(where_clauses)
    
    query = f"""
        SELECT 
            timestamp,
            hostname,
            broker_id,
            container_name,
            metric_name,
            value,
            consumer_group,
            topic,
            partition
        FROM kafka_metrics
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    
    results = await clickhouse_query(query)
    return {"data": results, "count": len(results)}


@router.get("/kafka/consumer-lag")
async def get_kafka_consumer_lag(
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    consumer_group: Optional[str] = Query(None, description="Filter by consumer group"),
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get current consumer lag by group and topic."""
    where_clauses = ["metric_name = 'consumer_lag'"]
    
    if hostname:
        where_clauses.append(f"hostname = '{hostname}'")
    if consumer_group:
        where_clauses.append(f"consumer_group = '{consumer_group}'")
    if topic:
        where_clauses.append(f"topic = '{topic}'")
    
    where_clause = " AND ".join(where_clauses)
    
    query = f"""
        SELECT 
            hostname,
            container_name,
            consumer_group,
            topic,
            partition,
            argMax(value, timestamp) as current_lag,
            max(timestamp) as last_updated
        FROM kafka_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 5 MINUTE
        GROUP BY hostname, container_name, consumer_group, topic, partition
        ORDER BY current_lag DESC
    """
    
    results = await clickhouse_query(query)
    
    # Calculate totals
    total_lag = sum(r.get("current_lag", 0) for r in results)
    
    return {
        "consumer_groups": results,
        "total_lag": total_lag,
        "lagging_partitions": len([r for r in results if r.get("current_lag", 0) > 0])
    }


@router.get("/kafka/health")
async def get_kafka_health(hostname: Optional[str] = Query(None)):
    """Get overall Kafka cluster health summary."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    # Get latest metrics
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value,
            max(timestamp) as last_updated
        FROM kafka_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 5 MINUTE
          AND metric_name IN (
            'total_consumer_lag', 
            'under_replicated_partitions', 
            'total_partitions',
            'is_controller',
            'disk_usage_bytes'
          )
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    # Aggregate health status
    health = {
        "status": "healthy",
        "issues": [],
        "brokers": {}
    }
    
    for r in results:
        container = r.get("container_name", "unknown")
        metric = r.get("metric_name")
        value = r.get("value", 0)
        
        if container not in health["brokers"]:
            health["brokers"][container] = {}
        
        health["brokers"][container][metric] = value
        
        # Check for issues
        if metric == "under_replicated_partitions" and value > 0:
            health["status"] = "warning"
            health["issues"].append(f"{container}: {int(value)} under-replicated partitions")
        elif metric == "total_consumer_lag" and value > 100000:
            health["status"] = "warning"
            health["issues"].append(f"{container}: High consumer lag ({int(value)})")
    
    return health


# ============================================
# Redis Endpoints
# ============================================

@router.get("/redis/metrics")
async def get_redis_metrics(
    hostname: Optional[str] = Query(None),
    container_name: Optional[str] = Query(None),
    metric_name: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(1000)
):
    """Get Redis metrics with optional filtering."""
    where_clauses = ["1=1"]
    
    if hostname:
        where_clauses.append(f"hostname = '{hostname}'")
    if container_name:
        where_clauses.append(f"container_name = '{container_name}'")
    if metric_name:
        where_clauses.append(f"metric_name = '{metric_name}'")
    if start:
        where_clauses.append(f"timestamp >= parseDateTimeBestEffort('{start}')")
    if end:
        where_clauses.append(f"timestamp <= parseDateTimeBestEffort('{end}')")
    
    where_clause = " AND ".join(where_clauses)
    
    query = f"""
        SELECT timestamp, hostname, container_name, metric_name, value, db
        FROM redis_metrics
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    
    results = await clickhouse_query(query)
    return {"data": results, "count": len(results)}


@router.get("/redis/health")
async def get_redis_health(hostname: Optional[str] = Query(None)):
    """Get Redis health summary with key metrics."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value,
            max(timestamp) as last_updated
        FROM redis_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 5 MINUTE
          AND db = ''
          AND metric_name IN (
            'used_memory', 
            'maxmemory', 
            'memory_usage_percent',
            'hit_rate_percent',
            'evicted_keys',
            'connected_clients',
            'blocked_clients',
            'ops_per_sec',
            'is_master',
            'connected_slaves'
          )
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    # Organize by container
    containers = {}
    for r in results:
        container = r.get("container_name", "unknown")
        if container not in containers:
            containers[container] = {"hostname": r.get("hostname"), "metrics": {}}
        containers[container]["metrics"][r.get("metric_name")] = r.get("value")
    
    # Calculate health status
    health = {"status": "healthy", "issues": [], "instances": containers}
    
    for container, data in containers.items():
        metrics = data.get("metrics", {})
        
        # Check memory usage
        mem_percent = metrics.get("memory_usage_percent", 0)
        if mem_percent > 90:
            health["status"] = "critical"
            health["issues"].append(f"{container}: Memory usage critical ({mem_percent:.1f}%)")
        elif mem_percent > 75:
            health["status"] = "warning" if health["status"] != "critical" else health["status"]
            health["issues"].append(f"{container}: Memory usage high ({mem_percent:.1f}%)")
        
        # Check evictions
        evictions = metrics.get("evicted_keys", 0)
        if evictions > 1000:
            health["status"] = "warning" if health["status"] != "critical" else health["status"]
            health["issues"].append(f"{container}: High eviction rate ({int(evictions)} keys)")
        
        # Check hit rate
        hit_rate = metrics.get("hit_rate_percent", 100)
        if hit_rate < 80:
            health["issues"].append(f"{container}: Low cache hit rate ({hit_rate:.1f}%)")
    
    return health


# ============================================
# PostgreSQL Endpoints
# ============================================

@router.get("/postgres/metrics")
async def get_postgres_metrics(
    hostname: Optional[str] = Query(None),
    container_name: Optional[str] = Query(None),
    database: Optional[str] = Query(None),
    metric_name: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(1000)
):
    """Get PostgreSQL metrics with optional filtering."""
    where_clauses = ["1=1"]
    
    if hostname:
        where_clauses.append(f"hostname = '{hostname}'")
    if container_name:
        where_clauses.append(f"container_name = '{container_name}'")
    if database:
        where_clauses.append(f"database = '{database}'")
    if metric_name:
        where_clauses.append(f"metric_name = '{metric_name}'")
    if start:
        where_clauses.append(f"timestamp >= parseDateTimeBestEffort('{start}')")
    if end:
        where_clauses.append(f"timestamp <= parseDateTimeBestEffort('{end}')")
    
    where_clause = " AND ".join(where_clauses)
    
    query = f"""
        SELECT timestamp, hostname, container_name, database, metric_name, value
        FROM postgres_metrics
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    
    results = await clickhouse_query(query)
    return {"data": results, "count": len(results)}


@router.get("/postgres/connections")
async def get_postgres_connections(hostname: Optional[str] = Query(None)):
    """Get PostgreSQL connection pool status."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value,
            max(timestamp) as last_updated
        FROM postgres_metrics
        WHERE {where_clause}
          AND database = '_global'
          AND timestamp > now() - INTERVAL 5 MINUTE
          AND metric_name IN (
            'connections_total',
            'connections_active',
            'connections_idle',
            'connections_idle_in_transaction',
            'connections_waiting_on_lock',
            'max_connections'
          )
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    # Organize by container
    containers = {}
    for r in results:
        container = r.get("container_name", "unknown")
        if container not in containers:
            containers[container] = {"hostname": r.get("hostname"), "connections": {}}
        containers[container]["connections"][r.get("metric_name")] = int(r.get("value", 0))
    
    # Calculate utilization
    for container, data in containers.items():
        conns = data.get("connections", {})
        total = conns.get("connections_total", 0)
        max_conn = conns.get("max_connections", 100)
        if max_conn > 0:
            data["utilization_percent"] = round((total / max_conn) * 100, 2)
    
    return {"instances": containers}


@router.get("/postgres/health")
async def get_postgres_health(hostname: Optional[str] = Query(None)):
    """Get PostgreSQL health summary."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    # Get global metrics
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value,
            max(timestamp) as last_updated
        FROM postgres_metrics
        WHERE {where_clause}
          AND database = '_global'
          AND timestamp > now() - INTERVAL 5 MINUTE
          AND metric_name IN (
            'connections_total',
            'max_connections',
            'connections_waiting_on_lock',
            'is_replica',
            'replica_lag_seconds',
            'replication_max_lag_bytes',
            'checkpoints_timed',
            'checkpoints_requested'
          )
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    # Get database-level metrics
    db_query = f"""
        SELECT 
            hostname,
            container_name,
            database,
            metric_name,
            argMax(value, timestamp) as value
        FROM postgres_metrics
        WHERE {where_clause}
          AND database != '_global'
          AND timestamp > now() - INTERVAL 5 MINUTE
          AND metric_name IN ('cache_hit_ratio', 'dead_tuple_ratio', 'database_size_bytes')
        GROUP BY hostname, container_name, database, metric_name
    """
    
    db_results = await clickhouse_query(db_query)
    
    # Organize health data
    health = {"status": "healthy", "issues": [], "instances": {}}
    
    for r in results:
        container = r.get("container_name", "unknown")
        if container not in health["instances"]:
            health["instances"][container] = {"hostname": r.get("hostname"), "global": {}, "databases": {}}
        health["instances"][container]["global"][r.get("metric_name")] = r.get("value")
    
    for r in db_results:
        container = r.get("container_name", "unknown")
        db = r.get("database", "")
        if container in health["instances"]:
            if db not in health["instances"][container]["databases"]:
                health["instances"][container]["databases"][db] = {}
            health["instances"][container]["databases"][db][r.get("metric_name")] = r.get("value")
    
    # Check for issues
    for container, data in health["instances"].items():
        global_metrics = data.get("global", {})
        
        # Connection pool utilization
        total = global_metrics.get("connections_total", 0)
        max_conn = global_metrics.get("max_connections", 100)
        if max_conn > 0:
            util = (total / max_conn) * 100
            if util > 90:
                health["status"] = "critical"
                health["issues"].append(f"{container}: Connection pool near full ({util:.1f}%)")
            elif util > 75:
                health["status"] = "warning" if health["status"] != "critical" else health["status"]
                health["issues"].append(f"{container}: Connection pool filling up ({util:.1f}%)")
        
        # Lock waits
        lock_waits = global_metrics.get("connections_waiting_on_lock", 0)
        if lock_waits > 5:
            health["issues"].append(f"{container}: {int(lock_waits)} queries waiting on locks")
        
        # Replication lag
        if global_metrics.get("is_replica", 0) == 1:
            lag = global_metrics.get("replica_lag_seconds", 0)
            if lag > 60:
                health["status"] = "warning" if health["status"] != "critical" else health["status"]
                health["issues"].append(f"{container}: Replica lag {lag:.0f}s")
        
        # Check database-level metrics
        for db, metrics in data.get("databases", {}).items():
            cache_ratio = metrics.get("cache_hit_ratio", 100)
            if cache_ratio < 90:
                health["issues"].append(f"{container}/{db}: Low cache hit ratio ({cache_ratio:.1f}%)")
            
            dead_ratio = metrics.get("dead_tuple_ratio", 0)
            if dead_ratio > 10:
                health["issues"].append(f"{container}/{db}: High dead tuple ratio ({dead_ratio:.1f}%)")
    
    return health


# ============================================
# Detected Containers Endpoint
# ============================================

@router.get("/detected")
async def get_detected_containers(hostname: Optional[str] = Query(None)):
    """List all detected Kafka, Redis, PostgreSQL, NGINX, MongoDB, and ClickHouse containers."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    containers = {"kafka": [], "redis": [], "postgres": [], "nginx": [], "mongo": [], "clickhouse": []}
    
    # Kafka containers
    query = f"""
        SELECT DISTINCT hostname, container_name, container_id
        FROM kafka_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 1 HOUR
    """
    results = await clickhouse_query(query)
    containers["kafka"] = results
    
    # Redis containers
    query = f"""
        SELECT DISTINCT hostname, container_name, container_id
        FROM redis_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 1 HOUR
    """
    results = await clickhouse_query(query)
    containers["redis"] = results
    
    # PostgreSQL containers
    query = f"""
        SELECT DISTINCT hostname, container_name, container_id
        FROM postgres_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 1 HOUR
    """
    results = await clickhouse_query(query)
    containers["postgres"] = results
    
    # NGINX containers
    query = f"""
        SELECT DISTINCT hostname, container_name, container_id
        FROM nginx_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 1 HOUR
    """
    results = await clickhouse_query(query)
    containers["nginx"] = results
    
    # MongoDB containers
    query = f"""
        SELECT DISTINCT hostname, container_name, container_id
        FROM mongo_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 1 HOUR
    """
    results = await clickhouse_query(query)
    containers["mongo"] = results
    
    # ClickHouse containers
    query = f"""
        SELECT DISTINCT hostname, container_name, container_id
        FROM clickhouse_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 1 HOUR
    """
    results = await clickhouse_query(query)
    containers["clickhouse"] = results
    
    total = sum(len(v) for v in containers.values())
    return {"containers": containers, "total": total}


# ============================================
# NGINX Endpoints
# ============================================

@router.get("/nginx/health")
async def get_nginx_health(hostname: Optional[str] = Query(None)):
    """Get NGINX health summary."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value
        FROM nginx_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 5 MINUTE
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    health = {"status": "healthy", "issues": [], "instances": {}}
    
    for r in results:
        container = r.get("container_name", "unknown")
        if container not in health["instances"]:
            health["instances"][container] = {"hostname": r.get("hostname"), "metrics": {}}
        health["instances"][container]["metrics"][r.get("metric_name")] = r.get("value")
    
    # Check for issues
    for container, data in health["instances"].items():
        metrics = data.get("metrics", {})
        
        # High connection count
        active = metrics.get("active_connections", 0)
        if active > 1000:
            health["status"] = "warning"
            health["issues"].append(f"{container}: High active connections ({int(active)})")
        
        # Many waiting connections
        waiting = metrics.get("waiting", 0)
        if waiting > 100:
            health["issues"].append(f"{container}: Many waiting connections ({int(waiting)})")
    
    return health


# ============================================
# MongoDB Endpoints
# ============================================

@router.get("/mongo/health")
async def get_mongo_health(hostname: Optional[str] = Query(None)):
    """Get MongoDB health summary."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value
        FROM mongo_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 5 MINUTE
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    health = {"status": "healthy", "issues": [], "instances": {}}
    
    for r in results:
        container = r.get("container_name", "unknown")
        if container not in health["instances"]:
            health["instances"][container] = {"hostname": r.get("hostname"), "metrics": {}}
        health["instances"][container]["metrics"][r.get("metric_name")] = r.get("value")
    
    # Check for issues
    for container, data in health["instances"].items():
        metrics = data.get("metrics", {})
        
        # Connection pool issues
        current = metrics.get("connections_current", 0)
        available = metrics.get("connections_available", 0)
        if available > 0 and current / (current + available) > 0.9:
            health["status"] = "critical"
            health["issues"].append(f"{container}: Connection pool nearly exhausted")
        
        # Cache pressure
        cache_used = metrics.get("cache_bytes_in_cache", 0)
        cache_max = metrics.get("cache_bytes_max", 0)
        if cache_max > 0:
            util = (cache_used / cache_max) * 100
            if util > 95:
                health["status"] = "warning" if health["status"] != "critical" else health["status"]
                health["issues"].append(f"{container}: Cache pressure ({util:.1f}%)")
        
        # Lock queue
        lock_queue = metrics.get("global_lock_queue", 0)
        if lock_queue > 10:
            health["issues"].append(f"{container}: Lock queue growing ({int(lock_queue)})")
    
    return health


# ============================================
# ClickHouse Endpoints
# ============================================

@router.get("/clickhouse/health")
async def get_clickhouse_health(hostname: Optional[str] = Query(None)):
    """Get ClickHouse health summary."""
    where_clause = f"hostname = '{hostname}'" if hostname else "1=1"
    
    query = f"""
        SELECT 
            hostname,
            container_name,
            metric_name,
            argMax(value, timestamp) as value
        FROM clickhouse_metrics
        WHERE {where_clause}
          AND timestamp > now() - INTERVAL 5 MINUTE
        GROUP BY hostname, container_name, metric_name
    """
    
    results = await clickhouse_query(query)
    
    health = {"status": "healthy", "issues": [], "instances": {}}
    
    for r in results:
        container = r.get("container_name", "unknown")
        if container not in health["instances"]:
            health["instances"][container] = {"hostname": r.get("hostname"), "metrics": {}}
        health["instances"][container]["metrics"][r.get("metric_name")] = r.get("value")
    
    # Check for issues
    for container, data in health["instances"].items():
        metrics = data.get("metrics", {})
        
        # Too many parts
        parts = metrics.get("parts_active", 0)
        if parts > 3000:
            health["status"] = "warning"
            health["issues"].append(f"{container}: High part count ({int(parts)})")
        
        # Merge queue growing
        merge_queue = metrics.get("replicas_queue_size", 0)
        if merge_queue > 50:
            health["issues"].append(f"{container}: Merge queue growing ({int(merge_queue)})")
        
        # Rejected inserts
        rejected = metrics.get("rejected_inserts", 0)
        if rejected > 0:
            health["status"] = "critical"
            health["issues"].append(f"{container}: Rejected inserts ({int(rejected)})")
        
        # Delayed inserts
        delayed = metrics.get("delayed_inserts", 0)
        if delayed > 10:
            health["status"] = "warning" if health["status"] != "critical" else health["status"]
            health["issues"].append(f"{container}: Delayed inserts ({int(delayed)})")
    
    return health
