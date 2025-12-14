"""
SLO API - Service Level Objective Tracking
Tracks SLI compliance, error budgets, and burn rates
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
router = APIRouter(prefix="/api/slo", tags=["SLO Tracking"])


# ============================================
# Models
# ============================================

class SLOCreate(BaseModel):
    name: str
    service: str
    description: str = ""
    sli_type: str = "availability"  # availability, latency, throughput, custom
    sli_metric: str = ""
    sli_good_query: str = ""  # Custom query for good events
    sli_total_query: str = ""  # Custom query for total events
    target: float  # 0.0 to 1.0, e.g., 0.999 for 99.9%
    window_days: int = 30
    burn_rate_threshold: float = 10.0


class SLOUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target: Optional[float] = None
    window_days: Optional[int] = None
    burn_rate_threshold: Optional[float] = None
    enabled: Optional[bool] = None


class SLO(BaseModel):
    id: str
    name: str
    service: str
    description: str
    sli_type: str
    sli_metric: str
    target: float
    window_days: int
    burn_rate_threshold: float
    enabled: bool
    created_at: str
    # Current status
    current_sli: Optional[float] = None
    error_budget_remaining_pct: Optional[float] = None
    burn_rate: Optional[float] = None
    is_breached: bool = False


class SLOStatusHistory(BaseModel):
    timestamp: str
    current_sli: float
    target: float
    error_budget_consumed_pct: float
    burn_rate: float
    is_breached: bool
    events_total: int
    events_good: int


# ============================================
# SLI Calculation Helpers
# ============================================

async def calculate_availability_sli(client, service: str, window_days: int) -> dict:
    """Calculate availability SLI from synthetic monitor results"""
    query = f"""
        SELECT 
            count() as total,
            countIf(success = 1) as good
        FROM synthetic_results
        WHERE monitor_name LIKE '%{service}%'
          AND timestamp >= now() - INTERVAL {window_days} DAY
    """
    try:
        result = client.client.execute(query)
        if result and result[0][0] > 0:
            total = result[0][0]
            good = result[0][1]
            return {"total": total, "good": good, "sli": good / total}
    except:
        pass
    return {"total": 0, "good": 0, "sli": 1.0}


async def calculate_latency_sli(client, service: str, window_days: int, threshold_ms: float = 200) -> dict:
    """Calculate latency SLI (percentage of requests under threshold)"""
    query = f"""
        SELECT 
            count() as total,
            countIf(latency_ms < {threshold_ms}) as good
        FROM synthetic_results
        WHERE monitor_name LIKE '%{service}%'
          AND timestamp >= now() - INTERVAL {window_days} DAY
    """
    try:
        result = client.client.execute(query)
        if result and result[0][0] > 0:
            total = result[0][0]
            good = result[0][1]
            return {"total": total, "good": good, "sli": good / total}
    except:
        pass
    return {"total": 0, "good": 0, "sli": 1.0}


async def calculate_custom_sli(client, good_query: str, total_query: str) -> dict:
    """Calculate SLI from custom queries"""
    try:
        good_result = client.client.execute(good_query)
        total_result = client.client.execute(total_query)
        
        good = good_result[0][0] if good_result else 0
        total = total_result[0][0] if total_result else 0
        
        sli = good / total if total > 0 else 1.0
        return {"total": total, "good": good, "sli": sli}
    except Exception as e:
        logger.error(f"Custom SLI query failed: {e}")
        return {"total": 0, "good": 0, "sli": 1.0}


def calculate_error_budget(sli: float, target: float) -> dict:
    """Calculate error budget metrics"""
    if target >= 1.0:
        target = 0.9999
    
    # Error budget = 1 - target (e.g., 0.1% for 99.9% target)
    budget_total = 1.0 - target
    
    # Consumed = 1 - sli (actual errors)
    consumed = 1.0 - sli
    
    # Remaining budget
    remaining = max(0, budget_total - consumed)
    
    # Percentage consumed
    consumed_pct = (consumed / budget_total * 100) if budget_total > 0 else 0
    
    return {
        "budget_total": budget_total,
        "consumed": consumed,
        "remaining": remaining,
        "consumed_pct": min(100, consumed_pct),
        "remaining_pct": max(0, 100 - consumed_pct)
    }


def calculate_burn_rate(sli: float, target: float, window_hours: int) -> float:
    """Calculate burn rate (how fast we're consuming error budget)"""
    if target >= 1.0 or window_hours <= 0:
        return 0
    
    # Error rate
    error_rate = 1.0 - sli
    expected_error_rate = 1.0 - target
    
    # Burn rate = actual error rate / expected error rate
    burn_rate = error_rate / expected_error_rate if expected_error_rate > 0 else 0
    
    return burn_rate


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=List[SLO])
async def list_slos():
    """List all SLO definitions with current status"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = """
            SELECT 
                toString(id), name, service, description, sli_type, sli_metric,
                target, window_days, burn_rate_threshold, enabled, toString(created_at)
            FROM slo_definitions FINAL
            ORDER BY name
        """
        rows = client.client.execute(query)
        
        slos = []
        for row in rows:
            slo_id = row[0]
            
            # Get latest status
            status_query = f"""
                SELECT current_sli, error_budget_consumed_pct, burn_rate, is_breached
                FROM slo_status
                WHERE slo_id = toUUID('{slo_id}')
                ORDER BY timestamp DESC
                LIMIT 1
            """
            status = client.client.execute(status_query)
            
            current_sli = None
            error_budget_remaining = None
            burn_rate = None
            is_breached = False
            
            if status:
                current_sli = status[0][0]
                error_budget_remaining = 100 - status[0][1]
                burn_rate = status[0][2]
                is_breached = bool(status[0][3])
            
            slos.append(SLO(
                id=slo_id,
                name=row[1],
                service=row[2],
                description=row[3],
                sli_type=row[4],
                sli_metric=row[5],
                target=row[6],
                window_days=row[7],
                burn_rate_threshold=row[8],
                enabled=bool(row[9]),
                created_at=row[10],
                current_sli=current_sli,
                error_budget_remaining_pct=error_budget_remaining,
                burn_rate=burn_rate,
                is_breached=is_breached
            ))
        
        return slos
    except Exception as e:
        logger.error(f"Failed to list SLOs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=SLO)
async def create_slo(data: SLOCreate):
    """Create a new SLO definition"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        slo_id = str(uuid.uuid4())
        
        query = f"""
            INSERT INTO slo_definitions (
                id, name, service, description, sli_type, sli_metric,
                sli_good_query, sli_total_query, target, window_days, burn_rate_threshold
            ) VALUES (
                toUUID('{slo_id}'),
                '{data.name.replace("'", "''")}',
                '{data.service.replace("'", "''")}',
                '{data.description.replace("'", "''")}',
                '{data.sli_type}',
                '{data.sli_metric.replace("'", "''")}',
                '{data.sli_good_query.replace("'", "''")}',
                '{data.sli_total_query.replace("'", "''")}',
                {data.target},
                {data.window_days},
                {data.burn_rate_threshold}
            )
        """
        client.client.execute(query)
        
        return SLO(
            id=slo_id,
            name=data.name,
            service=data.service,
            description=data.description,
            sli_type=data.sli_type,
            sli_metric=data.sli_metric,
            target=data.target,
            window_days=data.window_days,
            burn_rate_threshold=data.burn_rate_threshold,
            enabled=True,
            created_at=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to create SLO: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slo_id}")
