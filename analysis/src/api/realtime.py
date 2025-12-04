"""
Real-time WebSocket endpoints for streaming metrics and alerts
"""
import asyncio
import json
import logging
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.timezone import now

logger = logging.getLogger(__name__)

router = APIRouter()

# Global connection managers
class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients"""
        if not self.active_connections:
            return
        
        disconnected = set()
        message_json = json.dumps(message)
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_personal(self, message: dict, websocket: WebSocket):
        """Send a message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)


# Create global connection managers
metrics_manager = ConnectionManager()
alerts_manager = ConnectionManager()


@router.websocket("/ws/metrics")
async def websocket_metrics_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time metrics streaming
    
    Clients connect here to receive live metric updates as they're ingested from NATS
    """
    await metrics_manager.connect(websocket)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "timestamp": now().isoformat(),
            "message": "Connected to metrics stream"
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive messages from client (e.g., subscription preferences)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Parse and handle client requests
                try:
                    request = json.loads(data)
                    if request.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": now().isoformat()})
                    elif request.get("type") == "subscribe":
                        # Handle subscription to specific metrics
                        hostname = request.get("hostname")
                        await websocket.send_json({
                            "type": "subscribed",
                            "hostname": hostname,
                            "timestamp": now().isoformat()
                        })
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {data}")
                    
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": now().isoformat()
                })
                
    except WebSocketDisconnect:
        metrics_manager.disconnect(websocket)
        logger.info("Client disconnected from metrics stream")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        metrics_manager.disconnect(websocket)


@router.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time alerts
    
    Clients connect here to receive instant alerts when anomalies are detected
    """
    await alerts_manager.connect(websocket)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "timestamp": now().isoformat(),
            "message": "Connected to alerts stream"
        })
        
        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Handle ping/pong
                try:
                    request = json.loads(data)
                    if request.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": now().isoformat()})
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": now().isoformat()
                })
                
    except WebSocketDisconnect:
        alerts_manager.disconnect(websocket)
        logger.info("Client disconnected from alerts stream")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        alerts_manager.disconnect(websocket)


async def broadcast_metric(metric: dict):
    """
    Broadcast a metric update to all connected clients
    
    Call this function from the ingestion gateway when new metrics arrive
    """
    await metrics_manager.broadcast({
        "type": "metric",
        "data": metric,
        "timestamp": now().isoformat()
    })


async def broadcast_alert(alert: dict):
    """
    Broadcast an alert to all connected clients
    
    Call this function when an anomaly or threshold breach is detected
    """
    await alerts_manager.broadcast({
        "type": "alert",
        "data": alert,
        "timestamp": now().isoformat()
    })


def get_connection_stats():
    """Get statistics about active WebSocket connections"""
    return {
        "metrics_connections": len(metrics_manager.active_connections),
        "alerts_connections": len(alerts_manager.active_connections),
        "total_connections": len(metrics_manager.active_connections) + len(alerts_manager.active_connections)
    }

