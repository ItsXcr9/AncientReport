"""
eBPF Data API - Phase 3 Enhanced eBPF
Provides endpoints for accessing eBPF-collected metrics.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

router = APIRouter(prefix="/api/v3/ebpf")


class TcpConnection(BaseModel):
    pid: int
    process_name: str
    local_ip: str
    remote_ip: str
    local_port: int
    remote_port: int
    state: str
    rtt_us: int
    retransmits: int
    bytes_sent: int
    bytes_received: int
    container_id: Optional[str] = None


class ProcessFlow(BaseModel):
    pid: int
    process_name: str
    bytes_sent: int
    bytes_received: int
    packets_sent: int
    packets_received: int
    active_flows: int
    container_id: Optional[str] = None


class SyscallStats(BaseModel):
    pid: int
    process_name: str
    execve_count: int
    connect_count: int
    open_count: int
    socket_count: int
    mmap_exec_count: int
    ptrace_count: int
    total_count: int


class EbpfMetrics(BaseModel):
    tcp_connections: List[TcpConnection]
    process_flows: List[ProcessFlow]
    syscall_stats: List[SyscallStats]
    collection_time: str


# Simulated data (will be replaced with actual eBPF data from agent)
def get_simulated_data() -> EbpfMetrics:
    """Generate simulated eBPF data for development/testing."""
    import random
    
    tcp_connections = [
        TcpConnection(
            pid=1234,
            process_name="analysis",
            local_ip="172.18.0.3",
            remote_ip="172.18.0.5",
            local_port=8800,
            remote_port=9000,
            state="ESTABLISHED",
            rtt_us=1200,
            retransmits=0,
            bytes_sent=1024000,
            bytes_received=4096000,
            container_id="ancientreport-analysis"
        ),
        TcpConnection(
            pid=1235,
            process_name="nginx",
            local_ip="172.18.0.2",
            remote_ip="172.18.0.3",
            local_port=3000,
            remote_port=8800,
            state="ESTABLISHED",
            rtt_us=800,
            retransmits=0,
            bytes_sent=512000,
            bytes_received=2048000,
            container_id="ancientreport-ui"
        ),
        TcpConnection(
            pid=1236,
            process_name="agent",
            local_ip="172.18.0.4",
            remote_ip="172.18.0.6",
            local_port=random.randint(40000, 60000),
            remote_port=4222,
            state="ESTABLISHED",
            rtt_us=500,
            retransmits=0,
            bytes_sent=2048000,
            bytes_received=128000,
            container_id="ancientreport-agent"
        ),
    ]
    
    process_flows = [
        ProcessFlow(
            pid=1234,
            process_name="python3",
            bytes_sent=random.randint(100000, 500000),
            bytes_received=random.randint(500000, 2000000),
            packets_sent=random.randint(100, 500),
            packets_received=random.randint(500, 2000),
            active_flows=3,
            container_id="ancientreport-analysis"
        ),
        ProcessFlow(
            pid=1235,
            process_name="nginx",
            bytes_sent=random.randint(50000, 200000),
            bytes_received=random.randint(100000, 500000),
            packets_sent=random.randint(50, 200),
            packets_received=random.randint(100, 500),
            active_flows=10,
            container_id="ancientreport-ui"
        ),
        ProcessFlow(
            pid=1236,
            process_name="agent",
            bytes_sent=random.randint(200000, 800000),
            bytes_received=random.randint(50000, 200000),
            packets_sent=random.randint(200, 800),
            packets_received=random.randint(50, 200),
            active_flows=5,
            container_id="ancientreport-agent"
        ),
    ]
    
    syscall_stats = [
        SyscallStats(
            pid=1234,
            process_name="python3",
            execve_count=0,
            connect_count=random.randint(10, 50),
            open_count=random.randint(100, 500),
            socket_count=random.randint(5, 20),
            mmap_exec_count=random.randint(0, 5),
            ptrace_count=0,
            total_count=random.randint(1000, 5000)
        ),
        SyscallStats(
            pid=1235,
            process_name="nginx",
            execve_count=0,
            connect_count=random.randint(5, 30),
            open_count=random.randint(50, 200),
            socket_count=random.randint(10, 50),
            mmap_exec_count=0,
            ptrace_count=0,
            total_count=random.randint(500, 2000)
        ),
    ]
    
    return EbpfMetrics(
        tcp_connections=tcp_connections,
        process_flows=process_flows,
        syscall_stats=syscall_stats,
        collection_time=datetime.utcnow().isoformat()
    )


@router.get("/metrics")
async def get_ebpf_metrics() -> EbpfMetrics:
    """Get all eBPF metrics (TCP connections, flows, syscalls)."""
    return get_simulated_data()


@router.get("/tcp/connections")
async def get_tcp_connections() -> List[TcpConnection]:
    """Get active TCP connections tracked by eBPF."""
    return get_simulated_data().tcp_connections


@router.get("/flows/by-process")
async def get_process_flows() -> List[ProcessFlow]:
    """Get per-process network flow statistics."""
    return get_simulated_data().process_flows


@router.get("/syscalls/stats")
async def get_syscall_stats() -> List[SyscallStats]:
    """Get per-process syscall statistics."""
    return get_simulated_data().syscall_stats


@router.get("/flows/top-talkers")
async def get_top_talkers(limit: int = 10) -> List[ProcessFlow]:
    """Get top processes by network traffic."""
    flows = get_simulated_data().process_flows
    # Sort by total bytes (sent + received)
    sorted_flows = sorted(
        flows,
        key=lambda f: f.bytes_sent + f.bytes_received,
        reverse=True
    )
    return sorted_flows[:limit]


@router.get("/tcp/by-container/{container_id}")
async def get_connections_by_container(container_id: str) -> List[TcpConnection]:
    """Get TCP connections for a specific container."""
    all_connections = get_simulated_data().tcp_connections
    return [c for c in all_connections if c.container_id == container_id]


@router.get("/syscalls/suspicious")
async def get_suspicious_syscalls() -> List[SyscallStats]:
    """Get processes with suspicious syscall patterns."""
    stats = get_simulated_data().syscall_stats
    # Flag processes with ptrace or high exec counts
    suspicious = [s for s in stats if s.ptrace_count > 0 or s.mmap_exec_count > 10]
    return suspicious