async def get_slo(slo_id: str):
    """Get SLO details with current status"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            SELECT 
                toString(id), name, service, description, sli_type, sli_metric,
                target, window_days, burn_rate_threshold, enabled, toString(created_at)
            FROM slo_definitions FINAL
            WHERE id = toUUID('{slo_id}')
        """
        rows = client.client.execute(query)
        
        if not rows:
            raise HTTPException(status_code=404, detail="SLO not found")
        
        row = rows[0]
        
        # Get latest status
        status_query = f"""
            SELECT current_sli, error_budget_consumed_pct, burn_rate, is_breached,
                   events_total, events_good
            FROM slo_status
            WHERE slo_id = toUUID('{slo_id}')
            ORDER BY timestamp DESC
            LIMIT 1
        """
        status = client.client.execute(status_query)
        
        result = {
            "id": row[0],
            "name": row[1],
            "service": row[2],
            "description": row[3],
            "sli_type": row[4],
            "sli_metric": row[5],
            "target": row[6],
            "window_days": row[7],
            "burn_rate_threshold": row[8],
            "enabled": bool(row[9]),
            "created_at": row[10]
        }
        
        if status:
            result["current_sli"] = status[0][0]
            result["error_budget_consumed_pct"] = status[0][1]
            result["error_budget_remaining_pct"] = 100 - status[0][1]
            result["burn_rate"] = status[0][2]
            result["is_breached"] = bool(status[0][3])
            result["events_total"] = status[0][4]
            result["events_good"] = status[0][5]
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get SLO: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slo_id}/history", response_model=List[SLOStatusHistory])
async def get_slo_history(slo_id: str, hours: int = 24):
    """Get SLO status history"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = f"""
            SELECT 
                toString(timestamp), current_sli, target, 
                error_budget_consumed_pct, burn_rate, is_breached,
                events_total, events_good
            FROM slo_status
            WHERE slo_id = toUUID('{slo_id}')
              AND timestamp >= now() - INTERVAL {hours} HOUR
            ORDER BY timestamp
        """
        rows = client.client.execute(query)
        
        return [
            SLOStatusHistory(
                timestamp=row[0],
                current_sli=row[1],
                target=row[2],
                error_budget_consumed_pct=row[3],
                burn_rate=row[4],
                is_breached=bool(row[5]),
                events_total=row[6],
                events_good=row[7]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to get SLO history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{slo_id}")
async def delete_slo(slo_id: str):
    """Delete an SLO"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        client.client.execute(f"ALTER TABLE slo_definitions DELETE WHERE id = toUUID('{slo_id}')")
        client.client.execute(f"ALTER TABLE slo_status DELETE WHERE slo_id = toUUID('{slo_id}')")
        return {"status": "deleted", "id": slo_id}
    except Exception as e:
        logger.error(f"Failed to delete SLO: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Background SLO Calculation
# ============================================

async def calculate_all_slos():
    """Calculate status for all enabled SLOs"""
    client = get_clickhouse_client()
    if not client:
        return
    
    try:
        query = """
            SELECT id, service, sli_type, sli_metric, sli_good_query, sli_total_query,
                   target, window_days, burn_rate_threshold
            FROM slo_definitions FINAL
            WHERE enabled = 1
        """
        slos = client.client.execute(query)
        
        for slo in slos:
            slo_id = str(slo[0])
            service = slo[1]
            sli_type = slo[2]
            sli_metric = slo[3]
            good_query = slo[4]
            total_query = slo[5]
            target = slo[6]
            window_days = slo[7]
            burn_rate_threshold = slo[8]
            
            # Calculate SLI based on type
            if sli_type == "custom" and good_query and total_query:
                sli_data = await calculate_custom_sli(client, good_query, total_query)
            elif sli_type == "latency":
                sli_data = await calculate_latency_sli(client, service, window_days)
            else:  # availability
                sli_data = await calculate_availability_sli(client, service, window_days)
            
            current_sli = sli_data["sli"]
            events_total = sli_data["total"]
            events_good = sli_data["good"]
            events_bad = events_total - events_good
            
            # Calculate error budget
            budget = calculate_error_budget(current_sli, target)
            
            # Calculate burn rate (using 1-hour window)
            burn_rate = calculate_burn_rate(current_sli, target, 1)
            
            # Check if breached
            is_breached = current_sli < target or budget["consumed_pct"] >= 100
            
            # Store status
            try:
                insert_query = f"""
                    INSERT INTO slo_status (
                        slo_id, current_sli, target, error_budget_total,
                        error_budget_remaining, error_budget_consumed_pct, burn_rate,
                        is_breached, events_total, events_good, events_bad
                    ) VALUES (
                        toUUID('{slo_id}'),
                        {current_sli},
                        {target},
                        {budget["budget_total"]},
                        {budget["remaining"]},
                        {budget["consumed_pct"]},
                        {burn_rate},
                        {1 if is_breached else 0},
                        {events_total},
                        {events_good},
                        {events_bad}
                    )
                """
                client.client.execute(insert_query)
            except Exception as e:
                logger.error(f"Failed to store SLO status: {e}")
    
    except Exception as e:
        logger.error(f"SLO calculation failed: {e}")


async def slo_calculation_loop():
    """Background loop for SLO calculations"""
    logger.info("Starting SLO calculation loop")
    while True:
        try:
            await calculate_all_slos()
        except Exception as e:
            logger.error(f"SLO calculation loop error: {e}")
        await asyncio.sleep(60)  # Run every minute
