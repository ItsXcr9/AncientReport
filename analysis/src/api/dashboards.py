"""
Dashboard API - CRUD for custom dashboards and panels
Stores dashboard configurations in ClickHouse
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging
import uuid

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


# Pydantic models
class DashboardCreate(BaseModel):
    name: str
    description: str = ""

class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class PanelCreate(BaseModel):
    title: str
    target_id: str
    metric_name: str
    chart_type: str = "area"
    color: str = "#00F3FF"
    time_range: str = "1h"

class Dashboard(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    panel_count: int = 0

class Panel(BaseModel):
    id: str
    dashboard_id: str
    title: str
    target_id: str
    metric_name: str
    chart_type: str
    color: str
    position: int
    time_range: str
    created_at: datetime


# Dashboard CRUD
@router.get("", response_model=List[Dashboard])
async def list_dashboards():
    """List all dashboards with panel counts"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        query = """
            SELECT 
                d.id, d.name, d.description, d.created_at, d.updated_at,
                count(p.id) as panel_count
            FROM dashboards d FINAL
            LEFT JOIN dashboard_panels p ON d.id = p.dashboard_id
            GROUP BY d.id, d.name, d.description, d.created_at, d.updated_at
            ORDER BY d.updated_at DESC
        """
        rows = client.client.execute(query)
        return [
            Dashboard(
                id=str(row[0]),
                name=row[1],
                description=row[2],
                created_at=row[3],
                updated_at=row[4],
                panel_count=row[5]
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list dashboards: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=Dashboard)
async def create_dashboard(data: DashboardCreate):
    """Create a new dashboard"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        dashboard_id = str(uuid.uuid4())
        now = datetime.now()
        
        query = f"""
            INSERT INTO dashboards (id, name, description, created_at, updated_at)
            VALUES (
                toUUID('{dashboard_id}'),
                '{data.name.replace("'", "''")}',
                '{data.description.replace("'", "''")}',
                now(),
                now()
            )
        """
        client.client.execute(query)
        
        return Dashboard(
            id=dashboard_id,
            name=data.name,
            description=data.description,
            created_at=now,
            updated_at=now,
            panel_count=0
        )
    except Exception as e:
        logger.error(f"Failed to create dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str):
    """Get a dashboard with all its panels"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Get dashboard
        dash_query = f"""
            SELECT id, name, description, created_at, updated_at
            FROM dashboards FINAL
            WHERE id = toUUID('{dashboard_id}')
        """
        dash_rows = client.client.execute(dash_query)
        
        if not dash_rows:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        row = dash_rows[0]
        
        # Get panels
        panel_query = f"""
            SELECT id, dashboard_id, title, target_id, metric_name, 
                   chart_type, color, position, time_range, created_at
            FROM dashboard_panels
            WHERE dashboard_id = toUUID('{dashboard_id}')
            ORDER BY position
        """
        panel_rows = client.client.execute(panel_query)
        
        panels = [
            Panel(
                id=str(p[0]),
                dashboard_id=str(p[1]),
                title=p[2],
                target_id=str(p[3]),
                metric_name=p[4],
                chart_type=p[5],
                color=p[6],
                position=p[7],
                time_range=p[8],
                created_at=p[9]
            )
            for p in panel_rows
        ]
        
        return {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "created_at": row[3].isoformat(),
            "updated_at": row[4].isoformat(),
            "panels": [p.dict() for p in panels]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{dashboard_id}", response_model=Dashboard)
async def update_dashboard(dashboard_id: str, data: DashboardUpdate):
    """Update a dashboard"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Fetch existing dashboard first
        fetch_query = f"""
            SELECT name, description, created_at
            FROM dashboards FINAL
            WHERE id = toUUID('{dashboard_id}')
        """
        existing = client.client.execute(fetch_query)
        
        if not existing:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        row = existing[0]
        name = data.name if data.name else row[0]
        description = data.description if data.description else row[1]
        created_at = row[2]
        
        # Insert updated row (ReplacingMergeTree handles deduplication)
        insert_query = f"""
            INSERT INTO dashboards (id, name, description, created_at, updated_at)
            VALUES (
                toUUID('{dashboard_id}'),
                '{name.replace("'", "''")}',
                '{description.replace("'", "''")}',
                '{created_at.strftime('%Y-%m-%d %H:%M:%S')}',
                now()
            )
        """
        client.client.execute(insert_query)
        
        now = datetime.now()
        return Dashboard(
            id=dashboard_id,
            name=name,
            description=description,
            created_at=created_at,
            updated_at=now,
            panel_count=0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str):
    """Delete a dashboard and all its panels"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Delete panels first
        client.client.execute(f"""
            ALTER TABLE dashboard_panels DELETE 
            WHERE dashboard_id = toUUID('{dashboard_id}')
        """)
        
        # Delete dashboard
        client.client.execute(f"""
            ALTER TABLE dashboards DELETE 
            WHERE id = toUUID('{dashboard_id}')
        """)
        
        return {"status": "deleted", "id": dashboard_id}
    except Exception as e:
        logger.error(f"Failed to delete dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Panel CRUD
@router.post("/{dashboard_id}/panels", response_model=Panel)
async def add_panel(dashboard_id: str, data: PanelCreate):
    """Add a panel to a dashboard"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        # Get max position
        pos_query = f"""
            SELECT max(position) FROM dashboard_panels
            WHERE dashboard_id = toUUID('{dashboard_id}')
        """
        pos_result = client.client.execute(pos_query)
        next_pos = (pos_result[0][0] or 0) + 1
        
        panel_id = str(uuid.uuid4())
        now = datetime.now()
        
        query = f"""
            INSERT INTO dashboard_panels 
            (id, dashboard_id, title, target_id, metric_name, chart_type, color, position, time_range, created_at)
            VALUES (
                toUUID('{panel_id}'),
                toUUID('{dashboard_id}'),
                '{data.title.replace("'", "''")}',
                toUUID('{data.target_id}'),
                '{data.metric_name.replace("'", "''")}',
                '{data.chart_type}',
                '{data.color}',
                {next_pos},
                '{data.time_range}',
                now()
            )
        """
        client.client.execute(query)
        
        return Panel(
            id=panel_id,
            dashboard_id=dashboard_id,
            title=data.title,
            target_id=data.target_id,
            metric_name=data.metric_name,
            chart_type=data.chart_type,
            color=data.color,
            position=next_pos,
            time_range=data.time_range,
            created_at=now
        )
    except Exception as e:
        logger.error(f"Failed to add panel: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{dashboard_id}/panels/{panel_id}")
async def delete_panel(dashboard_id: str, panel_id: str):
    """Delete a panel from a dashboard"""
    client = get_clickhouse_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    try:
        client.client.execute(f"""
            ALTER TABLE dashboard_panels DELETE 
            WHERE id = toUUID('{panel_id}') AND dashboard_id = toUUID('{dashboard_id}')
        """)
        
        return {"status": "deleted", "panel_id": panel_id}
    except Exception as e:
        logger.error(f"Failed to delete panel: {e}")
        raise HTTPException(status_code=500, detail=str(e))
