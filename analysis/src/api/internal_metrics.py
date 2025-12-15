"""
Internal Metrics & Self-Monitoring

Collect and expose metrics about the monitoring system itself.
Essential for answering "is the monitoring system healthy?"
"""
import logging
import os
import psutil
import resource
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/internal", tags=["internal"])

# Global metrics collector
_metrics_collector: Optional['SelfMetricsCollector'] = None


class SelfMetricsCollector:
    """
    Collect metrics about the monitoring system itself.
    
    Provides visibility into:
    - Process resources (CPU, memory, FDs)
    - Ingestion pipeline (buffer size, throughput, drops)
    - Cardinality (series count, limit breaches)
    - Alert evaluation (duration, triggered count)
    - Component health
    """
    
    def __init__(self, clickhouse_client=None):
        self.client = clickhouse_client
        self.process = psutil.Process()
        self.start_time = datetime.now()
        
        # Counters (monotonically increasing)
        self.counters = {
            'ingested_total': 0,
            'dropped_total': 0,
            'alerts_triggered_total': 0,
            'errors_total': 0,
            'flushes_total': 0,
        }
        
        # Gauges (current values)
        self.gauges = {
            'buffer_size': 0,
            'cardinality_series': 0,
            'active_alerts': 0,
            'open_fds': 0,
            'memory_mb': 0,
            'cpu_percent': 0,
        }
        
        # Histograms (distributions)
        self.histograms = {
            'flush_duration_ms': [],
            'alert_eval_duration_ms': [],
            'query_duration_ms': [],
        }
        
        # Component health
        self.component_health = {
            'clickhouse': 'unknown',
            'nats': 'unknown',
            'scheduler': 'unknown',
            'ingestion': 'unknown',
        }
    
    def set_client(self, client):
        """Set ClickHouse client"""
        self.client = client
    
    def increment(self, name: str, value: int = 1):
        """Increment a counter"""
        if name in self.counters:
            self.counters[name] += value
    
    def set_gauge(self, name: str, value: float):
        """Set a gauge value"""
        if name in self.gauges:
            self.gauges[name] = value
    
    def observe(self, name: str, value: float):
        """Record a histogram observation"""
        if name in self.histograms:
            self.histograms[name].append(value)
            # Keep only last 1000 observations
            if len(self.histograms[name]) > 1000:
                self.histograms[name] = self.histograms[name][-1000:]
    
    def set_component_health(self, component: str, status: str):
        """Set component health status"""
        self.component_health[component] = status
    
    def _collect_process_metrics(self):
        """Collect process-level metrics"""
        try:
            cpu = self.process.cpu_percent(interval=0.1)
            memory = self.process.memory_info()
            
            self.gauges['cpu_percent'] = cpu
            self.gauges['memory_mb'] = memory.rss / 1024 / 1024
            
            # File descriptor count
            try:
                self.gauges['open_fds'] = len(self.process.open_files()) + len(self.process.connections())
            except:
                self.gauges['open_fds'] = self.process.num_fds() if hasattr(self.process, 'num_fds') else 0
                
        except Exception as e:
            logger.debug(f"Could not collect process metrics: {e}")
    
    def _calculate_histogram_stats(self, name: str) -> Dict[str, float]:
        """Calculate p50, p90, p99 for a histogram"""
        values = self.histograms.get(name, [])
        if not values:
            return {'p50': 0, 'p90': 0, 'p99': 0, 'count': 0}
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        return {
            'p50': sorted_values[int(n * 0.5)] if n > 0 else 0,
            'p90': sorted_values[int(n * 0.9)] if n > 0 else 0,
            'p99': sorted_values[int(n * 0.99)] if n > 0 else 0,
            'count': n,
            'sum': sum(values),
        }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all internal metrics"""
        self._collect_process_metrics()
        
        # Get resource limits
        soft_fd, hard_fd = resource.getrlimit(resource.RLIMIT_NOFILE)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            
            'counters': self.counters.copy(),
            'gauges': self.gauges.copy(),
            
            'histograms': {
                name: self._calculate_histogram_stats(name)
                for name in self.histograms
            },
            
            'component_health': self.component_health.copy(),
            
            'resources': {
                'open_fds': self.gauges['open_fds'],
                'fd_limit_soft': soft_fd,
                'fd_limit_hard': hard_fd,
                'fd_usage_percent': (self.gauges['open_fds'] / soft_fd * 100) if soft_fd > 0 else 0,
                'memory_mb': self.gauges['memory_mb'],
                'cpu_percent': self.gauges['cpu_percent'],
                'threads': self.process.num_threads(),
            }
        }
    
    async def collect_and_store(self):
        """Collect metrics and store to ClickHouse for historical analysis"""
        if not self.client:
            return
        
        self._collect_process_metrics()
        
        metrics = [
            # Process metrics
            ('analysis', 'process_cpu_percent', self.gauges['cpu_percent']),
            ('analysis', 'process_memory_mb', self.gauges['memory_mb']),
            ('analysis', 'process_open_fds', self.gauges['open_fds']),
            ('analysis', 'process_threads', self.process.num_threads()),
            ('analysis', 'uptime_seconds', (datetime.now() - self.start_time).total_seconds()),
            
            # Ingestion metrics
            ('ingestion', 'buffer_size', self.gauges['buffer_size']),
            ('ingestion', 'ingested_total', self.counters['ingested_total']),
            ('ingestion', 'dropped_total', self.counters['dropped_total']),
            ('ingestion', 'flushes_total', self.counters['flushes_total']),
            
            # Cardinality metrics
            ('cardinality', 'total_series', self.gauges['cardinality_series']),
            
            # Alert metrics
            ('alerts', 'triggered_total', self.counters['alerts_triggered_total']),
            ('alerts', 'active_count', self.gauges['active_alerts']),
            
            # Error metrics
            ('errors', 'total', self.counters['errors_total']),
        ]
        
        try:
            rows = [
                (datetime.now(), comp, name, float(val), {})
                for comp, name, val in metrics
            ]
            await self.client.insert('internal_metrics', rows)
            logger.debug(f"Stored {len(rows)} internal metrics")
        except Exception as e:
            logger.warning(f"Could not store internal metrics: {e}")


def get_metrics_collector() -> SelfMetricsCollector:
    """Get or create the global metrics collector"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = SelfMetricsCollector()
    return _metrics_collector


