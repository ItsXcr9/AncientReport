"""
Recording Rules API - Pre-aggregate expensive Prometheus queries

Similar to Prometheus recording rules, this allows users to define rules that
periodically evaluate queries and store the results as new metrics.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from uuid import UUID
import json
import asyncio
import logging

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recording-rules", tags=["recording-rules"])

# Models
class RecordingRuleCreate(BaseModel):
    name: str
    target_id: str
    source_metric: str
    labels_filter: Optional[dict] = {}
    aggregation: str = "avg"  # sum, avg, max, min
    group_by: Optional[str] = ""  # Comma-separated label keys
    interval_seconds: int = 60
    description: Optional[str] = ""

class RecordingRuleUpdate(BaseModel):
    name: Optional[str] = None
    source_metric: Optional[str] = None
    labels_filter: Optional[dict] = None
    aggregation: Optional[str] = None
    group_by: Optional[str] = None
    interval_seconds: Optional[int] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None

class RecordingRule(BaseModel):
    id: str
    name: str
    target_id: str
    source_metric: str
    labels_filter: dict
    aggregation: str
    group_by: str
    interval_seconds: int
    enabled: bool
    description: str
    last_evaluated: Optional[datetime]
    created_at: datetime
    updated_at: datetime

# CRUD Operations
@router.get("")
async def list_recording_rules():
    """List all recording rules"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        result = client.client.execute("""
            SELECT 
                id, name, target_id, source_metric, labels_filter,
                aggregation, group_by, interval_seconds, enabled,
                description, last_evaluated, created_at, updated_at
            FROM recording_rules
            ORDER BY name
        """)
        
        rules = []
        for row in result:
            rules.append({
                "id": str(row[0]),
                "name": row[1],
                "target_id": str(row[2]),
                "source_metric": row[3],
                "labels_filter": json.loads(row[4]) if row[4] else {},
                "aggregation": row[5],
                "group_by": row[6],
                "interval_seconds": row[7],
                "enabled": bool(row[8]),
                "description": row[9],
                "last_evaluated": row[10],
                "created_at": row[11],
                "updated_at": row[12]
            })
        
        return {"rules": rules}
    except Exception as e:
        logger.error(f"Failed to list recording rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_recording_rule(rule: RecordingRuleCreate):
    """Create a new recording rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        labels_json = json.dumps(rule.labels_filter or {})
        
        client.client.execute("""
            INSERT INTO recording_rules (
                name, target_id, source_metric, labels_filter,
                aggregation, group_by, interval_seconds, description
            ) VALUES
        """, [{
            "name": rule.name,
            "target_id": rule.target_id,
            "source_metric": rule.source_metric,
            "labels_filter": labels_json,
            "aggregation": rule.aggregation,
            "group_by": rule.group_by or "",
            "interval_seconds": rule.interval_seconds,
            "description": rule.description or ""
        }])
        
        logger.info(f"Created recording rule: {rule.name}")
        return {"status": "created", "name": rule.name}
    except Exception as e:
        logger.error(f"Failed to create recording rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{rule_id}")
