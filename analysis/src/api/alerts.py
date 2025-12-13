"""
Alerts API - Metric alert rules and webhook notifications
Evaluates thresholds and sends webhooks when triggered
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import uuid
import httpx
import json
import asyncio

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Pydantic models
class AlertRuleCreate(BaseModel):
    name: str
    target_id: str
    metric_name: str
    condition: str  # 'gt', 'lt', 'eq', 'gte', 'lte'
    threshold: float
    duration_seconds: int = 60
    notification_channel: str = "webhook"
    notification_config: str = "{}"  # JSON with webhook URL etc.

class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    duration_seconds: Optional[int] = None
    notification_config: Optional[str] = None
    enabled: Optional[bool] = None

class AlertRule(BaseModel):
    id: str
    name: str
    target_id: str
    metric_name: str
    condition: str
    threshold: float
    duration_seconds: int
    notification_channel: str
    notification_config: str
    enabled: bool
    last_triggered: Optional[datetime]
    created_at: datetime

class AlertHistoryItem(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    triggered_at: datetime
    value: float
    threshold: float
    status: str
    notified: bool


# Alert Rule CRUD
@router.get("/rules", response_model=List[AlertRule])
async def list_alert_rules():
    """List all alert rules"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = """
            SELECT id, name, target_id, metric_name, condition, threshold,
                   duration_seconds, notification_channel, notification_config,
                   enabled, last_triggered, created_at
            FROM metric_alert_rules FINAL
            ORDER BY created_at DESC
        """
        rows = client.client.execute(query)
        return [
            AlertRule(
                id=str(row[0]),
                name=row[1],
                target_id=str(row[2]),
                metric_name=row[3],
                condition=row[4],
                threshold=row[5],
                duration_seconds=row[6],
                notification_channel=row[7],
                notification_config=row[8],
                enabled=bool(row[9]),
                last_triggered=row[10] if row[10] and row[10].year > 1970 else None,
                created_at=row[11]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list alert rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rules", response_model=AlertRule)
async def create_alert_rule(data: AlertRuleCreate):
    """Create an alert rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        rule_id = str(uuid.uuid4())
        now = datetime.now()
        
        query = f"""
            INSERT INTO metric_alert_rules 
            (id, name, target_id, metric_name, condition, threshold, duration_seconds,
             notification_channel, notification_config, enabled, created_at, updated_at)
            VALUES (
                toUUID('{rule_id}'),
                '{data.name.replace("'", "''")}',
                toUUID('{data.target_id}'),
                '{data.metric_name.replace("'", "''")}',
                '{data.condition}',
                {data.threshold},
                {data.duration_seconds},
                '{data.notification_channel}',
                '{data.notification_config.replace("'", "''")}',
                1,
                now(),
                now()
            )
        """
        client.client.execute(query)
        
        return AlertRule(
            id=rule_id,
            name=data.name,
            target_id=data.target_id,
            metric_name=data.metric_name,
            condition=data.condition,
            threshold=data.threshold,
            duration_seconds=data.duration_seconds,
            notification_channel=data.notification_channel,
            notification_config=data.notification_config,
            enabled=True,
            last_triggered=None,
            created_at=now
        )
    except Exception as e:
        logger.error(f"Failed to create alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_alert_rule(rule_id: str, data: AlertRuleUpdate):
    """Update an alert rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Fetch existing
        fetch_query = f"""
            SELECT name, target_id, metric_name, condition, threshold, 
                   duration_seconds, notification_channel, notification_config,
                   enabled, last_triggered, created_at
            FROM metric_alert_rules FINAL
            WHERE id = toUUID('{rule_id}')
        """
        existing = client.client.execute(fetch_query)
        
        if not existing:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        row = existing[0]
        name = data.name if data.name else row[0]
        condition = data.condition if data.condition else row[3]
        threshold = data.threshold if data.threshold is not None else row[4]
        duration = data.duration_seconds if data.duration_seconds is not None else row[5]
        config = data.notification_config if data.notification_config else row[7]
        enabled = data.enabled if data.enabled is not None else bool(row[8])
        
        # Insert updated row
        last_trig = row[9]
        last_trig_str = "toDateTime('1970-01-01 00:00:00')"
        if last_trig and last_trig.year > 1970:
            last_trig_str = f"toDateTime('{last_trig.strftime('%Y-%m-%d %H:%M:%S')}')"
        
        insert_query = f"""
            INSERT INTO metric_alert_rules 
            (id, name, target_id, metric_name, condition, threshold, duration_seconds,
             notification_channel, notification_config, enabled, last_triggered, created_at, updated_at)
            VALUES (
                toUUID('{rule_id}'),
                '{name.replace("'", "''")}',
                toUUID('{str(row[1])}'),
                '{row[2]}',
                '{condition}',
                {threshold},
                {duration},
                '{row[6]}',
                '{config.replace("'", "''")}',
                {1 if enabled else 0},
                {last_trig_str},
                toDateTime('{row[10].strftime('%Y-%m-%d %H:%M:%S')}'),
                now()
            )
        """
        client.client.execute(insert_query)
        
        return AlertRule(
            id=rule_id,
            name=name,
            target_id=str(row[1]),
            metric_name=row[2],
            condition=condition,
            threshold=threshold,
            duration_seconds=duration,
            notification_channel=row[6],
            notification_config=config,
            enabled=enabled,
            last_triggered=row[9] if row[9] and row[9].year > 1970 else None,
            created_at=row[10]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        client.client.execute(f"""
            ALTER TABLE metric_alert_rules DELETE 
            WHERE id = toUUID('{rule_id}')
        """)
        return {"status": "deleted", "id": rule_id}
    except Exception as e:
        logger.error(f"Failed to delete alert rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Alert History
@router.get("/history", response_model=List[AlertHistoryItem])
async def get_alert_history(limit: int = 100):
    """Get recent alert history"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            SELECT id, rule_id, rule_name, triggered_at, value, threshold, status, notified
            FROM metric_alert_history
            ORDER BY triggered_at DESC
            LIMIT {limit}
        """
        rows = client.client.execute(query)
        return [
            AlertHistoryItem(
                id=str(row[0]),
                rule_id=str(row[1]),
                rule_name=row[2],
                triggered_at=row[3],
                value=row[4],
                threshold=row[5],
                status=row[6],
                notified=bool(row[7])
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to get alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Alert Evaluator (background task)
async def evaluate_alerts():
    """Evaluate all alert rules and send notifications"""
    client = get_clickhouse_client()
    if not client:
        logger.warning("Alert evaluator: Database not initialized")
        return
    
    try:
        # Get all enabled rules
        rules_query = """
            SELECT id, name, target_id, metric_name, condition, threshold,
                   duration_seconds, notification_channel, notification_config, last_triggered
            FROM metric_alert_rules FINAL
            WHERE enabled = 1
        """
        rules = client.client.execute(rules_query)
        
        for rule in rules:
            rule_id = str(rule[0])
            rule_name = rule[1]
            target_id = str(rule[2])
            metric_name = rule[3]
            condition = rule[4]
            threshold = rule[5]
            duration = rule[6]
            channel = rule[7]
            config = rule[8]
            last_triggered = rule[9]
            
            # Get latest metric value (last 5 minutes)
            value_query = f"""
                SELECT avg(value) as avg_val
                FROM scraped_metrics
                WHERE target_id = toUUID('{target_id}')
                  AND metric_name = '{metric_name}'
                  AND timestamp >= now() - INTERVAL {max(duration, 60)} SECOND
            """
            result = client.client.execute(value_query)
            
            if not result or result[0][0] is None:
                continue
            
            avg_value = result[0][0]
            
            # Check condition
            triggered = False
            if condition == 'gt' and avg_value > threshold:
                triggered = True
            elif condition == 'gte' and avg_value >= threshold:
                triggered = True
            elif condition == 'lt' and avg_value < threshold:
                triggered = True
            elif condition == 'lte' and avg_value <= threshold:
                triggered = True
            elif condition == 'eq' and avg_value == threshold:
                triggered = True
            
            if triggered:
                # Check cooldown (don't send if triggered within last 5 minutes)
                if last_triggered and last_triggered.year > 1970:
                    if datetime.now() - last_triggered < timedelta(minutes=5):
                        continue
                
                logger.info(f"Alert triggered: {rule_name} (value={avg_value}, threshold={threshold})")
                
                # Record in history
                history_id = str(uuid.uuid4())
                client.client.execute(f"""
                    INSERT INTO metric_alert_history 
                    (id, rule_id, rule_name, triggered_at, value, threshold, status, notified)
                    VALUES (
                        toUUID('{history_id}'),
                        toUUID('{rule_id}'),
                        '{rule_name.replace("'", "''")}',
                        now(),
                        {avg_value},
                        {threshold},
                        'firing',
                        0
                    )
                """)
                
                # Send webhook notification
                if channel == 'webhook':
                    try:
                        config_dict = json.loads(config) if config else {}
                        webhook_url = config_dict.get('url', '')
                        
                        if webhook_url:
                            payload = {
                                "alert_name": rule_name,
                                "metric": metric_name,
                                "value": avg_value,
                                "threshold": threshold,
                                "condition": condition,
                                "triggered_at": datetime.now().isoformat()
                            }
                            
                            async with httpx.AsyncClient() as http_client:
                                await http_client.post(
                                    webhook_url,
                                    json=payload,
                                    timeout=10.0
                                )
                            
                            # Update notified status
                            client.client.execute(f"""
                                ALTER TABLE metric_alert_history UPDATE 
                                notified = 1, notification_sent_at = now()
                                WHERE id = toUUID('{history_id}')
                            """)
                            
                            logger.info(f"Webhook sent for alert: {rule_name}")
                    except Exception as e:
                        logger.error(f"Failed to send webhook for {rule_name}: {e}")
                
                # Update last_triggered on rule
                client.client.execute(f"""
                    INSERT INTO metric_alert_rules 
                    (id, name, target_id, metric_name, condition, threshold, duration_seconds,
                     notification_channel, notification_config, enabled, last_triggered, created_at, updated_at)
                    SELECT 
                        id, name, target_id, metric_name, condition, threshold, duration_seconds,
                        notification_channel, notification_config, enabled, now(), created_at, now()
                    FROM metric_alert_rules FINAL
                    WHERE id = toUUID('{rule_id}')
                """)
                
    except Exception as e:
        logger.error(f"Alert evaluation failed: {e}")

# Background task runner
async def alert_evaluator_loop():
    """Run alert evaluator every 30 seconds"""
    while True:
        await asyncio.sleep(30)
        await evaluate_alerts()
