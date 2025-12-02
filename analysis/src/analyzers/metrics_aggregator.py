from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class MetricsAggregator:
    """
    Aggregates raw metrics into statistical summaries for AI consumption
    """
    
    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client
    
    async def aggregate_hourly_metrics(
        self, 
        start_time: datetime, 
        end_time: datetime,
        hostname: str = None
    ) -> Dict[str, Any]:
        """
        Aggregate an hour's worth of metrics into statistical summaries.
        This reduces ~3600 data points down to ~30 summary statistics.
        """
        
        # Get aggregated data from ClickHouse
        result = await self.ch.get_metrics_aggregated(start_time, end_time, hostname=hostname)
        
        if not result or not result.get('data'):
            logger.warning(f"No metrics found for aggregation between {start_time} and {end_time}")
            # Try to check what metrics exist in the database
            await self._diagnose_metrics(start_time, end_time)
            return self._empty_aggregation()
        
        logger.info(f"Found {len(result['data'])} metric types in aggregation")
        
        # Parse the results into a structured format
        aggregated = {}
        
        for row in result['data']:
            metric_name = row[0]
            stats = {
                'min': row[1],
                'max': row[2],
                'avg': row[3],
                'p50': row[4],
                'p95': row[5],
                'p99': row[6],
                'std_dev': row[7],
                'sample_count': row[8]
            }
            aggregated[metric_name] = stats
            logger.info(f"Metric {metric_name}: avg={stats['avg']:.2f}, max={stats['max']:.2f}, samples={stats['sample_count']}")
        
        # Organize by metric type
        organized = {
            'cpu': self._extract_cpu_stats(aggregated),
            'memory': self._extract_memory_stats(aggregated),
            'load_avg': self._extract_load_stats(aggregated),
            'process': self._extract_process_stats(aggregated),
            'disk_io': self._extract_disk_io_stats(aggregated),
            'network': self._extract_network_stats(aggregated)
        }
        
        logger.info(f"Aggregated metrics for {start_time} to {end_time}")
        return organized
    
    def _extract_cpu_stats(self, aggregated: Dict) -> Dict:
        """Extract CPU statistics"""
        cpu_stats = aggregated.get('cpu_usage_percent', {})
        if not cpu_stats:
            logger.warning("No CPU stats found in aggregated data")
            return {'average': 0, 'peak': 0, 'min': 0}
        
        avg = round(cpu_stats.get('avg', 0), 2)
        peak = round(cpu_stats.get('max', 0), 2)
        logger.debug(f"CPU stats: avg={avg}, peak={peak}")
        
        return {
            'average': avg,
            'peak': peak,
            'min': round(cpu_stats.get('min', 0), 2),
            'p95': round(cpu_stats.get('p95', 0), 2),
            'std_dev': round(cpu_stats.get('std_dev', 0), 2)
        }
    
    def _extract_memory_stats(self, aggregated: Dict) -> Dict:
        """Extract memory statistics"""
        mem_pct_stats = aggregated.get('memory_usage_percent', {})
        mem_used_stats = aggregated.get('memory_used_mb', {})
        mem_total_stats = aggregated.get('memory_total_mb', {})
        
        if not mem_pct_stats:
            logger.warning("No memory stats found in aggregated data")
            return {'average': 0, 'peak': 0}
        
        avg = round(mem_pct_stats.get('avg', 0), 2)
        peak = round(mem_pct_stats.get('max', 0), 2)
        logger.debug(f"Memory stats: avg={avg}, peak={peak}")
        
        return {
            'average': avg,
            'peak': peak,
            'min': round(mem_pct_stats.get('min', 0), 2),
            'used_mb': round(mem_used_stats.get('avg', 0), 2) if mem_used_stats else 0,
            'total_mb': round(mem_total_stats.get('avg', 0), 2) if mem_total_stats else 0,
        }
    
    def _extract_load_stats(self, aggregated: Dict) -> Dict:
        """Extract load average statistics"""
        load_1 = aggregated.get('load_avg_1min', {})
        load_5 = aggregated.get('load_avg_5min', {})
        load_15 = aggregated.get('load_avg_15min', {})
        
        return {
            'load_1min': round(load_1.get('avg', 0), 2) if load_1 else 0,
            'load_5min': round(load_5.get('avg', 0), 2) if load_5 else 0,
            'load_15min': round(load_15.get('avg', 0), 2) if load_15 else 0,
        }
    
    def _extract_process_stats(self, aggregated: Dict) -> Dict:
        """Extract process count statistics"""
        proc_stats = aggregated.get('process_count', {})
        
        if not proc_stats:
            return {'count': 0}
        
        return {
            'average': round(proc_stats.get('avg', 0), 0),
            'max': round(proc_stats.get('max', 0), 0),
            'min': round(proc_stats.get('min', 0), 0),
        }
    
    def _extract_disk_io_stats(self, aggregated: Dict) -> Dict:
        """Extract disk I/O statistics"""
        reads_stats = aggregated.get('disk_reads_per_sec', {})
        writes_stats = aggregated.get('disk_writes_per_sec', {})
        latency_stats = aggregated.get('disk_latency_ms', {})
        
        return {
            'reads_per_sec': round(reads_stats.get('avg', 0), 2) if reads_stats else 0,
            'writes_per_sec': round(writes_stats.get('avg', 0), 2) if writes_stats else 0,
            'latency_ms': round(latency_stats.get('avg', 0), 2) if latency_stats else 0,
            'peak_reads': round(reads_stats.get('max', 0), 2) if reads_stats else 0,
            'peak_writes': round(writes_stats.get('max', 0), 2) if writes_stats else 0,
        }
    
    def _extract_network_stats(self, aggregated: Dict) -> Dict:
        """Extract network statistics"""
        sent_stats = aggregated.get('network_packets_sent', {})
        received_stats = aggregated.get('network_packets_received', {})
        drops_stats = aggregated.get('network_drops', {})
        
        return {
            'packets_sent': round(sent_stats.get('avg', 0), 2) if sent_stats else 0,
            'packets_received': round(received_stats.get('avg', 0), 2) if received_stats else 0,
            'drops': round(drops_stats.get('avg', 0), 2) if drops_stats else 0,
            'peak_sent': round(sent_stats.get('max', 0), 2) if sent_stats else 0,
            'peak_received': round(received_stats.get('max', 0), 2) if received_stats else 0,
        }
    
    async def _diagnose_metrics(self, start_time: datetime, end_time: datetime):
        """Diagnose why no metrics are found"""
        try:
            start_str = start_time.replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
            end_str = end_time.replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
            
            # Check if table exists and has any data
            check_sql = f"""
            SELECT 
                count(*) as total_rows,
                min(timestamp) as earliest,
                max(timestamp) as latest,
                uniq(metric_name) as unique_metrics
            FROM metrics
            """
            
            result = await self.ch.query_df(check_sql)
            if result and result.get('data'):
                row = result['data'][0]
                total_rows = row[0] if row[0] else 0
                earliest = row[1] if row[1] else None
                latest = row[2] if row[2] else None
                unique_metrics = row[3] if row[3] else 0
                
                logger.warning(f"Metrics table diagnostics:")
                logger.warning(f"  Total rows: {total_rows}")
                logger.warning(f"  Earliest timestamp: {earliest}")
                logger.warning(f"  Latest timestamp: {latest}")
                logger.warning(f"  Unique metric names: {unique_metrics}")
                logger.warning(f"  Query time range: {start_str} to {end_str}")
                
                # Check what metric names exist
                if total_rows > 0:
                    names_sql = """
                    SELECT DISTINCT metric_name 
                    FROM metrics 
                    ORDER BY metric_name 
                    LIMIT 20
                    """
                    names_result = await self.ch.query_df(names_sql)
                    if names_result and names_result.get('data'):
                        metric_names = [row[0] for row in names_result['data']]
                        logger.warning(f"  Available metric names: {', '.join(metric_names)}")
            
            # Check for data in the requested time range
            range_sql = f"""
            SELECT count(*) as count
            FROM metrics
            WHERE timestamp >= '{start_str}' AND timestamp <= '{end_str}'
            """
            range_result = await self.ch.query_df(range_sql)
            if range_result and range_result.get('data'):
                count = range_result['data'][0][0] if range_result['data'][0][0] else 0
                logger.warning(f"  Rows in requested time range: {count}")
                
        except Exception as e:
            logger.error(f"Failed to diagnose metrics: {e}", exc_info=True)
    
    def _empty_aggregation(self) -> Dict:
        """Return empty aggregation structure"""
        return {
            'cpu': {'average': 0, 'peak': 0, 'min': 0},
            'memory': {'average': 0, 'peak': 0},
            'load_avg': {'load_1min': 0, 'load_5min': 0, 'load_15min': 0},
            'process': {'average': 0},
            'disk_io': {'reads_per_sec': 0, 'writes_per_sec': 0, 'latency_ms': 0},
            'network': {'packets_sent': 0, 'packets_received': 0, 'drops': 0}
        }