async def get_recording_rule(rule_id: str):
    """Get a specific recording rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        result = client.client.execute(f"""
            SELECT 
                id, name, target_id, source_metric, labels_filter,
                aggregation, group_by, interval_seconds, enabled,
                description, last_evaluated, created_at, updated_at
            FROM recording_rules
            WHERE id = toUUID('{rule_id}')
            LIMIT 1
        """)
        
        if not result:
            raise HTTPException(status_code=404, detail="Recording rule not found")
        
        row = result[0]
        return {
            "id": str(row[0]),
            "name": row[1],
            "target_id": str(row[2]),
            "source_metric": row[3],
            "labels_filter": json.loads(row[4]) if row[4] else {},
            "aggregation": row[5],
            "group_by": row[6],
            "interval_seconds": row[7],
            "enabled": bool(row[8]),
            "description": row[9],
            "last_evaluated": row[10],
            "created_at": row[11],
            "updated_at": row[12]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recording rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{rule_id}")
async def update_recording_rule(rule_id: str, update: RecordingRuleUpdate):
    """Update a recording rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Build update fields
        updates = ["updated_at = now()"]
        
        if update.name is not None:
            updates.append(f"name = '{update.name}'")
        if update.source_metric is not None:
            updates.append(f"source_metric = '{update.source_metric}'")
        if update.labels_filter is not None:
            updates.append(f"labels_filter = '{json.dumps(update.labels_filter)}'")
        if update.aggregation is not None:
            updates.append(f"aggregation = '{update.aggregation}'")
        if update.group_by is not None:
            updates.append(f"group_by = '{update.group_by}'")
        if update.interval_seconds is not None:
            updates.append(f"interval_seconds = {update.interval_seconds}")
        if update.description is not None:
            updates.append(f"description = '{update.description}'")
        if update.enabled is not None:
            updates.append(f"enabled = {1 if update.enabled else 0}")
        
        update_clause = ", ".join(updates)
        
        client.client.execute(f"""
            ALTER TABLE recording_rules
            UPDATE {update_clause}
            WHERE id = toUUID('{rule_id}')
        """)
        
        logger.info(f"Updated recording rule: {rule_id}")
        return {"status": "updated", "id": rule_id}
    except Exception as e:
        logger.error(f"Failed to update recording rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{rule_id}")
