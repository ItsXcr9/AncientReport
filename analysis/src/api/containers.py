from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)

# Global ClickHouse client (will be set by main.py)
clickhouse_client = None

def set_clickhouse_client(client):
    """Set the global ClickHouse client"""
    global clickhouse_client
    clickhouse_client = client

@router.get("/current", response_model=List[Dict[str, Any]])
async def get_current_containers():
    """
    Get the latest stats for all containers (running and stopped)
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
        # First, get the latest record for each container_id
        # Then we'll deduplicate by container_name to show only the most recent instance
        query = """
        SELECT 
            container_id,
            argMax(container_name, timestamp) as name,
            argMax(image, timestamp) as image,
            argMax(status, timestamp) as status,
            argMax(cpu_percent, timestamp) as cpu_percent,
            argMax(memory_usage, timestamp) as memory_usage,
            argMax(memory_limit, timestamp) as memory_limit,
            argMax(memory_percent, timestamp) as memory_percent,
            argMax(network_rx_bytes, timestamp) as network_rx_bytes,
            argMax(network_tx_bytes, timestamp) as network_tx_bytes,
            argMax(block_read_bytes, timestamp) as block_read_bytes,
            argMax(block_write_bytes, timestamp) as block_write_bytes,
            argMax(uptime_seconds, timestamp) as uptime_seconds,
            argMax(restart_count, timestamp) as restart_count,
            argMax(created_at, timestamp) as created_at,
            max(timestamp) as last_seen,
            argMax(hostname, timestamp) as hostname
        FROM docker_containers
        WHERE timestamp > now() - INTERVAL 24 HOUR
          AND container_id != ''
          AND container_id IS NOT NULL
        GROUP BY container_id
        HAVING max(timestamp) > now() - INTERVAL 24 HOUR
        ORDER BY last_seen DESC
        """
        
        logger.info("Fetching containers from docker_containers table...")
        # Use async query method
        results = await clickhouse_client.query(query)
        logger.info(f"Query returned {len(results)} rows before deduplication")
        
        containers = []
        seen_names = set()  # Track container names we've already added
        
        # Since results are sorted by last_seen DESC, the first occurrence of each name is the newest
        for row in results:
            container_id = row[0] if row[0] else ""
            
            # Skip empty IDs
            if not container_id:
                continue
            
            container_name_raw = row[1] if row[1] else ""
            image = row[2] if row[2] else ""
            last_seen_str = str(row[15]) if row[15] else ""
            hostname = row[16] if row[16] else "unknown"
            
            # Clean container name - remove leading slash if present
            container_name = container_name_raw.lstrip('/') if container_name_raw else ""
            
            # If no name, use container ID as the name
            if not container_name:
                container_name = container_id[:12]
            
            # Normalize name for comparison (lowercase, strip whitespace)
            normalized_name = container_name.lower().strip()
            
            # Skip if we've already seen this container name (first occurrence is newest)
            if normalized_name in seen_names:
                logger.debug(f"Skipping duplicate container name: '{container_name}'")
                continue
            
            # Mark this name as seen
            seen_names.add(normalized_name)
            
            # Build and add container data
            containers.append({
                "id": container_id,
                "name": container_name,
                "image": image,
                "status": row[3] if row[3] else "unknown",
                "cpu_percent": float(row[4]) if row[4] is not None else 0.0,
                "memory_usage": int(row[5]) if row[5] is not None else 0,
                "memory_limit": int(row[6]) if row[6] is not None else 0,
                "memory_percent": float(row[7]) if row[7] is not None else 0.0,
                "network_rx_bytes": int(row[8]) if row[8] is not None else 0,
                "network_tx_bytes": int(row[9]) if row[9] is not None else 0,
                "block_read_bytes": int(row[10]) if row[10] is not None else 0,
                "block_write_bytes": int(row[11]) if row[11] is not None else 0,
                "uptime_seconds": int(row[12]) if row[12] is not None else 0,
                "restart_count": int(row[13]) if row[13] is not None else 0,
                "created_at": str(row[14]) if row[14] else "",
                "created_at": str(row[14]) if row[14] else "",
                "last_seen": last_seen_str,
                "hostname": hostname
            })
        
        # Sort by status (running first) and then by name
        containers.sort(key=lambda x: (
            0 if x['status'] == 'running' else 1,
            x['name'].lower()
        ))
        
        logger.info(f"Returning {len(containers)} unique containers (deduplicated by name from {len(results)} total rows)")
        return containers
        
    except Exception as e:
        logger.error(f"Failed to fetch container stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
