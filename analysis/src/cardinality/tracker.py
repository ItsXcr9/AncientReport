"""
Cardinality Control - Prevent series explosions

Tracks and enforces cardinality limits to prevent unbounded series growth.
High cardinality is the #1 killer of monitoring systems at scale.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Tuple
from collections import defaultdict

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)


# Default configuration for label handling
LABEL_DENYLIST = {
    # These labels cause cardinality explosions
    'request_id',
    'trace_id',
    'span_id',
    'uuid',
    'session_id',
    'correlation_id',
    'transaction_id',
    'message_id',
    'user_id',  # Consider sampling instead
    'ip',
    'client_ip',
    'source_ip',
}

LABEL_ALLOWLIST = {
    # These labels are always safe
    'hostname',
    'instance',
    'job',
    'service',
    'env',
    'environment',
    'container_name',
    'container_id',  # Only 12 chars, bounded
    'namespace',
    'pod',
    'node',
}


class CardinalityTracker:
    """
    Track and enforce cardinality limits for metrics.
    
    Cardinality = number of unique time series
    A series is defined by: metric_name + all labels
    
    Limits can be set at three levels:
    - Global: total series across all hosts
    - Per-host: series per hostname
    - Per-metric: series per metric name
    """
    
    def __init__(self, client=None):
        self.client = client or get_clickhouse_client()
        
        # Series tracking: key -> last_seen_timestamp
        self.series_cache: Dict[str, datetime] = {}
        
        # Per-host and per-metric counts
        self.host_series_count: Dict[str, int] = defaultdict(int)
        self.metric_series_count: Dict[str, int] = defaultdict(int)
        
        # Limits (loaded from DB) - reduced to prevent memory bloat
        # At ~500 bytes per entry, 100k entries = ~50MB max
        self.limits = {
            'global': 100_000,      # Reduced from 1M to 100k
            'hostname': 10_000,     # Reduced from 50k to 10k
            'metric': 2_000,        # Reduced from 10k to 2k
        }
        
        # Metrics for observability
        self.metrics = {
            'total_series': 0,
            'dropped_total': 0,
            'dropped_by_host': defaultdict(int),
            'dropped_by_metric': defaultdict(int),
            'limit_breaches': 0,
        }
        
        # Actions
        self.actions = {
            'global': 'alert',
            'hostname': 'drop',
            'metric': 'sample',
        }
    
    async def load_limits(self):
        """Load cardinality limits from ClickHouse"""
        try:
            query = """
                SELECT scope, scope_value, max_series, action
                FROM cardinality_limits FINAL
            """
            result = self.client.client.execute(query)
            
            for scope, scope_value, max_series, action in result:
                if scope_value == '*':
                    self.limits[scope] = max_series
                    self.actions[scope] = action
                else:
                    # Specific host or metric limit
                    self.limits[f"{scope}:{scope_value}"] = max_series
                    self.actions[f"{scope}:{scope_value}"] = action
            
            logger.info(f"Loaded cardinality limits: global={self.limits.get('global')}, "
                       f"per-host={self.limits.get('hostname')}, per-metric={self.limits.get('metric')}")
        except Exception as e:
            logger.warning(f"Could not load cardinality limits: {e}")
    
    def _make_series_key(self, metric: dict) -> str:
        """Create unique series identifier from metric + labels"""
        hostname = metric.get('hostname', 'unknown')
        metric_name = metric.get('metric_name', 'unknown')
        tags = metric.get('tags', {})
        
        # Sort tags for consistent key generation
        tag_str = ','.join(f'{k}={v}' for k, v in sorted(tags.items()))
        return f"{hostname}:{metric_name}:{tag_str}"
    
    def sanitize_labels(self, tags: dict) -> dict:
        """Remove high-cardinality labels based on denylist"""
        if not tags:
            return {}
        
        sanitized = {}
        dropped = []
        
        for key, value in tags.items():
            key_lower = key.lower()
            
            # Check denylist
            if key_lower in LABEL_DENYLIST:
                dropped.append(key)
                continue
            
            # Check for suspicious patterns
            if len(str(value)) > 100:  # Very long values
                dropped.append(key)
                continue
            
            # Check if value looks like a UUID/ID
            if self._looks_like_id(str(value)):
                dropped.append(key)
                continue
            
            sanitized[key] = value
        
        if dropped:
            logger.debug(f"Dropped high-cardinality labels: {dropped}")
        
        return sanitized
    
    def _looks_like_id(self, value: str) -> bool:
        """Check if a value looks like a high-cardinality ID"""
        # UUID pattern
        if len(value) == 36 and value.count('-') == 4:
            return True
        
        # Long hex string
        if len(value) >= 16 and all(c in '0123456789abcdefABCDEF' for c in value):
            return True
        
        return False
    
    async def check_and_track(self, metric: dict) -> Tuple[bool, str]:
        """
        Check if a metric should be ingested based on cardinality limits.
        
        Returns:
            Tuple[bool, str]: (should_ingest, reason)
        """
        hostname = metric.get('hostname', 'unknown')
        metric_name = metric.get('metric_name', 'unknown')
        series_key = self._make_series_key(metric)
        
        # Check if this is a new series
        is_new_series = series_key not in self.series_cache
        
        if is_new_series:
            # Check global limit
            global_limit = self.limits.get('global', 1_000_000)
            if len(self.series_cache) >= global_limit:
                action = self.actions.get('global', 'alert')
                self.metrics['dropped_total'] += 1
                self.metrics['limit_breaches'] += 1
                
                if action == 'drop':
                    logger.debug(f"Global cardinality limit reached ({global_limit}), dropping: {series_key[:50]}...")
                    return False, 'global_limit'
                elif action == 'alert':
                    logger.error(f"ALERT: Global cardinality limit breach! {len(self.series_cache)}/{global_limit}")
                    # Still ingest but raise alert
            
            # Check per-host limit
            host_limit = self.limits.get(f'hostname:{hostname}', self.limits.get('hostname', 50_000))
            host_count = self.host_series_count.get(hostname, 0)
            if host_count >= host_limit:
                action = self.actions.get('hostname', 'drop')
                self.metrics['dropped_total'] += 1
                self.metrics['dropped_by_host'][hostname] += 1
                
                if action == 'drop':
                    logger.debug(f"Host {hostname} cardinality limit reached ({host_limit}), dropping")
                    return False, 'host_limit'
                elif action == 'sample':
                    # Sample at 10%
                    if hash(series_key) % 10 != 0:
                        return False, 'sampled'
            
            # Check per-metric limit
            metric_limit = self.limits.get(f'metric:{metric_name}', self.limits.get('metric', 10_000))
            metric_count = self.metric_series_count.get(metric_name, 0)
            if metric_count >= metric_limit:
                action = self.actions.get('metric', 'sample')
                self.metrics['dropped_total'] += 1
                self.metrics['dropped_by_metric'][metric_name] += 1
                
                if action == 'drop':
                    logger.debug(f"Metric {metric_name} cardinality limit reached ({metric_limit})")
                    return False, 'metric_limit'
                elif action == 'sample':
                    if hash(series_key) % 10 != 0:
                        return False, 'sampled'
            
            # Track new series
            self.series_cache[series_key] = datetime.now()
            self.host_series_count[hostname] += 1
            self.metric_series_count[metric_name] += 1
            self.metrics['total_series'] = len(self.series_cache)
        else:
            # Update last seen
            self.series_cache[series_key] = datetime.now()
        
        return True, 'ok'
    
    async def cleanup_stale_series(self, max_age_hours: int = 24):
        """Remove series that haven't been seen recently"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        stale_keys = [
            key for key, last_seen in self.series_cache.items()
            if last_seen < cutoff
        ]
        
        for key in stale_keys:
            # Parse key to update counts
            parts = key.split(':', 2)
            if len(parts) >= 2:
                hostname, metric_name = parts[0], parts[1]
                self.host_series_count[hostname] = max(0, self.host_series_count.get(hostname, 1) - 1)
                self.metric_series_count[metric_name] = max(0, self.metric_series_count.get(metric_name, 1) - 1)
            
            del self.series_cache[key]
        
        self.metrics['total_series'] = len(self.series_cache)
        
        if stale_keys:
            logger.info(f"Cleaned up {len(stale_keys)} stale series (>{max_age_hours}h old)")
    
    def get_stats(self) -> dict:
        """Get cardinality statistics for monitoring"""
        return {
            'total_series': len(self.series_cache),
            'dropped_total': self.metrics['dropped_total'],
            'limit_breaches': self.metrics['limit_breaches'],
            'limits': self.limits.copy(),
            'top_hosts': dict(sorted(
                self.host_series_count.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]),
            'top_metrics': dict(sorted(
                self.metric_series_count.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
        }


# Global cardinality tracker instance
_cardinality_tracker: Optional[CardinalityTracker] = None


def get_cardinality_tracker() -> CardinalityTracker:
    """Get or create the global cardinality tracker"""
    global _cardinality_tracker
    if _cardinality_tracker is None:
        _cardinality_tracker = CardinalityTracker()
    return _cardinality_tracker


async def initialize_cardinality_tracker():
    """Initialize and load limits for the cardinality tracker"""
    tracker = get_cardinality_tracker()
    await tracker.load_limits()
    logger.info("Cardinality tracker initialized")
    return tracker
