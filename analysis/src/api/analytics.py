"""
Analytics API - ML Anomaly Detection and Capacity Forecasting
Detects metric anomalies using statistical methods (Z-score, IQR)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import asyncio
import math

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics & ML"])


# ============================================
# Models
# ============================================

class Anomaly(BaseModel):
    id: str
    timestamp: str
    hostname: str
    metric_name: str
    current_value: float
    expected_value: float
    lower_bound: float
    upper_bound: float
    deviation_score: float
    severity: str
    detection_method: str
    is_acknowledged: bool
    created_at: str


class CapacityForecast(BaseModel):
    metric: str
    hostname: str
    current_value: float
    trend: str  # increasing, decreasing, stable
    predicted_value_1h: float
    predicted_value_24h: float
    predicted_value_7d: float
    days_until_critical: Optional[float]
    critical_threshold: Optional[float]


# ============================================
# Anomaly Detection Logic
# ============================================

def calculate_zscore(value: float, mean: float, stddev: float) -> float:
    """Calculate Z-score for a value"""
    if stddev == 0:
        return 0
    return (value - mean) / stddev


def get_severity(zscore: float) -> str:
    """Determine severity based on Z-score"""
    abs_z = abs(zscore)
    if abs_z >= 4:
        return "critical"
    elif abs_z >= 3:
        return "warning"
    else:
        return "info"


async def detect_anomalies_for_metric(hostname: str, metric_name: str, window_hours: int = 24):
    """Detect anomalies for a specific metric using Z-score method"""
    client = get_clickhouse_client()
    if not client:
        return []
    
    try:
        # Get historical stats
        stats_query = f"""
            SELECT 
                avg(value) as mean_val,
                stddevPop(value) as stddev_val,
                min(value) as min_val,
                max(value) as max_val,
                count() as cnt
            FROM metrics
            WHERE hostname = '{hostname}'
              AND metric_name = '{metric_name}'
              AND timestamp >= now() - INTERVAL {window_hours} HOUR
              AND timestamp < now() - INTERVAL 10 MINUTE
        """
        stats = client.client.execute(stats_query)
        
        if not stats or stats[0][4] < 10:  # Need at least 10 samples
            return []
        
        mean_val, stddev_val, min_val, max_val, cnt = stats[0]
        
        if stddev_val is None or stddev_val == 0:
            return []
        
        # Get recent values (last 5 minutes)
        recent_query = f"""
            SELECT value, timestamp
            FROM metrics
            WHERE hostname = '{hostname}'
              AND metric_name = '{metric_name}'
              AND timestamp >= now() - INTERVAL 5 MINUTE
            ORDER BY timestamp DESC
            LIMIT 5
        """
        recent = client.client.execute(recent_query)
        
        anomalies = []
        for row in recent:
            current_val = row[0]
            ts = row[1]
            
            zscore = calculate_zscore(current_val, mean_val, stddev_val)
            
            # Only flag if Z-score > 2.5 (outside 99% of normal distribution)
            if abs(zscore) > 2.5:
                lower_bound = mean_val - (2.5 * stddev_val)
                upper_bound = mean_val + (2.5 * stddev_val)
                severity = get_severity(zscore)
                
                anomalies.append({
                    "hostname": hostname,
                    "metric_name": metric_name,
                    "current_value": current_val,
                    "expected_value": mean_val,
                    "lower_bound": lower_bound,
                    "upper_bound": upper_bound,
                    "deviation_score": zscore,
                    "severity": severity,
                    "detection_method": "zscore",
                    "timestamp": ts
                })
        
        return anomalies
    
    except Exception as e:
        logger.error(f"Anomaly detection error for {hostname}/{metric_name}: {e}")
        return []


async def run_anomaly_detection():
    """Run anomaly detection across all hosts and key metrics"""
    client = get_clickhouse_client()
    if not client:
        return
    
    try:
        # Key metrics to monitor
        key_metrics = [
            "cpu_usage", "cpu_percent", "memory_usage", "memory_percent",
            "disk_usage", "disk_read_bytes", "disk_write_bytes",
            "network_bytes_sent", "network_bytes_recv"
        ]
        
        # Get active hosts
        hosts_query = """
            SELECT DISTINCT hostname
            FROM metrics
            WHERE timestamp >= now() - INTERVAL 10 MINUTE
        """
        hosts = client.client.execute(hosts_query)
        
        all_anomalies = []
        for host_row in hosts:
            hostname = host_row[0]
            
            for metric in key_metrics:
                anomalies = await detect_anomalies_for_metric(hostname, metric)
                all_anomalies.extend(anomalies)
        
        # Store detected anomalies
        for anomaly in all_anomalies:
            try:
                insert_query = f"""
                    INSERT INTO anomalies (
                        hostname, metric_name, current_value, expected_value,
                        lower_bound, upper_bound, deviation_score, severity,
                        detection_method
                    ) VALUES (
                        '{anomaly["hostname"]}',
                        '{anomaly["metric_name"]}',
                        {anomaly["current_value"]},
                        {anomaly["expected_value"]},
                        {anomaly["lower_bound"]},
                        {anomaly["upper_bound"]},
                        {anomaly["deviation_score"]},
                        '{anomaly["severity"]}',
                        '{anomaly["detection_method"]}'
                    )
                """
                client.client.execute(insert_query)
            except Exception as e:
                logger.error(f"Failed to store anomaly: {e}")
        
        if all_anomalies:
            logger.info(f"Detected {len(all_anomalies)} anomalies")
    
    except Exception as e:
        logger.error(f"Anomaly detection run failed: {e}")


# ============================================
# API Endpoints
# ============================================

@router.get("/anomalies", response_model=List[Anomaly])
async def list_anomalies(
    hostname: Optional[str] = None,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    hours: int = 24,
    limit: int = 100
):
    """List detected anomalies"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        conditions = [f"timestamp >= now() - INTERVAL {hours} HOUR"]
        
        if hostname:
            conditions.append(f"hostname = '{hostname}'")
        if severity:
            conditions.append(f"severity = '{severity}'")
        if acknowledged is not None:
            conditions.append(f"is_acknowledged = {1 if acknowledged else 0}")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                toString(id), toString(timestamp), hostname, metric_name,
                current_value, expected_value, lower_bound, upper_bound,
                deviation_score, severity, detection_method, is_acknowledged,
                toString(created_at)
            FROM anomalies
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        rows = client.client.execute(query)
        
        return [
            Anomaly(
                id=row[0],
                timestamp=row[1],
                hostname=row[2],
                metric_name=row[3],
                current_value=row[4],
                expected_value=row[5],
                lower_bound=row[6],
                upper_bound=row[7],
                deviation_score=row[8],
                severity=row[9],
                detection_method=row[10],
                is_acknowledged=bool(row[11]),
                created_at=row[12]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/anomalies/{anomaly_id}/acknowledge")
async def acknowledge_anomaly(anomaly_id: str, user: str = "admin"):
    """Acknowledge an anomaly"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            ALTER TABLE anomalies UPDATE 
            is_acknowledged = 1, acknowledged_by = '{user}', acknowledged_at = now()
            WHERE id = toUUID('{anomaly_id}')
        """
        client.client.execute(query)
        return {"status": "acknowledged", "id": anomaly_id}
    except Exception as e:
        logger.error(f"Failed to acknowledge anomaly: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forecast/{metric}")
async def get_capacity_forecast(
    metric: str,
    hostname: Optional[str] = None,
    critical_threshold: float = 90.0
):
    """Get capacity forecast for a metric"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        host_filter = f"AND hostname = '{hostname}'" if hostname else ""
        
        # Get trend data from last 7 days
        query = f"""
            SELECT 
                toStartOfHour(timestamp) as hour,
                avg(value) as avg_val
            FROM metrics
            WHERE metric_name = '{metric}'
              {host_filter}
              AND timestamp >= now() - INTERVAL 7 DAY
            GROUP BY hour
            ORDER BY hour
        """
        rows = client.client.execute(query)
        
        if len(rows) < 24:  # Need at least 24 hours of data
            raise HTTPException(status_code=400, detail="Insufficient historical data")
        
        values = [r[1] for r in rows]
        current_value = values[-1] if values else 0
        
        # Simple linear regression for trend
        n = len(values)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(xi * xi for xi in x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
        intercept = (sum_y - slope * sum_x) / n
        
        # Predictions
        pred_1h = slope * (n + 1) + intercept
        pred_24h = slope * (n + 24) + intercept
        pred_7d = slope * (n + 24*7) + intercept
        
        # Trend classification
        if slope > 0.5:
            trend = "increasing"
        elif slope < -0.5:
            trend = "decreasing"
        else:
            trend = "stable"
        
        # Days until critical
        days_until_critical = None
        if slope > 0 and current_value < critical_threshold:
            hours_to_critical = (critical_threshold - current_value) / slope
            days_until_critical = hours_to_critical / 24
        
        return CapacityForecast(
            metric=metric,
            hostname=hostname or "all",
            current_value=current_value,
            trend=trend,
            predicted_value_1h=max(0, pred_1h),
            predicted_value_24h=max(0, pred_24h),
            predicted_value_7d=max(0, pred_7d),
            days_until_critical=days_until_critical,
            critical_threshold=critical_threshold
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forecast failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_analytics_stats():
    """Get analytics overview stats"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Count anomalies by severity
        query = """
            SELECT 
                severity,
                count() as cnt,
                countIf(is_acknowledged = 0) as unacknowledged
            FROM anomalies
            WHERE timestamp >= now() - INTERVAL 24 HOUR
            GROUP BY severity
        """
        rows = client.client.execute(query)
        
        by_severity = {row[0]: {"total": row[1], "unacknowledged": row[2]} for row in rows}
        
        return {
            "anomalies_24h": sum(r["total"] for r in by_severity.values()),
            "unacknowledged": sum(r["unacknowledged"] for r in by_severity.values()),
            "by_severity": by_severity
        }
    except Exception as e:
        logger.error(f"Failed to get analytics stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Background Task
# ============================================

async def anomaly_detection_loop():
    """Background loop for continuous anomaly detection"""
    logger.info("Starting anomaly detection loop")
    while True:
        try:
            await run_anomaly_detection()
        except Exception as e:
            logger.error(f"Anomaly detection loop error: {e}")
        await asyncio.sleep(60)  # Run every minute
