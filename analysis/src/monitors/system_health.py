"""
System Health Monitor - Comprehensive monitoring for all abnormal conditions

Monitors:
1. Container health (crash loops, unhealthy status)
2. High CPU usage
3. High memory usage
4. High disk usage
5. Network issues (high latency, drops, socket pressure)
6. Load average
7. Agent connectivity
8. Network connections (close_wait, time_wait)
"""
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


# Thresholds for various metrics
THRESHOLDS = {
    'cpu_critical': 90,
    'cpu_warning': 80,
    'memory_critical': 95,
    'memory_warning': 85,
    'disk_critical': 95,
    'disk_warning': 85,
    'latency_critical': 500,  # ms
    'latency_warning': 200,   # ms
    'container_restarts': 3,
    'agent_timeout_minutes': 5,
    'load_avg_warning': 10,  # load average
    'load_avg_critical': 20,
    'close_wait_warning': 100,  # connections in CLOSE_WAIT
    'time_wait_warning': 500,   # connections in TIME_WAIT
    'network_drops_warning': 100,  # drops per minute
    'retransmits_warning': 50,  # retransmits
}


async def check_all_health(client) -> List[Dict]:
    """Run all health checks and return list of alerts."""
    all_alerts = []
    
    # Container health
    container_alerts = await check_container_health(client)
    all_alerts.extend(container_alerts)
    
    # System metrics health (CPU, memory, disk, latency)
    system_alerts = await check_system_metrics(client)
    all_alerts.extend(system_alerts)
    
    # Network health (drops, connections, socket pressure)
    network_alerts = await check_network_health(client)
    all_alerts.extend(network_alerts)
    
    # Load average
    load_alerts = await check_load_average(client)
    all_alerts.extend(load_alerts)
    
    # Agent connectivity
    agent_alerts = await check_agent_connectivity(client)
    all_alerts.extend(agent_alerts)
    
    if all_alerts:
        logger.info(f"Health check found {len(all_alerts)} total issues")
    
    return all_alerts


