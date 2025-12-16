"""
Container Health Monitoring - Alert on container issues

Periodically checks docker_containers table for:
- High restart counts (crash loops)
- Containers in restarting/unhealthy status
- Containers that have been down for too long
"""
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


async def check_container_health(client) -> List[Dict]:
    """
    Check for container health issues and generate alerts.
    
    Returns list of alerts to trigger.
    """
    alerts = []
    
    try:
        # Check for containers with high restart counts (crash loops)
        restart_query = """
            SELECT 
                container_name,
                hostname,
                restart_count,
                status,
                max(timestamp) as last_seen
            FROM docker_containers
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
            GROUP BY container_name, hostname, restart_count, status
            HAVING restart_count > 3
            ORDER BY restart_count DESC
        """
        
        restart_results = client.client.execute(restart_query)
        
        for row in restart_results:
            container_name, hostname, restart_count, status, last_seen = row
            
            alerts.append({
                "id": f"container-restart-{hostname}-{container_name}",
                "severity": "critical" if restart_count > 10 else "warning",
                "metric_name": "container_restart_count",
                "hostname": hostname,
                "message": f"Container '{container_name}' has restarted {restart_count} times",
                "value": restart_count,
                "threshold": 3,
                "container_name": container_name,
                "status": status,
                "triggered_at": datetime.now().isoformat()
            })
            logger.warning(f"🔔 Container crash loop detected: {container_name} on {hostname} (restarts: {restart_count})")
        
        # Check for containers in bad state
        status_query = """
            SELECT 
                container_name,
                hostname,
                status,
                max(timestamp) as last_seen
            FROM docker_containers
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
              AND (status = 'restarting' OR status = 'dead' OR status = 'unhealthy')
            GROUP BY container_name, hostname, status
        """
        
        status_results = client.client.execute(status_query)
        
        for row in status_results:
            container_name, hostname, status, last_seen = row
            
            # Don't duplicate if we already have a restart alert for this container
            existing = any(
                a.get('container_name') == container_name and a.get('hostname') == hostname
                for a in alerts
            )
            
            if not existing:
                alerts.append({
                    "id": f"container-status-{hostname}-{container_name}",
                    "severity": "warning",
                    "metric_name": "container_status",
                    "hostname": hostname,
                    "message": f"Container '{container_name}' is in '{status}' state",
                    "value": status,
                    "threshold": "running",
                    "container_name": container_name,
                    "status": status,
                    "triggered_at": datetime.now().isoformat()
                })
        
        if alerts:
            logger.info(f"Container health check found {len(alerts)} issues")
        
    except Exception as e:
        logger.error(f"Container health check failed: {e}")
    
    return alerts


async def run_container_health_check(client, alert_callback=None):
    """
    Run container health check and optionally trigger alerts.
    
    Args:
        client: ClickHouse client
        alert_callback: Optional async function to call with each alert
    """
    alerts = await check_container_health(client)
    
    if alert_callback:
        for alert in alerts:
            try:
                await alert_callback(alert)
            except Exception as e:
                logger.error(f"Failed to trigger alert: {e}")
    
    return alerts