async def delete_recording_rule(rule_id: str):
    """Delete a recording rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        client.client.execute(f"""
            ALTER TABLE recording_rules
            DELETE WHERE id = toUUID('{rule_id}')
        """)
        
        # Also delete recorded metrics for this rule
        client.client.execute(f"""
            ALTER TABLE recorded_metrics
            DELETE WHERE rule_id = toUUID('{rule_id}')
        """)
        
        logger.info(f"Deleted recording rule and its metrics: {rule_id}")
        return {"status": "deleted", "id": rule_id}
    except Exception as e:
        logger.error(f"Failed to delete recording rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{rule_id}/evaluate")
async def evaluate_recording_rule_now(rule_id: str):
    """Manually trigger evaluation of a recording rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Get the rule
        result = client.client.execute(f"""
            SELECT id, name, target_id, source_metric, labels_filter, aggregation, group_by
            FROM recording_rules
            WHERE id = toUUID('{rule_id}') AND enabled = 1
            LIMIT 1
        """)
        
        if not result:
            raise HTTPException(status_code=404, detail="Recording rule not found or disabled")
        
        row = result[0]
        rule = {
            "id": str(row[0]),
            "name": row[1],
            "target_id": str(row[2]),
            "source_metric": row[3],
            "labels_filter": json.loads(row[4]) if row[4] else {},
            "aggregation": row[5],
            "group_by": row[6]
        }
        
        # Evaluate the rule
        value = await _evaluate_rule(client, rule)
        
        return {"status": "evaluated", "rule_id": rule_id, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to evaluate recording rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{rule_id}/series")
async def get_recorded_series(
    rule_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None
):
    """Get the pre-aggregated time series data for a recording rule"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        if not end:
            end = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not start:
            start = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        
        result = client.client.execute(f"""
            SELECT 
                toString(toStartOfMinute(timestamp)) as ts,
                group_labels,
                avg(value) as value
            FROM recorded_metrics
            WHERE rule_id = toUUID('{rule_id}')
              AND timestamp >= toDateTime('{start}')
              AND timestamp <= toDateTime('{end}')
            GROUP BY ts, group_labels
            ORDER BY ts
        """)
        
        data = []
        for row in result:
            data.append({
                "timestamp": row[0],
                "group_labels": json.loads(row[1]) if row[1] else {},
                "value": row[2]
            })
        
        return {"data": data, "rule_id": rule_id}
    except Exception as e:
        logger.error(f"Failed to get recorded series: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Background Evaluator
async def _evaluate_rule(client, rule: dict) -> float:
    """Evaluate a single recording rule and store the result"""
    try:
        target_id = rule["target_id"]
        metric_name = rule["source_metric"]
        aggregation = rule["aggregation"]
        labels_filter = rule.get("labels_filter", {})
        group_by = rule.get("group_by", "")
        
        # Build label conditions
        label_conditions = ""
        if labels_filter:
            for key, value in labels_filter.items():
                safe_value = str(value).replace("'", "\\'")
                label_conditions += f" AND JSONExtractString(labels, '{key}') = '{safe_value}'"
        
        # Build group by clause - ONLY include actual dimension columns, NOT aggregates
        group_by_select = ""
        group_by_clause = ""
        if group_by:
            group_keys = [k.strip() for k in group_by.split(",") if k.strip()]
            if group_keys:
                group_by_select = ", " + ", ".join([f"JSONExtractString(labels, '{k}') as {k}" for k in group_keys])
                # GROUP BY the extracted label columns, not positional references that might be aggregates
                group_by_clause = "GROUP BY " + ", ".join([f"JSONExtractString(labels, '{k}')" for k in group_keys])
        
        # Query the source data (last minute)
        end = datetime.now()
        start = end - timedelta(minutes=1)
        
        # Build the query - note: if no group_by, we just aggregate with no GROUP BY clause
        # If group_by exists, GROUP BY the dimension columns ONLY (not the aggregate)
        query = f"""
            SELECT 
                {aggregation}(value) as agg_value
                {group_by_select}
            FROM scraped_metrics
            WHERE target_id = toUUID('{target_id}')
              AND metric_name = '{metric_name}'
              AND timestamp >= toDateTime('{start.strftime('%Y-%m-%d %H:%M:%S')}')
              AND timestamp <= toDateTime('{end.strftime('%Y-%m-%d %H:%M:%S')}')
              {label_conditions}
            {group_by_clause}
        """
        
        result = client.client.execute(query)
        
        if not result:
            return None
        
        # Store the recorded metric(s)
        now = datetime.now()
        for row in result:
            value = row[0]
            group_labels = {}
            
            if group_by:
                group_keys = [k.strip() for k in group_by.split(",") if k.strip()]
                for i, key in enumerate(group_keys):
                    if i + 1 < len(row):
                        group_labels[key] = row[i + 1]
            
            client.client.execute("""
                INSERT INTO recorded_metrics (timestamp, rule_id, rule_name, group_labels, value)
                VALUES
            """, [{
                "timestamp": now,
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "group_labels": json.dumps(group_labels),
                "value": value
            }])
        
        # Update last_evaluated timestamp
        client.client.execute(f"""
            ALTER TABLE recording_rules
            UPDATE last_evaluated = now()
            WHERE id = toUUID('{rule["id"]}')
        """)
        
        logger.debug(f"Evaluated recording rule {rule['name']}: {result[0][0] if result else 'no data'}")
        return result[0][0] if result else None
        
    except Exception as e:
        logger.error(f"Failed to evaluate rule {rule.get('name', 'unknown')}: {e}")
        return None

async def run_recording_rules_evaluator():
    """Background task to periodically evaluate all enabled recording rules"""
    logger.info("Starting recording rules evaluator...")
    
    while True:
        try:
            client = get_clickhouse_client()
            if not client:
                await asyncio.sleep(30)
                continue
            
            # Get all enabled rules that need evaluation
            now = datetime.now()
            
            result = client.client.execute("""
                SELECT 
                    id, name, target_id, source_metric, labels_filter,
                    aggregation, group_by, interval_seconds, last_evaluated
                FROM recording_rules
                WHERE enabled = 1
            """)
            
            for row in result:
                rule = {
                    "id": str(row[0]),
                    "name": row[1],
                    "target_id": str(row[2]),
                    "source_metric": row[3],
                    "labels_filter": json.loads(row[4]) if row[4] else {},
                    "aggregation": row[5],
                    "group_by": row[6],
                    "interval_seconds": row[7],
                    "last_evaluated": row[8]
                }
                
                # Check if it's time to evaluate this rule
                if rule["last_evaluated"]:
                    next_eval = rule["last_evaluated"] + timedelta(seconds=rule["interval_seconds"])
                    if now < next_eval:
                        continue
                
                # Evaluate the rule
                await _evaluate_rule(client, rule)
            
            # Sleep for 10 seconds before checking again
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Recording rules evaluator error: {e}")
            await asyncio.sleep(30)