async def check_container_health(client) -> List[Dict]:
    """Check for container issues"""
    alerts = []
    
    try:
        # Crash loops
        query = """
            SELECT 
                container_name, hostname, restart_count, status
            FROM docker_containers
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
            GROUP BY container_name, hostname, restart_count, status
            HAVING restart_count > 3
            ORDER BY restart_count DESC
            LIMIT 20
        """
        
        results = client.client.execute(query)
        seen = set()
        
        for row in results:
            name, host, restarts, status = row
            key = f"{host}-{name}"
            if key in seen:
                continue
            seen.add(key)
            
            alerts.append({
                "id": f"container-restart-{key}",
                "severity": "critical" if restarts > 10 else "warning",
                "metric_name": "container_restart_count",
                "hostname": host,
                "message": f"🔄 Container '{name}' crash loop ({restarts} restarts)",
                "value": restarts,
                "threshold": 3,
                "triggered_at": datetime.now().isoformat()
            })
        
        # Unhealthy status
        query2 = """
            SELECT container_name, hostname, status
            FROM docker_containers
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
              AND status IN ('restarting', 'dead', 'unhealthy')
            GROUP BY container_name, hostname, status
            LIMIT 20
        """
        
        results2 = client.client.execute(query2)
        for row in results2:
            name, host, status = row
            key = f"{host}-{name}"
            if key in seen:
                continue
            seen.add(key)
                
            alerts.append({
                "id": f"container-status-{key}",
                "severity": "warning",
                "metric_name": "container_status",
                "hostname": host,
                "message": f"⚠️ Container '{name}' is {status}",
                "value": status,
                "threshold": "running",
                "triggered_at": datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Container health check failed: {e}")
    
    return alerts


async def check_system_metrics(client) -> List[Dict]:
    """Check CPU, memory, disk, latency metrics"""
    alerts = []
    
    try:
        query = """
            SELECT 
                hostname,
                argMax(value, timestamp) as latest_value,
                metric_name
            FROM metrics
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
              AND metric_name IN ('cpu_usage_percent', 'memory_usage_percent', 'disk_usage_percent', 'network_latency_p99')
            GROUP BY hostname, metric_name
        """
        
        results = client.client.execute(query)
        
        for row in results:
            host, value, metric = row
            
            if metric == 'cpu_usage_percent':
                if value >= THRESHOLDS['cpu_critical']:
                    alerts.append({
                        "id": f"cpu-critical-{host}",
                        "severity": "critical",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"🔥 High CPU on {host}: {value:.1f}%",
                        "value": value,
                        "threshold": THRESHOLDS['cpu_critical'],
                        "triggered_at": datetime.now().isoformat()
                    })
                elif value >= THRESHOLDS['cpu_warning']:
                    alerts.append({
                        "id": f"cpu-warning-{host}",
                        "severity": "warning",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"⚡ Elevated CPU on {host}: {value:.1f}%",
                        "value": value,
                        "threshold": THRESHOLDS['cpu_warning'],
                        "triggered_at": datetime.now().isoformat()
                    })
                    
            elif metric == 'memory_usage_percent':
                if value >= THRESHOLDS['memory_critical']:
                    alerts.append({
                        "id": f"memory-critical-{host}",
                        "severity": "critical",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"🔥 High memory on {host}: {value:.1f}%",
                        "value": value,
                        "threshold": THRESHOLDS['memory_critical'],
                        "triggered_at": datetime.now().isoformat()
                    })
                elif value >= THRESHOLDS['memory_warning']:
                    alerts.append({
                        "id": f"memory-warning-{host}",
                        "severity": "warning",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"⚡ Elevated memory on {host}: {value:.1f}%",
                        "value": value,
                        "threshold": THRESHOLDS['memory_warning'],
                        "triggered_at": datetime.now().isoformat()
                    })
                    
            elif metric == 'disk_usage_percent':
                if value >= THRESHOLDS['disk_critical']:
                    alerts.append({
                        "id": f"disk-critical-{host}",
                        "severity": "critical",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"💾 Disk almost full on {host}: {value:.1f}%",
                        "value": value,
                        "threshold": THRESHOLDS['disk_critical'],
                        "triggered_at": datetime.now().isoformat()
                    })
                elif value >= THRESHOLDS['disk_warning']:
                    alerts.append({
                        "id": f"disk-warning-{host}",
                        "severity": "warning",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"💾 Disk filling up on {host}: {value:.1f}%",
                        "value": value,
                        "threshold": THRESHOLDS['disk_warning'],
                        "triggered_at": datetime.now().isoformat()
                    })
                    
            elif metric == 'network_latency_p99':
                if value >= THRESHOLDS['latency_critical']:
                    alerts.append({
                        "id": f"latency-critical-{host}",
                        "severity": "critical",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"🌐 High latency on {host}: {value:.0f}ms",
                        "value": value,
                        "threshold": THRESHOLDS['latency_critical'],
                        "triggered_at": datetime.now().isoformat()
                    })
                elif value >= THRESHOLDS['latency_warning']:
                    alerts.append({
                        "id": f"latency-warning-{host}",
                        "severity": "warning",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"🌐 Elevated latency on {host}: {value:.0f}ms",
                        "value": value,
                        "threshold": THRESHOLDS['latency_warning'],
                        "triggered_at": datetime.now().isoformat()
                    })
                    
    except Exception as e:
        logger.error(f"System metrics check failed: {e}")
    
    return alerts


async def check_network_health(client) -> List[Dict]:
    """Check network drops, socket pressure, connection states"""
    alerts = []
    

    try:
        # We need to distinguish between gauges (latest value) and counters (rate/increase)
        # For retransmits and drops, we want the INCREASE over the time window.
        # For close_wait/time_wait/pressure, we want the LATEST value.
        query = """
            SELECT 
                hostname,
                metric_name,
                argMax(value, timestamp) as latest_value,
                max(value) - min(value) as delta_value
            FROM metrics
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
              AND metric_name IN ('network_close_wait', 'network_time_wait', 'network_drops', 'network_retransmits', 'network_socket_pressure')
            GROUP BY hostname, metric_name
        """
        
        results = client.client.execute(query)
        
        for row in results:
            host, metric, latest_value, delta_value = row
            
            # Use delta for counters, latest for gauges
            effective_value = delta_value if metric in ('network_retransmits', 'network_drops') else latest_value
            
            if metric == 'network_close_wait' and effective_value >= THRESHOLDS['close_wait_warning']:
                alerts.append({
                    "id": f"close-wait-{host}",
                    "severity": "warning",
                    "metric_name": metric,
                    "hostname": host,
                    "message": f"🔌 High CLOSE_WAIT on {host}: {int(effective_value)} connections",
                    "value": effective_value,
                    "threshold": THRESHOLDS['close_wait_warning'],
                    "triggered_at": datetime.now().isoformat()
                })
                
            elif metric == 'network_time_wait' and effective_value >= THRESHOLDS['time_wait_warning']:
                alerts.append({
                    "id": f"time-wait-{host}",
                    "severity": "warning",
                    "metric_name": metric,
                    "hostname": host,
                    "message": f"⏳ High TIME_WAIT on {host}: {int(effective_value)} connections",
                    "value": effective_value,
                    "threshold": THRESHOLDS['time_wait_warning'],
                    "triggered_at": datetime.now().isoformat()
                })
                
            elif metric == 'network_drops' and effective_value >= THRESHOLDS['network_drops_warning']:
                alerts.append({
                    "id": f"net-drops-{host}",
                    "severity": "critical",
                    "metric_name": metric,
                    "hostname": host,
                    "message": f"🗑️ High Network Drops on {host}: {int(effective_value)} drops/5m",
                    "value": effective_value,
                    "threshold": THRESHOLDS['network_drops_warning'],
                    "triggered_at": datetime.now().isoformat()
                })
                
            elif metric == 'network_retransmits' and effective_value >= THRESHOLDS['retransmits_warning']:
                alerts.append({
                    "id": f"net-retrans-{host}",
                    "severity": "critical", # User concerned about this, prioritize it
                    "metric_name": metric,
                    "hostname": host,
                    "message": f"🔄 High Retransmits on {host}: {int(effective_value)} retrans/5m",
                    "value": effective_value,
                    "threshold": THRESHOLDS['retransmits_warning'],
                    "triggered_at": datetime.now().isoformat()
                })

            elif metric == 'network_socket_pressure' and effective_value >= 20:
                severity = "critical" if effective_value >= 50 else "warning"
                alerts.append({
                    "id": f"net-pressure-{host}",
                    "severity": severity,
                    "metric_name": metric,
                    "hostname": host,
                    "message": f"📈 Network Pressure on {host}: {effective_value:.1f}%",
                    "value": effective_value,
                    "threshold": 20,
                    "triggered_at": datetime.now().isoformat()
                })

    except Exception as e:
        logger.error(f"Network health check failed: {e}")
    
    return alerts



async def check_load_average(client) -> List[Dict]:
    """Check system load average"""
    alerts = []
    
    try:
        query = """
            SELECT 
                hostname,
                argMax(value, timestamp) as latest_value,
                metric_name
            FROM metrics
            WHERE timestamp >= now() - INTERVAL 5 MINUTE
              AND metric_name IN ('load_avg_1min', 'load_avg_5min')
            GROUP BY hostname, metric_name
        """
        
        results = client.client.execute(query)
        seen = set()
        
        for row in results:
            host, value, metric = row
            
            # Only alert once per host
            if host in seen:
                continue
                
            if metric == 'load_avg_1min' or metric == 'load_avg_5min':
                if value >= THRESHOLDS['load_avg_critical']:
                    seen.add(host)
                    alerts.append({
                        "id": f"load-critical-{host}",
                        "severity": "critical",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"📈 Critical load on {host}: {value:.1f}",
                        "value": value,
                        "threshold": THRESHOLDS['load_avg_critical'],
                        "triggered_at": datetime.now().isoformat()
                    })
                elif value >= THRESHOLDS['load_avg_warning']:
                    seen.add(host)
                    alerts.append({
                        "id": f"load-warning-{host}",
                        "severity": "warning",
                        "metric_name": metric,
                        "hostname": host,
                        "message": f"📈 High load on {host}: {value:.1f}",
                        "value": value,
                        "threshold": THRESHOLDS['load_avg_warning'],
                        "triggered_at": datetime.now().isoformat()
                    })
                    
    except Exception as e:
        logger.error(f"Load average check failed: {e}")
    
    return alerts


async def check_agent_connectivity(client) -> List[Dict]:
    """Check if agents are reporting"""
    alerts = []
    
    try:
        query = """
            SELECT 
                hostname,
                max(timestamp) as last_seen,
                dateDiff('minute', max(timestamp), now()) as minutes_ago
            FROM metrics
            WHERE timestamp >= now() - INTERVAL 1 HOUR
            GROUP BY hostname
            HAVING minutes_ago > 5
        """
        
        results = client.client.execute(query)
        
        for row in results:
            host, last_seen, minutes = row
            
            if host in ('', 'unknown'):
                continue
                
            alerts.append({
                "id": f"agent-offline-{host}",
                "severity": "critical",
                "metric_name": "agent_connectivity",
                "hostname": host,
                "message": f"📡 Agent offline: {host} (last seen {minutes} min ago)",
                "value": minutes,
                "threshold": THRESHOLDS['agent_timeout_minutes'],
                "triggered_at": datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Agent connectivity check failed: {e}")
    
    return alerts


async def run_comprehensive_health_check(client, alert_callback=None) -> List[Dict]:
    """Run all health checks and trigger alerts."""
    alerts = await check_all_health(client)
    
    if alert_callback and alerts:
        from monitors.alert_manager import trigger_alerts_batch
        triggered = await trigger_alerts_batch(client, alerts)
        logger.info(f"Triggered {triggered} alerts")
    
    return alerts
