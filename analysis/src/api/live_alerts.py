"""
Live Alerts API - Get active alerts for dashboard display

Provides real-time alerts from the comprehensive health monitoring system.
"""
from fastapi import APIRouter
from datetime import datetime, timedelta
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/alerts/live")
async def get_live_alerts():
    """
    Get currently active alerts (from last 5 minutes).
    These are alerts that are actively firing right now.
    """
    try:
        from monitors.system_health import run_comprehensive_health_check
        from storage.clickhouse_client import get_clickhouse_client
        
        client = get_clickhouse_client()
        alerts = await run_comprehensive_health_check(client)
        
        # Format for frontend
        formatted = []
        for alert in alerts:
            formatted.append({
                "id": alert.get("id", "unknown"),
                "severity": alert.get("severity", "warning"),
                "message": alert.get("message", "Unknown alert"),
                "hostname": alert.get("hostname", "unknown"),
                "metric": alert.get("metric_name", ""),
                "value": alert.get("value", 0),
                "threshold": alert.get("threshold", 0),
                "triggered_at": alert.get("triggered_at", datetime.now().isoformat())
            })
        
        # Sort by severity (critical first)
        formatted.sort(key=lambda x: 0 if x["severity"] == "critical" else 1)
        
        return {
            "count": len(formatted),
            "alerts": formatted,
            "checked_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get live alerts: {e}")
        return {
            "count": 0,
            "alerts": [],
            "error": str(e),
            "checked_at": datetime.now().isoformat()
        }


@router.get("/api/alerts/history")
async def get_alert_history(limit: int = 50):
    """
    Get historical alerts from database.
    These are alerts that were triggered in the past.
    """
    try:
        from storage.clickhouse_client import get_clickhouse_client
        
        client = get_clickhouse_client()
        
        query = f"""
            SELECT 
                toString(id) as id,
                rule_name as message,
                value,
                threshold,
                status,
                toDateTime(triggered_at) as triggered_at,
                resolved_at
            FROM metric_alert_history
            ORDER BY triggered_at DESC
            LIMIT {limit}
        """
        
        results = client.client.execute(query)
        
        alerts = []
        for row in results:
            alerts.append({
                "id": row[0],
                "message": row[1],
                "value": row[2],
                "threshold": row[3],
                "status": row[4],
                "triggered_at": row[5].isoformat() if row[5] else None,
                "resolved_at": row[6].isoformat() if row[6] else None
            })
        
        return {
            "count": len(alerts),
            "alerts": alerts
        }
        
    except Exception as e:
        logger.error(f"Failed to get alert history: {e}")
        return {
            "count": 0,
            "alerts": [],
            "error": str(e)
        }


@router.get("/api/alerts/summary")
async def get_alerts_summary():
    """
    Get a summary of current alert status for dashboard display.
    """
    try:
        from monitors.system_health import run_comprehensive_health_check
        from storage.clickhouse_client import get_clickhouse_client
        
        client = get_clickhouse_client()
        alerts = await run_comprehensive_health_check(client)
        
        critical = [a for a in alerts if a.get("severity") == "critical"]
        warning = [a for a in alerts if a.get("severity") == "warning"]
        
        return {
            "total": len(alerts),
            "critical_count": len(critical),
            "warning_count": len(warning),
            "status": "critical" if critical else ("warning" if warning else "healthy"),
            "critical_alerts": [{"message": a.get("message"), "hostname": a.get("hostname")} for a in critical[:5]],
            "warning_alerts": [{"message": a.get("message"), "hostname": a.get("hostname")} for a in warning[:5]],
            "checked_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get alerts summary: {e}")
        return {
            "total": 0,
            "critical_count": 0,
            "warning_count": 0,
            "status": "unknown",
            "error": str(e)
        }
