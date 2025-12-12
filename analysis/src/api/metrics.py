"""
API endpoints for system metrics history (CPU, Memory, Disk, Network)
Supports time-range querying from ClickHouse
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import os

from utils.timezone import now, from_iso

# Global instances (will be set by main.py)
clickhouse_client = None

router = APIRouter()
logger = logging.getLogger(__name__)

def set_clickhouse_client(client):
    """Set the global ClickHouse client"""
    global clickhouse_client
    clickhouse_client = client

async def query_metric_history(metric_name: str, start: datetime, end: datetime, hostname: str = None) -> List[Dict]:
    """
    Generic function to query metric history from ClickHouse.
    Returns list of {timestamp, value} points.
    """
    if not clickhouse_client:
        raise HTTPException(status_code=503, detail="Database connection not initialized")

    try:
        # Convert timestamps to suitable format for ClickHouse
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')
        
        # Determine aggregation interval based on time range duration
        duration_hours = (end - start).total_seconds() / 3600
        
        # Dynamic aggregation
        if duration_hours <= 2:
            interval = "1 minute"
        elif duration_hours <= 12:
            interval = "5 minute"
        elif duration_hours <= 24:
            interval = "15 minute"
        else:
            interval = "1 hour"
            
        # Base query
        query = f"""
        SELECT 
            toStartOfInterval(timestamp, INTERVAL {interval}) as time_bucket,
            avg(value) as avg_value
        FROM metrics
        WHERE timestamp >= '{start_str}' AND timestamp <= '{end_str}'
          AND metric_name = '{metric_name}'
        """
        
        # Add hostname filter
        if hostname and hostname.lower() != "all":
            query += f" AND hostname = '{hostname}'"
            
        # Group and order
        query += f"""
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """
        
        logger.debug(f"Querying metrics {metric_name} ({start_str} to {end_str}): {query}")
        
        result = await clickhouse_client.query_df(query)
        points = []
        
        if result and result.get('data'):
            for row in result['data']:
                points.append({
                    "timestamp": row[0],
                    "value": float(row[1])
                })
                
        return points
        
    except Exception as e:
        logger.error(f"Failed to query metrics history for {metric_name}: {e}")
        return []

@router.get("/cpu", response_model=List[Dict[str, Any]])
async def get_cpu_metrics(
    start: str = Query(..., description="Start timestamp (ISO)"),
    end: str = Query(..., description="End timestamp (ISO)"),
    hostname: Optional[str] = Query(None, description="Hostname filter")
):
    """Get CPU usage history"""
    try:
        start_dt = from_iso(start)
        end_dt = from_iso(end)
        
        # For CPU, we query cpu_percent or system_cpu_percent
        # Using 'cpu_usage_percent' as primary metric (based on ingestion logs)
        return await query_metric_history("cpu_usage_percent", start_dt, end_dt, hostname)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {e}")
    except Exception as e:
        logger.error(f"Error fetching CPU metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/memory", response_model=List[Dict[str, Any]])
async def get_memory_metrics(
    start: str = Query(..., description="Start timestamp (ISO)"),
    end: str = Query(..., description="End timestamp (ISO)"),
    hostname: Optional[str] = Query(None, description="Hostname filter")
):
    """Get Memory usage history"""
    try:
        start_dt = from_iso(start)
        end_dt = from_iso(end)
        
        return await query_metric_history("memory_used_percent", start_dt, end_dt, hostname)
    except Exception as e:
        logger.error(f"Error fetching Memory metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/disk_io", response_model=List[Dict[str, Any]])
async def get_disk_io_metrics(
    start: str = Query(..., description="Start timestamp (ISO)"),
    end: str = Query(..., description="End timestamp (ISO)"),
    hostname: Optional[str] = Query(None, description="Hostname filter")
):
    """Get Disk I/O history (combined read+write MB/s for simplicity in chart)"""
    try:
        start_dt = from_iso(start)
        end_dt = from_iso(end)
        
        if not clickhouse_client:
             raise HTTPException(status_code=503, detail="Database connection not initialized")
             
        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Similar aggregation logic
        duration_hours = (end_dt - start_dt).total_seconds() / 3600
        if duration_hours <= 2: interval = "1 minute"
        elif duration_hours <= 12: interval = "5 minute"
        elif duration_hours <= 24: interval = "15 minute"
        else: interval = "1 hour"

        # Querying sum of both read and write bytes
        query = f"""
        SELECT 
            toStartOfInterval(timestamp, INTERVAL {interval}) as time_bucket,
            (avg(value) / 1024 / 1024) as avg_mb
        FROM metrics
        WHERE timestamp >= '{start_str}' AND timestamp <= '{end_str}'
          AND metric_name IN ('disk_read_bytes', 'disk_write_bytes')
        """
        if hostname and hostname.lower() != "all":
             query += f" AND hostname = '{hostname}'"
             
        query += f" GROUP BY time_bucket ORDER BY time_bucket ASC"
        
        result = await clickhouse_client.query_df(query)
        points = []
        if result and result.get('data'):
            for row in result['data']:
                points.append({"timestamp": row[0], "value": float(row[1])})
        return points

    except Exception as e:
        logger.error(f"Error fetching Disk I/O metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/network", response_model=List[Dict[str, Any]])
async def get_network_metrics(
    start: str = Query(..., description="Start timestamp (ISO)"),
    end: str = Query(..., description="End timestamp (ISO)"),
    hostname: Optional[str] = Query(None, description="Hostname filter")
):
    """Get Network Traffic history (combined Rx+Tx MB/s)"""
    try:
        start_dt = from_iso(start)
        end_dt = from_iso(end)
        
        if not clickhouse_client:
             raise HTTPException(status_code=503, detail="Database connection not initialized")
             
        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        duration_hours = (end_dt - start_dt).total_seconds() / 3600
        if duration_hours <= 2: interval = "1 minute"
        elif duration_hours <= 12: interval = "5 minute"
        elif duration_hours <= 24: interval = "15 minute"
        else: interval = "1 hour"

        # combine network_rx_bytes + network_tx_bytes
        query = f"""
        SELECT 
            toStartOfInterval(timestamp, INTERVAL {interval}) as time_bucket,
            (avg(value) / 1024 / 1024) as avg_mb
        FROM metrics
        WHERE timestamp >= '{start_str}' AND timestamp <= '{end_str}'
          AND metric_name IN ('network_rx_bytes', 'network_tx_bytes')
        """
        if hostname and hostname.lower() != "all":
             query += f" AND hostname = '{hostname}'"
        
        query += f" GROUP BY time_bucket ORDER BY time_bucket ASC"
        
        result = await clickhouse_client.query_df(query)
        points = []
        if result and result.get('data'):
            for row in result['data']:
                points.append({"timestamp": row[0], "value": float(row[1])})
        return points

    except Exception as e:
        logger.error(f"Error fetching Network metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
