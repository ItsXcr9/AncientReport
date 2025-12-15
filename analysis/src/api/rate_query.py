"""
Rate Query API - PromQL-equivalent rate, irate, increase, delta, deriv endpoints

Provides HTTP endpoints for calculating rates and deltas on counter and gauge metrics.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from functions.rate import (
    calculate_rate,
    calculate_irate,
    calculate_increase,
    calculate_delta,
    calculate_deriv
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["query"])


@router.get("/rate")
async def get_rate(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(60, description="Time window in seconds (default: 60)"),
    handle_resets: bool = Query(True, description="Handle counter resets")
):
    """
    Calculate per-second rate with counter reset detection.
    
    Equivalent to PromQL: rate(metric[window])
    
    Returns the per-second average rate of increase over the specified window.
    Handles counter resets (process restarts, container churn) automatically.
    """
    try:
        result = await calculate_rate(
            metric_name=metric,
            hostname=hostname,
            window_seconds=window,
            handle_resets=handle_resets
        )
        return result
    except Exception as e:
        logger.error(f"Rate calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/irate")
async def get_irate(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname")
):
    """
    Calculate instant rate using last two data points.
    
    Equivalent to PromQL: irate(metric[5m])
    
    Uses only the last two samples for calculation.
    More responsive to sudden changes but noisier than rate().
    Best for alerting on sudden spikes.
    """
    try:
        result = await calculate_irate(
            metric_name=metric,
            hostname=hostname
        )
        return result
    except Exception as e:
        logger.error(f"irate calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/increase")
async def get_increase(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(300, description="Time window in seconds (default: 300)")
):
    """
    Calculate total increase over a time window.
    
    Equivalent to PromQL: increase(metric[window])
    
    Returns the absolute increase in value. Handles counter resets.
    Use for questions like "how many requests in the last 5 minutes?"
    """
    try:
        result = await calculate_increase(
            metric_name=metric,
            hostname=hostname,
            window_seconds=window
        )
        return result
    except Exception as e:
        logger.error(f"increase calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/delta")
async def get_delta(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(300, description="Time window in seconds (default: 300)")
):
    """
    Calculate difference between first and last value in window.
    
    Equivalent to PromQL: delta(metric[window])
    
    For gauge metrics (can go up or down).
    Unlike rate/increase, can return negative values.
    """
    try:
        result = await calculate_delta(
            metric_name=metric,
            hostname=hostname,
            window_seconds=window
        )
        return result
    except Exception as e:
        logger.error(f"delta calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deriv")
async def get_deriv(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(300, description="Time window in seconds (default: 300)")
):
    """
    Calculate per-second derivative using linear regression.
    
    Equivalent to PromQL: deriv(metric[window])
    
    Uses linear regression for smoother results than rate().
    Good for trending and capacity planning.
    """
    try:
        result = await calculate_deriv(
            metric_name=metric,
            hostname=hostname,
            window_seconds=window
        )
        return result
    except Exception as e:
        logger.error(f"deriv calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rate_series")
async def get_rate_series(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(3600, description="Time range in seconds (default: 1 hour)"),
    step: int = Query(60, description="Step size in seconds (default: 60)")
):
    """
    Get rate time series for charting.
    
    Returns rate values at each step interval over the window.
    Useful for plotting rate over time.
    """
    from storage.clickhouse_client import get_clickhouse_client
    
    client = get_clickhouse_client()
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Calculate rate at each step using ClickHouse window functions
    query = f"""
        WITH 
            toStartOfInterval(timestamp, INTERVAL {step} SECOND) as bucket,
            argMin(value, timestamp) as first_val,
            argMax(value, timestamp) as last_val,
            min(timestamp) as first_ts,
            max(timestamp) as last_ts
        SELECT
            bucket,
            hostname,
            if(last_val >= first_val,
               (last_val - first_val) / nullIf(dateDiff('second', first_ts, last_ts), 0),
               last_val / nullIf(dateDiff('second', first_ts, last_ts), 0)
            ) as rate
        FROM metrics
        WHERE metric_name = '{metric}'
          AND timestamp >= now() - INTERVAL {window} SECOND
          {hostname_filter}
        GROUP BY bucket, hostname
        ORDER BY bucket ASC
    """
    
    try:
        result = client.client.execute(query)
        
        series = []
        for row in result:
            bucket, host, rate = row
            series.append({
                "timestamp": bucket.isoformat() if bucket else None,
                "hostname": host,
                "rate": rate if rate is not None else 0.0
            })
        
        return {
            "metric": metric,
            "window_seconds": window,
            "step_seconds": step,
            "data": series
        }
        
    except Exception as e:
        logger.error(f"rate_series calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Histogram Quantile Endpoints ===

@router.get("/histogram_quantile")
async def get_histogram_quantile(
    metric: str = Query(..., description="Metric name (histogram base name)"),
    quantile: float = Query(0.99, description="Quantile (0.0 to 1.0, default: 0.99 for p99)"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(300, description="Time window in seconds (default: 300)")
):
    """
    Calculate histogram quantile (percentile).
    
    Equivalent to PromQL: histogram_quantile(quantile, metric)
    
    Common quantiles:
    - 0.5 = p50 (median)
    - 0.9 = p90
    - 0.95 = p95
    - 0.99 = p99
    - 0.999 = p999
    """
    from functions.histogram import histogram_quantile
    
    try:
        result = await histogram_quantile(
            quantile=quantile,
            metric_name=metric,
            hostname=hostname,
            window_seconds=window
        )
        return result
    except Exception as e:
        logger.error(f"histogram_quantile calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quantiles")
async def get_all_quantiles(
    metric: str = Query(..., description="Metric name"),
    hostname: Optional[str] = Query(None, description="Filter by hostname"),
    window: int = Query(300, description="Time window in seconds (default: 300)")
):
    """
    Get common quantiles (p50, p90, p95, p99) in one call.
    
    Efficient way to get multiple percentiles for latency analysis.
    """
    from functions.histogram import get_quantiles
    
    try:
        result = await get_quantiles(
            metric_name=metric,
            hostname=hostname,
            window_seconds=window,
            quantiles=[0.5, 0.9, 0.95, 0.99]
        )
        return result
    except Exception as e:
        logger.error(f"get_quantiles calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
