"""
Rate Calculation Functions - PromQL-equivalent rate(), irate(), increase(), delta()

Provides counter reset detection and proper rate calculation for time-series metrics.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)


class CounterStateManager:
    """
    Manages counter state for reset detection.
    
    Counters always increase until they reset (process restart, container churn).
    This class tracks the last known value to detect resets and calculate
    accurate rates across reset boundaries.
    """
    
    def __init__(self, client=None):
        self.client = client or get_clickhouse_client()
        self._state_cache: Dict[str, Tuple[float, datetime, int]] = {}  # (value, ts, reset_count)
    
    def _make_key(self, hostname: str, metric_name: str) -> str:
        return f"{hostname}:{metric_name}"
    
    async def get_state(self, hostname: str, metric_name: str) -> Optional[Tuple[float, datetime, int]]:
        """Get last known counter state (value, timestamp, reset_count)"""
        key = self._make_key(hostname, metric_name)
        
        # Check cache first
        if key in self._state_cache:
            return self._state_cache[key]
        
        # Load from ClickHouse
        try:
            query = f"""
                SELECT last_value, last_timestamp, reset_count
                FROM counter_state FINAL
                WHERE hostname = '{hostname}' AND metric_name = '{metric_name}'
            """
            result = self.client.client.execute(query)
            if result:
                state = (result[0][0], result[0][1], result[0][2])
                self._state_cache[key] = state
                return state
        except Exception as e:
            logger.debug(f"Could not load counter state: {e}")
        
        return None
    
    async def update_state(self, hostname: str, metric_name: str, value: float, 
                          timestamp: datetime, reset_detected: bool = False):
        """Update counter state"""
        key = self._make_key(hostname, metric_name)
        
        current = self._state_cache.get(key)
        reset_count = (current[2] + 1) if (current and reset_detected) else (current[2] if current else 0)
        
        self._state_cache[key] = (value, timestamp, reset_count)
        
        # Persist to ClickHouse
        try:
            query = f"""
                INSERT INTO counter_state (hostname, metric_name, last_value, last_timestamp, reset_count, updated_at)
                VALUES ('{hostname}', '{metric_name}', {value}, '{timestamp.strftime('%Y-%m-%d %H:%M:%S')}', {reset_count}, now())
            """
            self.client.client.execute(query)
        except Exception as e:
            logger.warning(f"Could not persist counter state: {e}")
    
    def detect_reset(self, old_value: float, new_value: float) -> bool:
        """Detect if a counter reset occurred"""
        # Counter reset = new value is less than old value
        return new_value < old_value


# Global counter state manager
_counter_state_manager: Optional[CounterStateManager] = None


def get_counter_state_manager() -> CounterStateManager:
    """Get or create the global counter state manager"""
    global _counter_state_manager
    if _counter_state_manager is None:
        _counter_state_manager = CounterStateManager()
    return _counter_state_manager


async def calculate_rate(
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 60,
    handle_resets: bool = True
) -> Dict[str, Any]:
    """
    Calculate per-second rate with counter reset detection.
    
    Equivalent to PromQL rate() function.
    
    Algorithm:
    1. Get data points within the window
    2. If value decreased -> counter reset occurred
    3. On reset: calculate rate from reset point only
    4. Otherwise: (last - first) / time_delta
    
    Args:
        metric_name: Name of the counter metric
        hostname: Filter by hostname (optional, aggregates all if None)
        window_seconds: Time window for rate calculation
        handle_resets: Whether to detect and handle counter resets
    
    Returns:
        Dict with rate value and metadata
    """
    client = get_clickhouse_client()
    state_mgr = get_counter_state_manager()
    
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Get first and last values in the window
    query = f"""
        SELECT 
            hostname,
            argMin(value, timestamp) as first_value,
            min(timestamp) as first_ts,
            argMax(value, timestamp) as last_value,
            max(timestamp) as last_ts,
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
            return {"rate": 0.0, "error": "no data", "samples": 0}
        
        rates = []
        for row in result:
            host, first_val, first_ts, last_val, last_ts, sample_count = row
            
            time_delta = (last_ts - first_ts).total_seconds()
            if time_delta <= 0:
                continue
            
            # Check for counter reset
            reset_detected = False
            if handle_resets:
                # Get previous state
                prev_state = await state_mgr.get_state(host, metric_name)
                if prev_state and first_val < prev_state[0]:
                    reset_detected = True
                    logger.info(f"Counter reset detected for {metric_name}@{host}: {prev_state[0]} -> {first_val}")
                
                # Also check within the window for mid-window resets
                # This is simplified - for full accuracy, we'd need to iterate all points
                if last_val < first_val:
                    reset_detected = True
                    # On reset mid-window, use rate from reset point
                    rate = last_val / time_delta
                else:
                    rate = (last_val - first_val) / time_delta
                
                # Update state
                await state_mgr.update_state(host, metric_name, last_val, last_ts, reset_detected)
            else:
                rate = (last_val - first_val) / time_delta
            
            rates.append({
                "hostname": host,
                "rate": rate,
                "first_value": first_val,
                "last_value": last_val,
                "time_delta_seconds": time_delta,
                "samples": sample_count,
                "reset_detected": reset_detected
            })
        
        if hostname and len(rates) == 1:
            return rates[0]
        elif not hostname and len(rates) > 0:
            # Aggregate across hosts
            total_rate = sum(r["rate"] for r in rates)
            return {
                "rate": total_rate,
                "by_host": rates,
                "hosts": len(rates)
            }
        else:
            return {"rate": 0.0, "error": "no matching data", "samples": 0}
            
    except Exception as e:
        logger.error(f"Rate calculation failed: {e}")
        return {"rate": 0.0, "error": str(e)}


