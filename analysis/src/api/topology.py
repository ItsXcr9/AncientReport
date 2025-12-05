"""
Container Topology API - Phase 4
Provides endpoints for container discovery, connection mapping, and topology visualization.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime
import asyncio
import json

router = APIRouter(prefix="/api/v3/topology")


# Data Models
class ContainerNode(BaseModel):
    id: str
    name: str
    image: str
    status: str  # running, stopped, paused
    health: str  # healthy, warning, critical, unknown
    networks: List[str]
    ports: List[str]
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    created_at: Optional[str] = None


class ConnectionEdge(BaseModel):
    id: str
    source: str  # container_id
    target: str  # container_id or external
    source_port: int
    target_port: int
    protocol: str  # tcp, udp
    bytes_sent: int = 0
    bytes_received: int = 0
    latency_ms: float = 0.0
    status: str  # active, slow, failed
    requests_per_sec: float = 0.0


class TopologyProblem(BaseModel):
    id: str
    type: str  # connection_failed, high_latency, unreachable
    severity: str  # warning, critical
    source_container: str
    target: str
    message: str
    detected_at: str


class TopologyMap(BaseModel):
    nodes: List[ContainerNode]
    edges: List[ConnectionEdge]
    problems: List[TopologyProblem]
    last_updated: str


# In-memory cache for topology data (would be ClickHouse in production)
topology_cache: Dict[str, Any] = {
    "nodes": [],
    "edges": [],
    "problems": [],
    "last_updated": None
}


async def discover_containers() -> List[ContainerNode]:
    """
    Discover running containers and their metadata.
    In production, this would query Docker API and ClickHouse.
    """
    # Simulated container discovery - replace with actual Docker API calls
    containers = [
        ContainerNode(
            id="nginx-1",
            name="ancientreport-ui",
            image="nginx:1.27-alpine",
            status="running",
            health="healthy",
            networks=["ancientreport_default"],
            ports=["3000:3000"],
            cpu_percent=2.5,
            memory_mb=45.2,
        ),
        ContainerNode(
            id="analysis-1",
            name="ancientreport-analysis",
            image="ancientreport-analysis:latest",
            status="running",
            health="healthy",
            networks=["ancientreport_default"],
            ports=["8800:8800"],
            cpu_percent=15.3,
            memory_mb=256.8,
        ),
        ContainerNode(
            id="agent-1",
            name="ancientreport-agent",
            image="ancientreport-agent:latest",
            status="running",
            health="healthy",
            networks=["ancientreport_default", "host"],
            ports=[],
            cpu_percent=8.1,
            memory_mb=128.4,
        ),
        ContainerNode(
            id="clickhouse-1",
            name="ancientreport-clickhouse",
            image="clickhouse/clickhouse-server:latest",
            status="running",
            health="healthy",
            networks=["ancientreport_default"],
            ports=["8123:8123", "9000:9000"],
            cpu_percent=5.2,
            memory_mb=512.0,
        ),
        ContainerNode(
            id="nats-1",
            name="ancientreport-nats",
            image="nats:latest",
            status="running",
            health="healthy",
            networks=["ancientreport_default"],
            ports=["4222:4222"],
            cpu_percent=1.2,
            memory_mb=32.5,
        ),
    ]
    return containers


async def discover_connections() -> List[ConnectionEdge]:
    """
    Discover inter-container connections.
    In production, this would use eBPF network flow data from ClickHouse.
    """
    connections = [
        # UI -> Analysis (HTTP API calls)
        ConnectionEdge(
            id="edge-ui-analysis",
            source="nginx-1",
            target="analysis-1",
            source_port=3000,
            target_port=8800,
            protocol="tcp",
            bytes_sent=1024000,
            bytes_received=5120000,
            latency_ms=2.5,
            status="active",
            requests_per_sec=45.2,
        ),
        # Analysis -> ClickHouse (database queries)
        ConnectionEdge(
            id="edge-analysis-ch",
            source="analysis-1",
            target="clickhouse-1",
            source_port=8800,
            target_port=9000,
            protocol="tcp",
            bytes_sent=512000,
            bytes_received=2048000,
            latency_ms=1.2,
            status="active",
            requests_per_sec=120.5,
        ),
        # Analysis -> NATS (message streaming)
        ConnectionEdge(
            id="edge-analysis-nats",
            source="analysis-1",
            target="nats-1",
            source_port=8800,
            target_port=4222,
            protocol="tcp",
            bytes_sent=256000,
            bytes_received=1024000,
            latency_ms=0.8,
            status="active",
            requests_per_sec=200.0,
        ),
        # Agent -> NATS (metrics publishing)
        ConnectionEdge(
            id="edge-agent-nats",
            source="agent-1",
            target="nats-1",
            source_port=0,
            target_port=4222,
            protocol="tcp",
            bytes_sent=2048000,
            bytes_received=128000,
            latency_ms=1.0,
            status="active",
            requests_per_sec=60.0,
        ),
        # Agent -> ClickHouse (direct metrics insert)
        ConnectionEdge(
            id="edge-agent-ch",
            source="agent-1",
            target="clickhouse-1",
            source_port=0,
            target_port=8123,
            protocol="tcp",
            bytes_sent=4096000,
            bytes_received=64000,
            latency_ms=3.5,
            status="active",
            requests_per_sec=10.0,
        ),
    ]
    return connections


async def detect_problems(nodes: List[ContainerNode], edges: List[ConnectionEdge]) -> List[TopologyProblem]:
    """
    Detect topology problems like failed connections, high latency, etc.
    """
    problems = []
    
    for edge in edges:
        # High latency detection
        if edge.latency_ms > 100:
            problems.append(TopologyProblem(
                id=f"prob-{edge.id}-latency",
                type="high_latency",
                severity="warning" if edge.latency_ms < 500 else "critical",
                source_container=edge.source,
                target=edge.target,
                message=f"High latency: {edge.latency_ms:.1f}ms",
                detected_at=datetime.utcnow().isoformat(),
            ))
        
        # Failed connection detection
        if edge.status == "failed":
            problems.append(TopologyProblem(
                id=f"prob-{edge.id}-failed",
                type="connection_failed",
                severity="critical",
                source_container=edge.source,
                target=edge.target,
                message="Connection failed",
                detected_at=datetime.utcnow().isoformat(),
            ))
    
    # Check for unhealthy containers
    for node in nodes:
        if node.health == "critical":
            problems.append(TopologyProblem(
                id=f"prob-{node.id}-health",
                type="container_unhealthy",
                severity="critical",
                source_container=node.id,
                target="",
                message=f"Container {node.name} is unhealthy",
                detected_at=datetime.utcnow().isoformat(),
            ))
    
    return problems


@router.get("/map", response_model=TopologyMap)
async def get_topology_map():
    """
    Get the full container topology map with nodes, edges, and problems.
    """
    nodes = await discover_containers()
    edges = await discover_connections()
    problems = await detect_problems(nodes, edges)
    
    return TopologyMap(
        nodes=nodes,
        edges=edges,
        problems=problems,
        last_updated=datetime.utcnow().isoformat(),
    )


@router.get("/container/{container_id}")
async def get_container_details(container_id: str):
    """
    Get detailed information about a specific container and its connections.
    """
    nodes = await discover_containers()
    edges = await discover_connections()
    
    container = next((n for n in nodes if n.id == container_id), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    
    # Get connections involving this container
    incoming = [e for e in edges if e.target == container_id]
    outgoing = [e for e in edges if e.source == container_id]
    
    return {
        "container": container,
        "incoming_connections": incoming,
        "outgoing_connections": outgoing,
        "total_bytes_in": sum(e.bytes_received for e in incoming),
        "total_bytes_out": sum(e.bytes_sent for e in outgoing),
    }


@router.get("/problems")
async def get_topology_problems():
    """
    Get all current topology problems.
    """
    nodes = await discover_containers()
    edges = await discover_connections()
    problems = await detect_problems(nodes, edges)
    
    return {
        "total": len(problems),
        "critical": len([p for p in problems if p.severity == "critical"]),
        "warning": len([p for p in problems if p.severity == "warning"]),
        "problems": problems,
    }


@router.get("/stats")
async def get_topology_stats():
    """
    Get topology statistics summary.
    """
    nodes = await discover_containers()
    edges = await discover_connections()
    
    return {
        "total_containers": len(nodes),
        "running": len([n for n in nodes if n.status == "running"]),
        "healthy": len([n for n in nodes if n.health == "healthy"]),
        "total_connections": len(edges),
        "active_connections": len([e for e in edges if e.status == "active"]),
        "total_traffic_bytes": sum(e.bytes_sent + e.bytes_received for e in edges),
    }
