"""
Alert Rules and Threshold Detection
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from ..storage.clickhouse_client import get_clickhouse_client
from ..api.realtime import broadcast_alert
from .telegram_notifier import send_telegram_alert
from .remediation_actions import execute_alert_remediation
from utils.timezone import now

logger = logging.getLogger(__name__)


class AlertRule:
    """Define an alert rule with thresholds"""
    
    def __init__(
        self,
        name: str,
        metric: str,
        condition: str,  # >, <, >=, <=, ==
        threshold: float,
        level: str = 'warning',  # critical, warning, info
        cooldown_minutes: int = 30
    ):
        self.name = name
        self.metric = metric
        self.condition = condition
        self.threshold = threshold
        self.level = level
        self.cooldown_minutes = cooldown_minutes
        self.last_triggered: Dict[str, datetime] = {}  # server -> last trigger time
    
    def check_cooldown(self, server: str) -> bool:
        """Check if alert is still in cooldown period"""
        if server not in self.last_triggered:
            return True
        
        last_time = self.last_triggered[server]
        cooldown_end = last_time + timedelta(minutes=self.cooldown_minutes)
        return now() > cooldown_end
    
    def evaluate(self, value: float) -> bool:
        """Evaluate if value meets the alert condition"""
        if self.condition == '>':
            return value > self.threshold
        elif self.condition == '<':
            return value < self.threshold
        elif self.condition == '>=':
            return value >= self.threshold
        elif self.condition == '<=':
            return value <= self.threshold
        elif self.condition == '==':
            return value == self.threshold
        return False
    
    def trigger(self, server: str, value: float):
        """Mark alert as triggered for this server"""
        self.last_triggered[server] = now()


# Define default alert rules
DEFAULT_RULES = [
    # CPU Alerts
    AlertRule('Critical CPU', 'cpu_usage_percent', '>', 90, level='critical', cooldown_minutes=15),
    AlertRule('High CPU', 'cpu_usage_percent', '>', 80, level='warning', cooldown_minutes=30),
    
    # Memory Alerts
    AlertRule('Critical Memory', 'memory_usage_percent', '>', 95, level='critical', cooldown_minutes=15),
    AlertRule('High Memory', 'memory_usage_percent', '>', 85, level='warning', cooldown_minutes=30),
    
    # Disk Space Alerts
    AlertRule('Critical Disk Usage', 'disk_usage_percent', '>', 95, level='critical', cooldown_minutes=30),
    AlertRule('High Disk Usage', 'disk_usage_percent', '>', 90, level='warning', cooldown_minutes=60),
    
    # Disk I/O Alerts
    AlertRule('High Disk Latency', 'disk_latency_ms', '>', 100, level='warning', cooldown_minutes=15),
    AlertRule('Critical Disk Latency', 'disk_latency_ms', '>', 500, level='critical', cooldown_minutes=10),
    
    # Network Alerts - Packet Loss & Retransmits
    AlertRule('Network Packet Loss', 'network_drops', '>', 1000, level='warning', cooldown_minutes=20),
    AlertRule('Critical Network Drops', 'network_drops', '>', 10000, level='critical', cooldown_minutes=10),
    AlertRule('High Network Retransmits', 'network_retransmits', '>', 10000, level='warning', cooldown_minutes=20),
    AlertRule('Critical Network Retransmits', 'network_retransmits', '>', 50000, level='critical', cooldown_minutes=10),
    
    # Network Alerts - Latency
    AlertRule('High Latency P50', 'network_latency_p50', '>', 50, level='warning', cooldown_minutes=15),
    AlertRule('Critical Latency P50', 'network_latency_p50', '>', 200, level='critical', cooldown_minutes=10),
    AlertRule('High Latency P90', 'network_latency_p90', '>', 100, level='warning', cooldown_minutes=15),
    AlertRule('Critical Latency P90', 'network_latency_p90', '>', 500, level='critical', cooldown_minutes=10),
    AlertRule('High Latency P99', 'network_latency_p99', '>', 200, level='warning', cooldown_minutes=15),
    AlertRule('Critical Latency P99', 'network_latency_p99', '>', 1000, level='critical', cooldown_minutes=10),
    
    # Network Alerts - Connection States
    AlertRule('High Active Connections', 'network_active_connections', '>', 5000, level='warning', cooldown_minutes=30),
    AlertRule('Critical Active Connections', 'network_active_connections', '>', 10000, level='critical', cooldown_minutes=15),
    AlertRule('High Established Connections', 'network_established', '>', 3000, level='warning', cooldown_minutes=30),
    AlertRule('High Time Wait', 'network_time_wait', '>', 1000, level='warning', cooldown_minutes=30),
    AlertRule('Critical Time Wait', 'network_time_wait', '>', 5000, level='critical', cooldown_minutes=15),
    AlertRule('High Close Wait', 'network_close_wait', '>', 100, level='warning', cooldown_minutes=15),
    AlertRule('Critical Close Wait', 'network_close_wait', '>', 500, level='critical', cooldown_minutes=10),
    
    # Network Alerts - Connection Rates
    AlertRule('High Connection Open Rate', 'network_connection_open_rate', '>', 500, level='warning', cooldown_minutes=15),
    AlertRule('Critical Connection Open Rate', 'network_connection_open_rate', '>', 2000, level='critical', cooldown_minutes=10),
    AlertRule('High Connection Close Rate', 'network_connection_close_rate', '>', 500, level='warning', cooldown_minutes=15),
    
    # Network Alerts - Bandwidth (bytes per second)
    AlertRule('High Bytes Sent', 'network_bytes_sent', '>', 100000000, level='warning', cooldown_minutes=30),  # 100 MB/s
    AlertRule('High Bytes Received', 'network_bytes_received', '>', 100000000, level='warning', cooldown_minutes=30),  # 100 MB/s
    AlertRule('High Packets Sent', 'network_packets_sent', '>', 100000, level='warning', cooldown_minutes=30),
    AlertRule('High Packets Received', 'network_packets_received', '>', 100000, level='warning', cooldown_minutes=30),
    
    # Open Files Alerts
    AlertRule('High Open Files', 'open_files_percent', '>', 80, level='warning', cooldown_minutes=30),
    AlertRule('Critical Open Files', 'open_files_percent', '>', 95, level='critical', cooldown_minutes=15),
    
    # Inode Alerts (using absolute thresholds since we don't have max inodes easily)
    # Typically inode exhaustion is rare but critical when it happens
    AlertRule('High Inode Usage', 'inodes_used', '>', 5000000, level='warning', cooldown_minutes=60),
    AlertRule('Critical Inode Usage', 'inodes_used', '>', 10000000, level='critical', cooldown_minutes=30),
    
    # Load Average Alerts
    AlertRule('High Load Average', 'load_avg_1min', '>', 10, level='warning', cooldown_minutes=15),
    AlertRule('Critical Load Average', 'load_avg_1min', '>', 20, level='critical', cooldown_minutes=10),
    
    # Socket/Network Pressure
    AlertRule('Socket Queue Pressure', 'socket_queue_pressure', '>', 0, level='warning', cooldown_minutes=15),
]


class AlertManager:
    """Manage alert rules and trigger alerts"""
    
    def __init__(self, rules: Optional[List[AlertRule]] = None):
        self.rules = rules or DEFAULT_RULES
        logger.info(f"Alert Manager initialized with {len(self.rules)} rules")
    
    async def check_metric(self, metric_name: str, value: float, server: str):
        """
        Check if a metric value triggers any alert rules
        
        Args:
            metric_name: Name of the metric
            value: Current metric value
            server: Server hostname
        """
        for rule in self.rules:
            if rule.metric != metric_name:
                continue
            
            # Check if rule is triggered
            if not rule.evaluate(value):
                continue
            
            # Check cooldown
            if not rule.check_cooldown(server):
                logger.debug(f"Alert '{rule.name}' still in cooldown for {server}")
                continue
            
            # Trigger alert
            rule.trigger(server, value)
            
            alert = {
                'level': rule.level,
                'title': rule.name,
                'message': f'{metric_name} is {value:.1f} (threshold: {rule.threshold})',
                'hostname': server,
                'server': server,
                'metric': metric_name,
                'value': value,
                'threshold': rule.threshold
            }
            
            logger.warning(f"🚨 Alert triggered: {rule.name} on {server} (value: {value})")
            
            # Send to WebSocket clients
            await broadcast_alert(alert)
            
            # Send to Telegram
            await send_telegram_alert(alert)
            
            # Execute auto-remediation if enabled
            try:
                await execute_alert_remediation(rule.name, server, value)
            except Exception as e:
                logger.error(f"Remediation failed for {rule.name}: {e}")
    
    async def check_recent_metrics(self, minutes: int = 5):
        """
        Check recent metrics from ClickHouse for threshold breaches
        
        This can be called periodically to check for alerts
        """
        ch = get_clickhouse_client()
        
        try:
            # Get recent metrics for each rule
            for rule in self.rules:
                query = f"""
                SELECT 
                    hostname,
                    metric_name,
                    AVG(value) as avg_value,
                    MAX(value) as max_value
                FROM AncientReport.metrics
                WHERE 
                    metric_name = '{rule.metric}'
                    AND timestamp >= now() - INTERVAL {minutes} MINUTE
                GROUP BY hostname, metric_name
                HAVING max_value {rule.condition} {rule.threshold}
                """
                
                result = ch.query(query)
                
                for row in result:
                    await self.check_metric(
                        metric_name=row['metric_name'],
                        value=row['max_value'],
                        server=row['hostname']
                    )
        
        except Exception as e:
            logger.error(f"Error checking recent metrics: {e}")


# Global alert manager
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


async def check_alerts():
    """Convenience function to check all alerts"""
    manager = get_alert_manager()
    await manager.check_recent_metrics()

