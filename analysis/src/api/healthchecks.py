"""
API endpoint for Docker container healthcheck status from ClickHouse
"""
import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Global ClickHouse client (will be set by main.py)
clickhouse_client = None

def set_clickhouse_client(client):
    """Set the global ClickHouse client"""
    global clickhouse_client
    clickhouse_client = client

@router.get("/healthchecks", response_model=List[Dict[str, Any]])
async def get_container_healthchecks(hostname: Optional[str] = Query(None)):
    """
    Get healthcheck status for all containers that have healthchecks configured.
    Returns only containers that have a healthcheck defined.
    Data is fetched from ClickHouse database where agents store container stats.
    
    Args:
        hostname: Optional filter to get healthchecks for a specific server
    """
    global clickhouse_client
    
    if clickhouse_client is None:
        # Fallback: create client if not set
        from storage.clickhouse_client import ClickHouseClient
        clickhouse_client = ClickHouseClient(
            host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            database=os.getenv("CLICKHOUSE_DB", "AncientReport"),
            user=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", "")
        )
    
    try:
        # Get the latest healthcheck status for each container from ClickHouse
        # Filter containers that have healthchecks BEFORE aggregation
        query = """
        SELECT 
            container_id,
            argMax(container_name, timestamp) as name,
            argMax(health_status, timestamp) as health_status,
            argMax(health_test, timestamp) as health_test,
            argMax(failing_streak, timestamp) as failing_streak,
            argMax(last_health_log, timestamp) as last_health_log,
            argMax(hostname, timestamp) as hostname,
            max(timestamp) as last_seen
        FROM (
            SELECT *
            FROM docker_containers
            WHERE timestamp > now() - INTERVAL 24 HOUR
              AND container_id != ''
              AND container_id IS NOT NULL
              AND health_status != 'none'
              AND health_status != ''
        """
        
        # Add hostname filter if provided
        if hostname:
            query += f"\n              AND hostname = '{hostname}'"
        
        query += """
        )
        GROUP BY container_id
        HAVING max(timestamp) > now() - INTERVAL 2 HOUR
        ORDER BY last_seen DESC
        """
        
        logger.info(f"Fetching healthchecks from ClickHouse{f' for hostname: {hostname}' if hostname else ''}")
        results = await clickhouse_client.query(query)
        logger.info(f"Query returned {len(results)} containers with healthchecks")
        
        containers = []
        for row in results:
            container_id = row[0] if row[0] else ""
            
            # Skip empty IDs
            if not container_id:
                continue
            
            container_name_raw = row[1] if row[1] else ""
            health_status = row[2] if row[2] else "none"
            health_test = row[3] if row[3] else ""
            failing_streak = int(row[4]) if row[4] is not None else 0
            last_health_log = row[5] if row[5] else ""
            container_hostname = row[6] if row[6] else "unknown"
            
            # Clean container name - remove leading slash if present
            container_name = container_name_raw.lstrip('/') if container_name_raw else ""
            
            # If no name, use container ID as the name
            if not container_name:
                container_name = container_id[:12]
            
            # Only include containers with actual healthchecks (status not 'none')
            if health_status == "none" or health_status == "":
                continue
            
            containers.append({
                "id": container_id,
                "name": container_name,
                "health_status": health_status,  # healthy, unhealthy, starting
                "health_test": health_test,
                "failing_streak": failing_streak,
                "last_log": last_health_log,
                "hostname": container_hostname
            })
        
        logger.info(f"Returning {len(containers)} containers with healthchecks")
        return containers
        
    except Exception as e:
        logger.error(f"Failed to fetch healthcheck status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
