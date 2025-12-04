"""
Alert Rules API for AncientReport V3
CRUD operations for alert rules and history
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/v3/alerts", tags=["V3 Alerts"])


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CreateRuleRequest(BaseModel):
    """Request to create an alert rule"""
    name: str = Field(..., min_length=1, max_length=100)
    condition: str = Field(..., description="DSL condition like 'cpu > 90'")
    severity: Severity = Severity.WARNING
    channels: List[str] = Field(default=["telegram"])
    cooldown_minutes: int = Field(default=15, ge=1, le=1440)
    enabled: bool = True


class RuleResponse(BaseModel):
    """Alert rule response"""
    id: str
    name: str
    condition: str
    severity: Severity
    channels: List[str]
    cooldown_minutes: int
    enabled: bool
    created_at: str
    updated_at: str


class AlertHistoryItem(BaseModel):
    """Alert history entry"""
    timestamp: str
    rule_id: str
    rule_name: str
    hostname: str
    severity: Severity
    message: str
    channels_notified: List[str]
    acknowledged: bool
    resolved: bool


# In-memory storage (will be replaced with ClickHouse)
rules_db: Dict[str, dict] = {}
history_db: List[dict] = []


@router.get("/rules", response_model=List[RuleResponse])
async def list_rules(enabled_only: bool = False):
    """List all alert rules"""
    rules = list(rules_db.values())
    if enabled_only:
        rules = [r for r in rules if r["enabled"]]
    return [RuleResponse(**r) for r in rules]


@router.post("/rules", response_model=RuleResponse)
async def create_rule(request: CreateRuleRequest):
    """Create a new alert rule"""
    rule_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    rule = {
        "id": rule_id,
        "name": request.name,
        "condition": request.condition,
        "severity": request.severity,
        "channels": request.channels,
        "cooldown_minutes": request.cooldown_minutes,
        "enabled": request.enabled,
        "created_at": now,
        "updated_at": now,
    }
    
    rules_db[rule_id] = rule
    return RuleResponse(**rule)


@router.get("/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: str):
    """Get a specific rule"""
    if rule_id not in rules_db:
        raise HTTPException(status_code=404, detail="Rule not found")
    return RuleResponse(**rules_db[rule_id])


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: str, request: CreateRuleRequest):
    """Update an existing rule"""
    if rule_id not in rules_db:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    rule = rules_db[rule_id]
    rule.update({
        "name": request.name,
        "condition": request.condition,
        "severity": request.severity,
        "channels": request.channels,
        "cooldown_minutes": request.cooldown_minutes,
        "enabled": request.enabled,
        "updated_at": datetime.utcnow().isoformat(),
    })
    
    return RuleResponse(**rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a rule"""
    if rule_id not in rules_db:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    del rules_db[rule_id]
    return {"status": "deleted", "id": rule_id}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str):
    """Toggle rule enabled state"""
    if rule_id not in rules_db:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    rule = rules_db[rule_id]
    rule["enabled"] = not rule["enabled"]
    rule["updated_at"] = datetime.utcnow().isoformat()
    
    return {"id": rule_id, "enabled": rule["enabled"]}


@router.get("/history", response_model=List[AlertHistoryItem])
async def get_alert_history(
    hostname: Optional[str] = None,
    severity: Optional[Severity] = None,
    acknowledged: Optional[bool] = None,
    resolved: Optional[bool] = None,
    limit: int = Query(default=50, ge=1, le=500)
):
    """Get alert history"""
    history = history_db.copy()
    
    if hostname:
        history = [h for h in history if h["hostname"] == hostname]
    if severity:
        history = [h for h in history if h["severity"] == severity]
    if acknowledged is not None:
        history = [h for h in history if h["acknowledged"] == acknowledged]
    if resolved is not None:
        history = [h for h in history if h["resolved"] == resolved]
    
    # Sort by timestamp descending
    history.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return [AlertHistoryItem(**h) for h in history[:limit]]


@router.post("/history/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, user: str = "admin"):
    """Acknowledge an alert"""
    # TODO: Update in ClickHouse
    return {"status": "acknowledged", "id": alert_id, "by": user}


@router.post("/history/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Mark an alert as resolved"""
    # TODO: Update in ClickHouse
    return {"status": "resolved", "id": alert_id}


@router.get("/channels")
async def list_channels():
    """List available notification channels and their status"""
    # TODO: Get from dispatcher
    return {
        "available": ["telegram", "slack", "email", "webhook"],
        "configured": {
            "telegram": True,
            "slack": False,
            "email": False,
            "webhook": False,
        }
    }


@router.post("/test/{channel}")
async def test_channel(channel: str):
    """Send a test alert to a specific channel"""
    # TODO: Implement test alert
    return {
        "status": "sent",
        "channel": channel,
        "message": "Test alert sent successfully"
    }
