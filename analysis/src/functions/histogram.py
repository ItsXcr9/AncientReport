"""
Histogram Query Functions - Calculate quantiles from histogram buckets

Provides histogram_quantile function for calculating p50, p90, p99 etc.
from ClickHouse histogram bucket data.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)


async def histogram_quantile(
    quantile: float,
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 300
) -> Dict[str, Any]:
    """
    Calculate histogram quantile from bucket data.
    
    Equivalent to PromQL: histogram_quantile(quantile, metric_name)
    
    Args:
        quantile: Quantile to calculate (0.0 to 1.0, e.g., 0.99 for p99)
        metric_name: Base name of the histogram metric (without _bucket suffix)
        hostname: Filter by hostname (optional)
        window_seconds: Time window for the calculation
    
    Returns:
        Dict with quantile value and metadata
    """
    client = get_clickhouse_client()
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Query histogram buckets
    # Prometheus histograms have _bucket, _count, _sum suffixes
    query = f"""
        SELECT 
            hostname,
            le,
            max(count) as bucket_count
        FROM histogram_metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {window_seconds} SECOND
          {hostname_filter}
        GROUP BY hostname, le
        ORDER BY hostname, le
    """
    
    try:
        result = client.client.execute(query)
        
        if not result:
            # Fall back to trying to calculate from raw values if no histogram data
            return await _quantile_from_raw(quantile, metric_name, hostname, window_seconds)
        
        # Group by hostname
        buckets_by_host: Dict[str, List[tuple]] = {}
        for row in result:
            host, le, count = row
            if host not in buckets_by_host:
                buckets_by_host[host] = []
            buckets_by_host[host].append((le, count))
        
        # Calculate quantile for each host
        results = []
        for host, buckets in buckets_by_host.items():
            quantile_value = _calculate_histogram_quantile(buckets, quantile)
            results.append({
                "hostname": host,
                "quantile": quantile,
                "value": quantile_value
            })
        
        if hostname and len(results) == 1:
            return results[0]
        elif len(results) > 0:
            avg_value = sum(r["value"] for r in results) / len(results)
            return {
                "quantile": quantile,
                "value": avg_value,
                "by_host": results
            }
        else:
            return {"quantile": quantile, "value": 0.0, "error": "no histogram data"}
            
    except Exception as e:
        logger.error(f"histogram_quantile failed: {e}")
        return {"quantile": quantile, "value": 0.0, "error": str(e)}


def _calculate_histogram_quantile(buckets: List[tuple], quantile: float) -> float:
    """
    Calculate quantile from histogram buckets using linear interpolation.
    
    Buckets should be sorted by 'le' (upper bound).
    Each bucket contains cumulative count of observations <= le.
    """
    if not buckets:
        return 0.0
    
    # Sort by upper bound
    sorted_buckets = sorted(buckets, key=lambda x: x[0])
    
    # Get total count (from +Inf bucket or last bucket)
    total = sorted_buckets[-1][1]
    if total == 0:
        return 0.0
    
    # Find the bucket containing the quantile
    target = quantile * total
    
    prev_bound = 0.0
    prev_count = 0
    
    for le, count in sorted_buckets:
        if count >= target:
            # Quantile is in this bucket
            # Linear interpolation within bucket
            bucket_count = count - prev_count
            if bucket_count <= 0:
                return le
            
            # How far into this bucket is the target?
            fraction = (target - prev_count) / bucket_count
            
            # Interpolate between prev_bound and le
            return prev_bound + (le - prev_bound) * fraction
        
        prev_bound = le
        prev_count = count
    
    # If we get here, return the last bucket's upper bound
    return sorted_buckets[-1][0]


async def _quantile_from_raw(
    quantile: float,
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 300
) -> Dict[str, Any]:
    """
    Calculate quantile directly from raw metric values.
    Fallback when no histogram bucket data is available.
    """
    client = get_clickhouse_client()
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Use ClickHouse's quantile function directly
    query = f"""
        SELECT
            hostname,
            quantile({quantile})(value) as q_value,
            count() as sample_count
        FROM metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {window_seconds} SECOND
          {hostname_filter}
        GROUP BY hostname
    """
    
    try:
        result = client.client.execute(query)
        
        if not result:
            return {"quantile": quantile, "value": 0.0, "error": "no data"}
        
        results = []
        for row in result:
            host, q_value, count = row
            results.append({
                "hostname": host,
                "quantile": quantile,
                "value": q_value,
                "samples": count,
                "source": "raw_values"
            })
        
        if hostname and len(results) == 1:
            return results[0]
        elif len(results) > 0:
            avg_value = sum(r["value"] for r in results) / len(results)
            return {
                "quantile": quantile,
                "value": avg_value,
                "by_host": results,
                "source": "raw_values"
            }
        else:
            return {"quantile": quantile, "value": 0.0, "error": "no data"}
            
    except Exception as e:
        logger.error(f"quantile_from_raw failed: {e}")
        return {"quantile": quantile, "value": 0.0, "error": str(e)}


async def get_quantiles(
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 300,
    quantiles: List[float] = None
) -> Dict[str, Any]:
    """
    Get multiple quantiles at once (p50, p90, p95, p99).
    
    Args:
        metric_name: Metric name
        hostname: Filter by hostname
        window_seconds: Time window
        quantiles: List of quantiles (default: [0.5, 0.9, 0.95, 0.99])
    
    Returns:
        Dict with all requested quantiles
    """
    if quantiles is None:
        quantiles = [0.5, 0.9, 0.95, 0.99]
    
    client = get_clickhouse_client()
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Build quantile expressions
    quantile_exprs = ", ".join([
        f"quantile({q})(value) as p{int(q*100)}"
        for q in quantiles
    ])
    
    query = f"""
        SELECT
            hostname,
            {quantile_exprs},
            count() as sample_count
        FROM metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {window_seconds} SECOND
          {hostname_filter}
        GROUP BY hostname
    """
    
    try:
        result = client.client.execute(query)
        
        if not result:
            return {"quantiles": {f"p{int(q*100)}": 0.0 for q in quantiles}, "error": "no data"}
        
        # Process first row (single host or aggregated)
        row = result[0]
        host = row[0]
        
        quantile_values = {}
        for i, q in enumerate(quantiles):
            quantile_values[f"p{int(q*100)}"] = row[i + 1]
        
        return {
            "hostname": host,
            "quantiles": quantile_values,
            "samples": row[-1],
            "window_seconds": window_seconds
        }
        
    except Exception as e:
        logger.error(f"get_quantiles failed: {e}")
        return {"quantiles": {}, "error": str(e)}
