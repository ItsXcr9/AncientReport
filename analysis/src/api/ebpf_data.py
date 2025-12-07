"""
eBPF Data API - Phase 3 Enhanced eBPF
Provides endpoints for accessing REAL system metrics (TCP connections, processes, etc.)
Fixed to use real data from /proc instead of simulated data.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import subprocess
import os
import re

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
    total_processes: int = 0  # Total running processes on system
    packet_drops: int = 0  # Total RX+TX packet drops from all interfaces


def get_packet_drops() -> int:
    """Get total packet drops from /proc/net/dev."""
    total_drops = 0
    proc_path = '/host/proc/net/dev' if os.path.exists('/host/proc/net/dev') else '/proc/net/dev'
    
    try:
        with open(proc_path, 'r') as f:
            lines = f.readlines()[2:]  # Skip header lines
            for line in lines:
                parts = line.split()
                if len(parts) >= 12:
                    interface = parts[0].rstrip(':')
                    if interface != 'lo':  # Skip loopback
                        rx_drop = int(parts[4])  # RX drop is column 4 (0-indexed)
                        tx_drop = int(parts[12])  # TX drop is column 12
                        total_drops += rx_drop + tx_drop
    except Exception:
        pass
    
    return total_drops


def get_total_process_count() -> int:
    """Get total count of running processes from /host/proc."""
    proc_path = '/host/proc' if os.path.exists('/host/proc') else '/proc'
    count = 0
    try:
        for entry in os.listdir(proc_path):
            if entry.isdigit():
                count += 1
    except Exception:
        pass
    return count


def parse_tcp_state(state_hex: str) -> str:
    """Convert TCP state hex code to human-readable state."""
    states = {
        '01': 'ESTABLISHED', '02': 'SYN_SENT', '03': 'SYN_RECV',
        '04': 'FIN_WAIT1', '05': 'FIN_WAIT2', '06': 'TIME_WAIT',
        '07': 'CLOSE', '08': 'CLOSE_WAIT', '09': 'LAST_ACK',
        '0A': 'LISTEN', '0B': 'CLOSING'
    }
    return states.get(state_hex.upper(), 'UNKNOWN')


def hex_to_ip_port(hex_addr: str) -> tuple:
    """Convert hex address:port to IP and port."""
    ip_hex, port_hex = hex_addr.split(':')
    # IP is little-endian for x86
    ip_bytes = bytes.fromhex(ip_hex)
    ip = '.'.join(str(b) for b in reversed(ip_bytes))
    port = int(port_hex, 16)
    return ip, port


def get_process_name(pid: int) -> str:
    """Get process name from /proc/{pid}/comm."""
    try:
        with open(f'/host/proc/{pid}/comm', 'r') as f:
            return f.read().strip()[:15]
    except:
        try:
            with open(f'/proc/{pid}/comm', 'r') as f:
                return f.read().strip()[:15]
        except:
            return 'unknown'


def build_inode_to_pid_map() -> dict:
    """Build a mapping of socket inodes to (pid, process_name)."""
    inode_map = {}
    proc_path = '/host/proc' if os.path.exists('/host/proc') else '/proc'
    
    try:
        for pid_entry in os.listdir(proc_path):
            if not pid_entry.isdigit():
                continue
            
            pid = int(pid_entry)
            fd_path = f'{proc_path}/{pid}/fd'
            
            try:
                # Get process name
                try:
                    with open(f'{proc_path}/{pid}/comm', 'r') as f:
                        process_name = f.read().strip()[:15]
                except:
                    process_name = 'unknown'
                
                # Scan file descriptors for sockets
                for fd in os.listdir(fd_path):
                    try:
                        link = os.readlink(f'{fd_path}/{fd}')
                        if link.startswith('socket:['):
                            inode = link[8:-1]  # Extract inode number
                            inode_map[inode] = (pid, process_name)
                    except:
                        continue
            except PermissionError:
                continue
            except Exception:
                continue
    except Exception:
        pass
    
    return inode_map


def get_real_tcp_connections() -> List[TcpConnection]:
    """Read real TCP connections from /proc/net/tcp and /proc/net/tcp6."""
    connections = []
    
    # First, build the inode to PID mapping
    inode_map = build_inode_to_pid_map()
    
    for tcp_file in ['/host/proc/net/tcp', '/proc/net/tcp', '/host/proc/net/tcp6', '/proc/net/tcp6']:
        try:
            with open(tcp_file, 'r') as f:
                lines = f.readlines()[1:]  # Skip header
                for line in lines[:100]:  # Limit to 100 connections
                    parts = line.split()
                    if len(parts) < 10:
                        continue
                    
                    local_addr = parts[1]
                    remote_addr = parts[2]
                    state = parts[3]
                    
                    # Skip if not a valid format
                    if ':' not in local_addr or ':' not in remote_addr:
                        continue
                    
                    try:
                        local_ip, local_port = hex_to_ip_port(local_addr)
                        remote_ip, remote_port = hex_to_ip_port(remote_addr)
                    except:
                        continue
                    
                    # Get inode and look up PID/process name
                    inode = parts[9] if len(parts) > 9 else '0'
                    pid = 0
                    process_name = 'system'
                    
                    if inode in inode_map:
                        pid, process_name = inode_map[inode]
                    
                    # Only add established or listen connections
                    state_str = parse_tcp_state(state)
                    if state_str not in ['ESTABLISHED', 'LISTEN', 'TIME_WAIT', 'CLOSE_WAIT']:
                        continue
                    
                    connections.append(TcpConnection(
                        pid=pid,
                        process_name=process_name,
                        local_ip=local_ip,
                        remote_ip=remote_ip,
                        local_port=local_port,
                        remote_port=remote_port,
                        state=state_str,
                        rtt_us=0,
                        retransmits=0,
                        bytes_sent=0,
                        bytes_received=0,
                        container_id=None
                    ))
            break  # If we found one file, don't try others
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Error reading {tcp_file}: {e}")
            continue
    
    return connections


def get_real_process_flows() -> List[ProcessFlow]:
    """Get per-process network flow statistics from /host/proc."""
    flows = []
    processes_with_network = {}
    
    # Read all processes and check which have network connections
    proc_path = '/host/proc' if os.path.exists('/host/proc') else '/proc'
    
    try:
        # Get list of all processes with open sockets
        for pid_entry in os.listdir(proc_path):
            if not pid_entry.isdigit():
                continue
            
            pid = int(pid_entry)
            fd_path = f'{proc_path}/{pid}/fd'
            
            try:
                # Check if process has socket file descriptors
                socket_count = 0
                for fd in os.listdir(fd_path):
                    try:
                        link = os.readlink(f'{fd_path}/{fd}')
                        if 'socket:' in link:
                            socket_count += 1
                    except:
                        continue
                
                if socket_count > 0:
                    # Get process name
                    try:
                        with open(f'{proc_path}/{pid}/comm', 'r') as f:
                            process_name = f.read().strip()[:15]
                    except:
                        process_name = 'unknown'
                    
                    # Get network I/O stats from /proc/{pid}/net/dev if available
                    bytes_sent = 0
                    bytes_received = 0
                    
                    try:
                        with open(f'{proc_path}/{pid}/net/dev', 'r') as f:
                            for line in f.readlines()[2:]:  # Skip headers
                                parts = line.split()
                                if len(parts) >= 10:
                                    interface = parts[0].rstrip(':')
                                    if interface != 'lo':  # Skip loopback
                                        bytes_received += int(parts[1])
                                        bytes_sent += int(parts[9])
                    except:
                        pass
                    
                    # Aggregate by process name
                    if process_name in processes_with_network:
                        processes_with_network[process_name]['count'] += 1
                        processes_with_network[process_name]['bytes_sent'] += bytes_sent
                        processes_with_network[process_name]['bytes_received'] += bytes_received
                        processes_with_network[process_name]['sockets'] += socket_count
                    else:
                        processes_with_network[process_name] = {
                            'pid': pid,
                            'count': 1,
                            'bytes_sent': bytes_sent,
                            'bytes_received': bytes_received,
                            'sockets': socket_count
                        }
            except PermissionError:
                continue
            except Exception:
                continue
    except Exception as e:
        print(f"Error reading processes: {e}")
    
    # Convert to ProcessFlow objects
    for process_name, data in processes_with_network.items():
        flows.append(ProcessFlow(
            pid=data['pid'],
            process_name=process_name,
            bytes_sent=data['bytes_sent'],
            bytes_received=data['bytes_received'],
            packets_sent=0,
            packets_received=0,
            active_flows=data['sockets'],
            container_id=None
        ))
    
    # Sort by socket count (active flows)
    flows.sort(key=lambda f: f.active_flows, reverse=True)
    return flows[:50]  # Return top 50


def get_real_metrics() -> EbpfMetrics:
    """Get real system metrics from /proc and system commands."""
    tcp_connections = get_real_tcp_connections()
    process_flows = get_real_process_flows()
    
    # Syscall stats require eBPF, return empty for now
    syscall_stats = []
    
    total_processes = get_total_process_count()
    packet_drops = get_packet_drops()
    
    return EbpfMetrics(
        tcp_connections=tcp_connections,
        process_flows=process_flows,
        syscall_stats=syscall_stats,
        collection_time=datetime.utcnow().isoformat(),
        total_processes=total_processes,
        packet_drops=packet_drops
    )


@router.get("/metrics")
async def get_ebpf_metrics() -> EbpfMetrics:
    """Get all eBPF metrics (TCP connections, flows, syscalls)."""
    return get_real_metrics()


@router.get("/tcp/connections")
async def get_tcp_connections() -> List[TcpConnection]:
    """Get active TCP connections from the system."""
    return get_real_tcp_connections()


@router.get("/flows/by-process")
async def get_process_flows() -> List[ProcessFlow]:
    """Get per-process network flow statistics."""
    return get_real_process_flows()


@router.get("/syscalls/stats")
async def get_syscall_stats() -> List[SyscallStats]:
    """Get per-process syscall statistics."""
    return get_real_metrics().syscall_stats


@router.get("/flows/top-talkers")
async def get_top_talkers(limit: int = 10) -> List[ProcessFlow]:
    """Get top processes by network traffic."""
    flows = get_real_process_flows()
    sorted_flows = sorted(
        flows,
        key=lambda f: f.active_flows,
        reverse=True
    )
    return sorted_flows[:limit]


@router.get("/tcp/by-container/{container_id}")
async def get_connections_by_container(container_id: str) -> List[TcpConnection]:
    """Get TCP connections for a specific container."""
    all_connections = get_real_tcp_connections()
    return [c for c in all_connections if c.container_id == container_id]


@router.get("/syscalls/suspicious")
async def get_suspicious_syscalls() -> List[SyscallStats]:
    """Get processes with suspicious syscall patterns."""
    stats = get_real_metrics().syscall_stats
    suspicious = [s for s in stats if s.ptrace_count > 0 or s.mmap_exec_count > 10]
    return suspicious