async def calculate_irate(
    metric_name: str,
    hostname: str = None
) -> Dict[str, Any]:
    """
    Calculate instant rate using last two data points.
    
    Equivalent to PromQL irate() function.
    More responsive to sudden changes but noisier.
    """
    client = get_clickhouse_client()
    
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Get last 2 data points
    query = f"""
        SELECT timestamp, value, hostname
        FROM metrics
        WHERE metric_name = '{metric_name}'
          {hostname_filter}
        ORDER BY timestamp DESC
        LIMIT 2
    """
    
    try:
        result = client.client.execute(query)
        
        if len(result) < 2:
            return {"irate": 0.0, "error": "insufficient data points"}
        
        (t2, v2, h2), (t1, v1, h1) = result
        time_delta = (t2 - t1).total_seconds()
        
        if time_delta <= 0:
            return {"irate": 0.0, "error": "invalid time delta"}
        
        # Counter reset detection
        if v2 < v1:
            # Reset occurred - rate from zero
            irate = v2 / time_delta
            reset_detected = True
        else:
            irate = (v2 - v1) / time_delta
            reset_detected = False
        
        return {
            "irate": irate,
            "hostname": h2,
            "last_value": v2,
            "prev_value": v1,
            "time_delta_seconds": time_delta,
            "reset_detected": reset_detected
        }
        
    except Exception as e:
        logger.error(f"irate calculation failed: {e}")
        return {"irate": 0.0, "error": str(e)}


