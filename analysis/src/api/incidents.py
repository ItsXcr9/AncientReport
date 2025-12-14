"""
Incidents API - Alert Correlation and Incident Management
Groups related alerts into incidents to reduce noise
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import asyncio
import uuid
import json

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/incidents", tags=["Alert Incidents"])


# ============================================
# Models
# ============================================

class Incident(BaseModel):
    id: str
    title: str
    description: str
    status: str  # open, acknowledged, resolved
    severity: str
    root_cause: str
    affected_hosts: List[str]
    affected_services: List[str]
    alert_count: int
    first_alert_at: str
    last_alert_at: str
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    resolved_by: Optional[str]
    resolved_at: Optional[str]
    created_at: str


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    root_cause: Optional[str] = None
    resolution_notes: Optional[str] = None


# ============================================
# Correlation Logic
# ============================================

def determine_severity(alerts: List[dict]) -> str:
    """Determine incident severity based on alerts"""
    severities = [a.get("severity", "warning") for a in alerts]
    if "critical" in severities:
        return "critical"
    elif "warning" in severities:
        return "warning"
    return "info"


def generate_incident_title(alerts: List[dict]) -> str:
    """Generate incident title from alerts"""
    if not alerts:
        return "Unknown Incident"
    
    # Get unique hosts and metrics
    hosts = set(a.get("hostname", "") for a in alerts if a.get("hostname"))
    metrics = set(a.get("metric_name", "") for a in alerts if a.get("metric_name"))
    
    if len(hosts) == 1:
        host = list(hosts)[0]
        if len(metrics) == 1:
            return f"{list(metrics)[0]} alert on {host}"
        else:
            return f"Multiple alerts on {host}"
    else:
        if len(metrics) == 1:
            return f"{list(metrics)[0]} alerts across {len(hosts)} hosts"
        else:
            return f"Multiple alerts across {len(hosts)} hosts"


async def find_or_create_incident(client, alert: dict) -> str:
    """Find an existing open incident to add alert to, or create new one"""
    
    hostname = alert.get("hostname", "")
    alert_time = alert.get("triggered_at")
    
    # Look for open incidents on the same host within the last 5 minutes
    query = f"""
        SELECT toString(id), title, affected_hosts, alert_ids, alert_count,
               last_alert_at, severity
        FROM alert_incidents FINAL
        WHERE status = 'open'
          AND last_alert_at >= now() - INTERVAL 5 MINUTE
        ORDER BY last_alert_at DESC
        LIMIT 10
    """
    
    existing = client.client.execute(query)
    
    for incident in existing:
        incident_id = incident[0]
        affected_hosts = json.loads(incident[2]) if incident[2] else []
        
        # If same host is affected, add to this incident
        if hostname in affected_hosts:
            return incident_id
    
    # Create new incident
    incident_id = str(uuid.uuid4())
    title = generate_incident_title([alert])
    severity = alert.get("severity", "warning")
    
    insert_query = f"""
        INSERT INTO alert_incidents (
            id, title, status, severity, affected_hosts, affected_services,
            alert_ids, alert_count, first_alert_at, last_alert_at
        ) VALUES (
            toUUID('{incident_id}'),
            '{title.replace("'", "''")}',
            'open',
            '{severity}',
            '["{hostname}"]',
            '[]',
            '[]',
            1,
            now(),
            now()
        )
    """
    client.client.execute(insert_query)
    
    logger.info(f"Created new incident: {title}")
    return incident_id


async def add_alert_to_incident(client, incident_id: str, alert: dict):
    """Add an alert to an existing incident"""
    
    alert_id = alert.get("id", "")
    hostname = alert.get("hostname", "")
    metric = alert.get("metric_name", "")
    
    # Get current incident data
    query = f"""
        SELECT affected_hosts, affected_services, alert_ids, alert_count, severity
        FROM alert_incidents FINAL
        WHERE id = toUUID('{incident_id}')
    """
    result = client.client.execute(query)
    
    if not result:
        return
    
    row = result[0]
    affected_hosts = json.loads(row[0]) if row[0] else []
    affected_services = json.loads(row[1]) if row[1] else []
    alert_ids = json.loads(row[2]) if row[2] else []
    alert_count = row[3]
    current_severity = row[4]
    
    # Update lists
    if hostname and hostname not in affected_hosts:
        affected_hosts.append(hostname)
    if metric and metric not in affected_services:
        affected_services.append(metric)
    if alert_id and alert_id not in alert_ids:
        alert_ids.append(alert_id)
    
    alert_count += 1
    
    # Escalate severity if needed
    alert_severity = alert.get("severity", "warning")
    if alert_severity == "critical":
        current_severity = "critical"
    
    # Update incident
    update_query = f"""
        ALTER TABLE alert_incidents UPDATE
        affected_hosts = '{json.dumps(affected_hosts)}',
        affected_services = '{json.dumps(affected_services)}',
        alert_ids = '{json.dumps(alert_ids)}',
        alert_count = {alert_count},
        severity = '{current_severity}',
        last_alert_at = now(),
        updated_at = now()
        WHERE id = toUUID('{incident_id}')
    """
    client.client.execute(update_query)
    
    # Map alert to incident
    map_query = f"""
        INSERT INTO incident_alerts (incident_id, alert_history_id, hostname, metric_name)
        VALUES (
            toUUID('{incident_id}'),
            toUUID('{alert_id}'),
            '{hostname}',
            '{metric}'
        )
    """
    client.client.execute(map_query)


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=List[Incident])
async def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    hours: int = 24,
    limit: int = 50
):
    """List incidents"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        conditions = [f"created_at >= now() - INTERVAL {hours} HOUR"]
        
        if status:
            conditions.append(f"status = '{status}'")
        if severity:
            conditions.append(f"severity = '{severity}'")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                toString(id), title, description, status, severity, root_cause,
                affected_hosts, affected_services, alert_count,
                toString(first_alert_at), toString(last_alert_at),
                acknowledged_by, toString(acknowledged_at),
                resolved_by, toString(resolved_at), toString(created_at)
            FROM alert_incidents FINAL
            WHERE {where_clause}
            ORDER BY 
                CASE status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                last_alert_at DESC
            LIMIT {limit}
        """
        rows = client.client.execute(query)
        
        return [
            Incident(
                id=row[0],
                title=row[1],
                description=row[2],
                status=row[3],
                severity=row[4],
                root_cause=row[5],
                affected_hosts=json.loads(row[6]) if row[6] else [],
                affected_services=json.loads(row[7]) if row[7] else [],
                alert_count=row[8],
                first_alert_at=row[9],
                last_alert_at=row[10],
                acknowledged_by=row[11] if row[11] else None,
                acknowledged_at=row[12] if row[12] and row[12] != "1970-01-01 00:00:00" else None,
                resolved_by=row[13] if row[13] else None,
                resolved_at=row[14] if row[14] and row[14] != "1970-01-01 00:00:00" else None,
                created_at=row[15]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list incidents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details with related alerts"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            SELECT 
                toString(id), title, description, status, severity, root_cause,
                affected_hosts, affected_services, alert_ids, alert_count,
                toString(first_alert_at), toString(last_alert_at),
                acknowledged_by, toString(acknowledged_at),
                resolved_by, toString(resolved_at), resolution_notes,
                toString(created_at)
            FROM alert_incidents FINAL
            WHERE id = toUUID('{incident_id}')
        """
        rows = client.client.execute(query)
        
        if not rows:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        row = rows[0]
        
        # Get related alerts
        alerts_query = f"""
            SELECT 
                toString(a.alert_history_id), a.hostname, a.metric_name, 
                toString(a.added_at)
            FROM incident_alerts a
            WHERE a.incident_id = toUUID('{incident_id}')
            ORDER BY a.added_at DESC
        """
        alerts = client.client.execute(alerts_query)
        
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "severity": row[4],
            "root_cause": row[5],
            "affected_hosts": json.loads(row[6]) if row[6] else [],
            "affected_services": json.loads(row[7]) if row[7] else [],
            "alert_ids": json.loads(row[8]) if row[8] else [],
            "alert_count": row[9],
            "first_alert_at": row[10],
            "last_alert_at": row[11],
            "acknowledged_by": row[12] if row[12] else None,
            "acknowledged_at": row[13] if row[13] and row[13] != "1970-01-01 00:00:00" else None,
            "resolved_by": row[14] if row[14] else None,
            "resolved_at": row[15] if row[15] and row[15] != "1970-01-01 00:00:00" else None,
            "resolution_notes": row[16],
            "created_at": row[17],
            "related_alerts": [
                {
                    "alert_id": a[0],
                    "hostname": a[1],
                    "metric_name": a[2],
                    "added_at": a[3]
                }
                for a in alerts
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, user: str = "admin"):
    """Acknowledge an incident"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            ALTER TABLE alert_incidents UPDATE
            status = 'acknowledged',
            acknowledged_by = '{user}',
            acknowledged_at = now(),
            updated_at = now()
            WHERE id = toUUID('{incident_id}')
        """
        client.client.execute(query)
        
        logger.info(f"Incident {incident_id} acknowledged by {user}")
        return {"status": "acknowledged", "id": incident_id, "by": user}
    except Exception as e:
        logger.error(f"Failed to acknowledge incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: str, user: str = "admin", notes: str = ""):
    """Resolve an incident"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        safe_notes = notes.replace("'", "''")
        query = f"""
            ALTER TABLE alert_incidents UPDATE
            status = 'resolved',
            resolved_by = '{user}',
            resolved_at = now(),
            resolution_notes = '{safe_notes}',
            updated_at = now()
            WHERE id = toUUID('{incident_id}')
        """
        client.client.execute(query)
        
        logger.info(f"Incident {incident_id} resolved by {user}")
        return {"status": "resolved", "id": incident_id, "by": user}
    except Exception as e:
        logger.error(f"Failed to resolve incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{incident_id}")
async def update_incident(incident_id: str, data: IncidentUpdate):
    """Update incident details"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        updates = []
        
        if data.title:
            updates.append(f"title = '{data.title.replace(chr(39), chr(39)+chr(39))}'")
        if data.description:
            updates.append(f"description = '{data.description.replace(chr(39), chr(39)+chr(39))}'")
        if data.root_cause:
            updates.append(f"root_cause = '{data.root_cause.replace(chr(39), chr(39)+chr(39))}'")
        if data.resolution_notes:
            updates.append(f"resolution_notes = '{data.resolution_notes.replace(chr(39), chr(39)+chr(39))}'")
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updates.append("updated_at = now()")
        
        query = f"""
            ALTER TABLE alert_incidents UPDATE
            {', '.join(updates)}
            WHERE id = toUUID('{incident_id}')
        """
        client.client.execute(query)
        
        return {"status": "updated", "id": incident_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_incident_stats():
    """Get incident statistics"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = """
            SELECT 
                status,
                severity,
                count() as cnt
            FROM alert_incidents FINAL
            WHERE created_at >= now() - INTERVAL 7 DAY
            GROUP BY status, severity
        """
        rows = client.client.execute(query)
        
        stats = {
            "by_status": {},
            "by_severity": {},
            "total_7d": 0
        }
        
        for row in rows:
            status = row[0]
            severity = row[1]
            count = row[2]
            
            stats["total_7d"] += count
            
            if status not in stats["by_status"]:
                stats["by_status"][status] = 0
            stats["by_status"][status] += count
            
            if severity not in stats["by_severity"]:
                stats["by_severity"][severity] = 0
            stats["by_severity"][severity] += count
        
        # MTTR (Mean Time to Resolve) for resolved incidents
        mttr_query = """
            SELECT avg(dateDiff('minute', first_alert_at, resolved_at)) as mttr_minutes
            FROM alert_incidents FINAL
            WHERE status = 'resolved'
              AND resolved_at > first_alert_at
              AND created_at >= now() - INTERVAL 7 DAY
        """
        mttr_result = client.client.execute(mttr_query)
        stats["mttr_minutes"] = round(mttr_result[0][0], 1) if mttr_result and mttr_result[0][0] else None
        
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Background Correlation Task
# ============================================

async def correlate_new_alerts():
    """Correlate new alerts into incidents"""
    client = get_clickhouse_client()
    if not client:
        return
    
    try:
        # Get recent uncorrelated alerts from alert history
        # Look for alerts in the last 5 minutes that aren't in any incident
        query = """
            SELECT 
                toString(h.id), h.rule_name, h.value, h.threshold, h.status,
                toString(h.triggered_at)
            FROM metric_alert_history h
            LEFT JOIN incident_alerts ia ON h.id = ia.alert_history_id
            WHERE h.triggered_at >= now() - INTERVAL 5 MINUTE
              AND ia.incident_id IS NULL
        """
        
        new_alerts = client.client.execute(query)
        
        for alert_row in new_alerts:
            alert = {
                "id": alert_row[0],
                "rule_name": alert_row[1],
                "metric_name": alert_row[1],  # Use rule name as metric placeholder
                "value": alert_row[2],
                "threshold": alert_row[3],
                "status": alert_row[4],
                "triggered_at": alert_row[5],
                "hostname": "default",  # Would need to extract from rule
                "severity": "warning" if alert_row[4] == "firing" else "info"
            }
            
            # Find or create incident
            incident_id = await find_or_create_incident(client, alert)
            
            # Add alert to incident
            await add_alert_to_incident(client, incident_id, alert)
        
        if new_alerts:
            logger.debug(f"Correlated {len(new_alerts)} alerts into incidents")
    
    except Exception as e:
        logger.error(f"Alert correlation failed: {e}")


async def auto_resolve_stale_incidents():
    """Auto-resolve incidents with no new alerts for 30 minutes"""
    client = get_clickhouse_client()
    if not client:
        return
    
    try:
        query = """
            ALTER TABLE alert_incidents UPDATE
            status = 'resolved',
            resolved_by = 'system',
            resolved_at = now(),
            resolution_notes = 'Auto-resolved: No new alerts for 30 minutes',
            updated_at = now()
            WHERE status IN ('open', 'acknowledged')
              AND last_alert_at < now() - INTERVAL 30 MINUTE
        """
        client.client.execute(query)
    except Exception as e:
        logger.error(f"Auto-resolve failed: {e}")


async def alert_correlation_loop():
    """Background loop for alert correlation"""
    logger.info("Starting alert correlation loop")
    while True:
        try:
            await correlate_new_alerts()
            await auto_resolve_stale_incidents()
        except Exception as e:
            logger.error(f"Alert correlation loop error: {e}")
        await asyncio.sleep(30)  # Run every 30 seconds