# API Endpoints

@router.get("/metrics")
async def get_internal_metrics():
    """
    Get all internal metrics for the monitoring system.
    
    Use this to monitor the health of the monitoring system itself.
    """
    collector = get_metrics_collector()
    return collector.get_all_metrics()


@router.get("/health")
async def get_detailed_health():
    """
    Comprehensive health check for all components.
    
    Returns detailed status of each subsystem.
    """
    from storage.clickhouse_client import get_clickhouse_client
    
    collector = get_metrics_collector()
    collector._collect_process_metrics()
    
    checks = {}
    overall_healthy = True
    
    # Check ClickHouse
    try:
        client = get_clickhouse_client()
        if client:
            start = datetime.now()
            client.client.execute("SELECT 1")
            latency_ms = (datetime.now() - start).total_seconds() * 1000
            checks['clickhouse'] = {
                'status': 'healthy',
                'latency_ms': latency_ms
            }
            collector.set_component_health('clickhouse', 'healthy')
        else:
            checks['clickhouse'] = {'status': 'unhealthy', 'error': 'client not initialized'}
            collector.set_component_health('clickhouse', 'unhealthy')
            overall_healthy = False
    except Exception as e:
        checks['clickhouse'] = {'status': 'unhealthy', 'error': str(e)}
        collector.set_component_health('clickhouse', 'unhealthy')
        overall_healthy = False
    
    # Check ingestion buffer
    buffer_size = collector.gauges.get('buffer_size', 0)
    buffer_limit = 100_000
    buffer_pct = (buffer_size / buffer_limit * 100) if buffer_limit > 0 else 0
    
    if buffer_pct >= 90:
        checks['ingestion'] = {'status': 'critical', 'buffer_percent': buffer_pct}
        collector.set_component_health('ingestion', 'critical')
        overall_healthy = False
    elif buffer_pct >= 70:
        checks['ingestion'] = {'status': 'degraded', 'buffer_percent': buffer_pct}
        collector.set_component_health('ingestion', 'degraded')
    else:
        checks['ingestion'] = {'status': 'healthy', 'buffer_percent': buffer_pct}
        collector.set_component_health('ingestion', 'healthy')
    
    # Check FD usage
    fd_count = collector.gauges.get('open_fds', 0)
    soft_fd, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    fd_pct = (fd_count / soft_fd * 100) if soft_fd > 0 else 0
    
    if fd_pct >= 90:
        checks['file_descriptors'] = {'status': 'critical', 'usage_percent': fd_pct, 'count': fd_count, 'limit': soft_fd}
        overall_healthy = False
    elif fd_pct >= 70:
        checks['file_descriptors'] = {'status': 'degraded', 'usage_percent': fd_pct, 'count': fd_count, 'limit': soft_fd}
    else:
        checks['file_descriptors'] = {'status': 'healthy', 'usage_percent': fd_pct, 'count': fd_count, 'limit': soft_fd}
    
    # Check memory usage
    memory_mb = collector.gauges.get('memory_mb', 0)
    total_memory_mb = psutil.virtual_memory().total / 1024 / 1024
    memory_pct = (memory_mb / total_memory_mb * 100) if total_memory_mb > 0 else 0
    
    if memory_pct >= 90:
        checks['memory'] = {'status': 'critical', 'usage_mb': memory_mb, 'percent': memory_pct}
        overall_healthy = False
    elif memory_pct >= 70:
        checks['memory'] = {'status': 'degraded', 'usage_mb': memory_mb, 'percent': memory_pct}
    else:
        checks['memory'] = {'status': 'healthy', 'usage_mb': memory_mb, 'percent': memory_pct}
    
    # Summary
    return {
        'status': 'healthy' if overall_healthy else 'unhealthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': (datetime.now() - collector.start_time).total_seconds(),
        'checks': checks,
        'component_health': collector.component_health.copy()
    }


@router.get("/cardinality")
async def get_cardinality_stats():
    """
    Get cardinality statistics.
    
    Shows current series counts and limit usage.
    """
    try:
        from cardinality import get_cardinality_tracker
        tracker = get_cardinality_tracker()
        return tracker.get_stats()
    except Exception as e:
        logger.error(f"Could not get cardinality stats: {e}")
        return {'error': str(e)}