async def calculate_increase(
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 300
) -> Dict[str, Any]:
    """
    Calculate total increase over a time window.
    
    Equivalent to PromQL increase() function.
    Handles counter resets by not reporting negative increases.
    """
    client = get_clickhouse_client()
    
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    query = f"""
        SELECT 
            hostname,
            argMin(value, timestamp) as first_value,
            argMax(value, timestamp) as last_value,
            min(timestamp) as first_ts,
            max(timestamp) as last_ts
        FROM metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {window_seconds} SECOND
          {hostname_filter}
        GROUP BY hostname
    """
    
    try:
        result = client.client.execute(query)
        
        if not result:
            return {"increase": 0.0, "error": "no data"}
        
        increases = []
        for row in result:
            host, first_val, last_val, first_ts, last_ts = row
            
            if last_val >= first_val:
                increase = last_val - first_val
                reset_detected = False
            else:
                # Reset occurred - count from reset point
                increase = last_val  # Increase since reset
                reset_detected = True
            
            increases.append({
                "hostname": host,
                "increase": increase,
                "reset_detected": reset_detected,
                "window_seconds": (last_ts - first_ts).total_seconds()
            })
        
        if hostname and len(increases) == 1:
            return increases[0]
        elif len(increases) > 0:
            total = sum(i["increase"] for i in increases)
            return {
                "increase": total,
                "by_host": increases
            }
        else:
            return {"increase": 0.0}
            
    except Exception as e:
        logger.error(f"increase calculation failed: {e}")
        return {"increase": 0.0, "error": str(e)}


async def calculate_delta(
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 300
) -> Dict[str, Any]:
    """
    Calculate difference between first and last value (for gauges).
    
    Equivalent to PromQL delta() function.
    Unlike rate/increase, this can return negative values (for gauges).
    """
    client = get_clickhouse_client()
    
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    query = f"""
        SELECT 
            hostname,
            argMin(value, timestamp) as first_value,
            argMax(value, timestamp) as last_value
        FROM metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {window_seconds} SECOND
          {hostname_filter}
        GROUP BY hostname
    """
    
    try:
        result = client.client.execute(query)
        
        if not result:
            return {"delta": 0.0, "error": "no data"}
        
        deltas = []
        for row in result:
            host, first_val, last_val = row
            deltas.append({
                "hostname": host,
                "delta": last_val - first_val,
                "first_value": first_val,
                "last_value": last_val
            })
        
        if hostname and len(deltas) == 1:
            return deltas[0]
        elif len(deltas) > 0:
            total = sum(d["delta"] for d in deltas)
            return {
                "delta": total,
                "by_host": deltas
            }
        else:
            return {"delta": 0.0}
            
    except Exception as e:
        logger.error(f"delta calculation failed: {e}")
        return {"delta": 0.0, "error": str(e)}


async def calculate_deriv(
    metric_name: str,
    hostname: str = None,
    window_seconds: int = 300
) -> Dict[str, Any]:
    """
    Calculate per-second derivative using linear regression.
    
    Equivalent to PromQL deriv() function.
    Uses linear regression for smoother results than rate().
    """
    client = get_clickhouse_client()
    
    hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
    
    # Use ClickHouse's linear regression functions
    query = f"""
        SELECT 
            hostname,
            count() as n,
            simpleLinearRegression(toUnixTimestamp(timestamp), value).1 as slope,
            simpleLinearRegression(toUnixTimestamp(timestamp), value).2 as intercept
        FROM metrics
        WHERE metric_name = '{metric_name}'
          AND timestamp >= now() - INTERVAL {window_seconds} SECOND
          {hostname_filter}
        GROUP BY hostname
        HAVING n >= 2
    """
    
    try:
        result = client.client.execute(query)
        
        if not result:
            return {"deriv": 0.0, "error": "insufficient data"}
        
        derivs = []
        for row in result:
            host, n, slope, intercept = row
            derivs.append({
                "hostname": host,
                "deriv": slope,  # Slope is the per-second rate of change
                "samples": n
            })
        
        if hostname and len(derivs) == 1:
            return derivs[0]
        elif len(derivs) > 0:
            # Average derivative across hosts
            avg_deriv = sum(d["deriv"] for d in derivs) / len(derivs)
            return {
                "deriv": avg_deriv,
                "by_host": derivs
            }
        else:
            return {"deriv": 0.0}
            
    except Exception as e:
        logger.error(f"deriv calculation failed: {e}")
        return {"deriv": 0.0, "error": str(e)}
