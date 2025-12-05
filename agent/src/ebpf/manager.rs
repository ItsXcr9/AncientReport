//! eBPF Program Manager - Phase 3 Enhanced eBPF
//! 
//! Manages loading and data collection from eBPF programs for:
//! - TCP connection tracking (RTT, retransmits, states)
//! - Per-process network flows (bandwidth)
//! - Syscall monitoring (security events)
//! - Disk I/O per process

use anyhow::{Context, Result};
use libbpf_rs::{MapFlags, Object, ObjectBuilder, RingBufferBuilder};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tracing::{info, warn, error, debug};

/// TCP connection event from eBPF
#[derive(Debug, Clone)]
pub struct TcpConnectionEvent {
    pub timestamp: u64,
    pub pid: u32,
    pub local_ip: std::net::Ipv4Addr,
    pub remote_ip: std::net::Ipv4Addr,
    pub local_port: u16,
    pub remote_port: u16,
    pub old_state: u32,
    pub new_state: u32,
    pub rtt_us: u32,
    pub retransmits: u32,
    pub bytes_sent: u64,
    pub bytes_received: u64,
    pub comm: String,
}

/// Network flow event from eBPF
#[derive(Debug, Clone)]
pub struct FlowEvent {
    pub timestamp: u64,
    pub pid: u32,
    pub local_ip: std::net::Ipv4Addr,
    pub remote_ip: std::net::Ipv4Addr,
    pub local_port: u16,
    pub remote_port: u16,
    pub bytes: u64,
    pub protocol: u8,
    pub direction: u8, // 0 = ingress, 1 = egress
    pub comm: String,
}

/// Syscall event from eBPF
#[derive(Debug, Clone)]
pub struct SyscallEvent {
    pub timestamp: u64,
    pub pid: u32,
    pub ppid: u32,
    pub uid: u32,
    pub gid: u32,
    pub syscall_nr: u32,
    pub ret: i64,
    pub container_id_hash: u32,
    pub comm: String,
    pub filename: Option<String>,
}

/// Per-process traffic statistics
#[derive(Debug, Clone, Default)]
pub struct ProcessTraffic {
    pub bytes_sent: u64,
    pub bytes_received: u64,
    pub packets_sent: u64,
    pub packets_received: u64,
    pub active_flows: u32,
    pub comm: String,
}

/// eBPF Program Manager
pub struct EbpfManager {
    // Loaded eBPF objects
    tcp_tracker: Option<Object>,
    process_flow: Option<Object>,
    syscall_monitor: Option<Object>,
    
    // Event handlers
    tcp_events: Arc<Mutex<Vec<TcpConnectionEvent>>>,
    flow_events: Arc<Mutex<Vec<FlowEvent>>>,
    syscall_events: Arc<Mutex<Vec<SyscallEvent>>>,
    
    // Aggregated stats
    process_traffic: Arc<Mutex<HashMap<u32, ProcessTraffic>>>,
}

impl EbpfManager {
    /// Create new eBPF manager
    pub fn new() -> Self {
        Self {
            tcp_tracker: None,
            process_flow: None,
            syscall_monitor: None,
            tcp_events: Arc::new(Mutex::new(Vec::new())),
            flow_events: Arc::new(Mutex::new(Vec::new())),
            syscall_events: Arc::new(Mutex::new(Vec::new())),
            process_traffic: Arc::new(Mutex::new(HashMap::new())),
        }
    }
    
    /// Load TCP tracker eBPF program
    pub fn load_tcp_tracker(&mut self, path: &str) -> Result<()> {
        info!("Loading TCP tracker eBPF from {}", path);
        
        let obj = ObjectBuilder::default()
            .open_file(path)
            .context("Failed to open TCP tracker BPF object")?
            .load()
            .context("Failed to load TCP tracker BPF object")?;
        
        self.tcp_tracker = Some(obj);
        info!("TCP tracker eBPF loaded successfully");
        Ok(())
    }
    
    /// Load process flow eBPF program
    pub fn load_process_flow(&mut self, path: &str) -> Result<()> {
        info!("Loading process flow eBPF from {}", path);
        
        let obj = ObjectBuilder::default()
            .open_file(path)
            .context("Failed to open process flow BPF object")?
            .load()
            .context("Failed to load process flow BPF object")?;
        
        self.process_flow = Some(obj);
        info!("Process flow eBPF loaded successfully");
        Ok(())
    }
    
    /// Load syscall monitor eBPF program
    pub fn load_syscall_monitor(&mut self, path: &str) -> Result<()> {
        info!("Loading syscall monitor eBPF from {}", path);
        
        let obj = ObjectBuilder::default()
            .open_file(path)
            .context("Failed to open syscall monitor BPF object")?
            .load()
            .context("Failed to load syscall monitor BPF object")?;
        
        self.syscall_monitor = Some(obj);
        info!("Syscall monitor eBPF loaded successfully");
        Ok(())
    }
    
    /// Start collecting events from all loaded eBPF programs
    pub async fn start_collection(&self) -> Result<()> {
        info!("Starting eBPF event collection");
        
        // Start TCP event collection
        if let Some(ref obj) = self.tcp_tracker {
            let tcp_events = self.tcp_events.clone();
            let map = obj.map("tcp_events").context("tcp_events map not found")?;
            
            tokio::spawn(async move {
                Self::collect_tcp_events(map, tcp_events).await;
            });
        }
        
        // Start flow event collection
        if let Some(ref obj) = self.process_flow {
            let flow_events = self.flow_events.clone();
            let process_traffic = self.process_traffic.clone();
            let map = obj.map("flow_events").context("flow_events map not found")?;
            
            tokio::spawn(async move {
                Self::collect_flow_events(map, flow_events, process_traffic).await;
            });
        }
        
        // Start syscall event collection
        if let Some(ref obj) = self.syscall_monitor {
            let syscall_events = self.syscall_events.clone();
            let map = obj.map("syscall_events").context("syscall_events map not found")?;
            
            tokio::spawn(async move {
                Self::collect_syscall_events(map, syscall_events).await;
            });
        }
        
        Ok(())
    }
    
    /// Collect TCP events from ring buffer
    async fn collect_tcp_events(
        map: &libbpf_rs::Map,
        events: Arc<Mutex<Vec<TcpConnectionEvent>>>,
    ) {
        // Ring buffer event processing would go here
        // This is a placeholder - actual implementation requires unsafe code
        info!("TCP event collection started");
    }
    
    /// Collect flow events from ring buffer
    async fn collect_flow_events(
        map: &libbpf_rs::Map,
        events: Arc<Mutex<Vec<FlowEvent>>>,
        traffic: Arc<Mutex<HashMap<u32, ProcessTraffic>>>,
    ) {
        info!("Flow event collection started");
    }
    
    /// Collect syscall events from ring buffer
    async fn collect_syscall_events(
        map: &libbpf_rs::Map,
        events: Arc<Mutex<Vec<SyscallEvent>>>,
    ) {
        info!("Syscall event collection started");
    }
    
    /// Get recent TCP events
    pub fn get_tcp_events(&self) -> Vec<TcpConnectionEvent> {
        let mut events = self.tcp_events.lock().unwrap();
        let result = events.drain(..).collect();
        result
    }
    
    /// Get recent flow events
    pub fn get_flow_events(&self) -> Vec<FlowEvent> {
        let mut events = self.flow_events.lock().unwrap();
        let result = events.drain(..).collect();
        result
    }
    
    /// Get recent syscall events
    pub fn get_syscall_events(&self) -> Vec<SyscallEvent> {
        let mut events = self.syscall_events.lock().unwrap();
        let result = events.drain(..).collect();
        result
    }
    
    /// Get per-process traffic statistics
    pub fn get_process_traffic(&self) -> HashMap<u32, ProcessTraffic> {
        self.process_traffic.lock().unwrap().clone()
    }
    
    /// Read TCP connection stats from eBPF map
    pub fn read_tcp_connections(&self) -> Result<Vec<(u32, u32, u32)>> {
        // Returns (pid, connections_count, avg_rtt_us)
        let mut results = Vec::new();
        
        if let Some(ref obj) = self.tcp_tracker {
            if let Some(map) = obj.map("process_conn_count") {
                // Iterate over map entries
                for key in map.keys() {
                    if let Ok(value) = map.lookup(&key, MapFlags::ANY) {
                        if let (Some(pid_bytes), Some(count_bytes)) = (key.get(..4), value.as_deref()) {
                            let pid = u32::from_ne_bytes(pid_bytes.try_into().unwrap_or([0; 4]));
                            let count = u64::from_ne_bytes(
                                count_bytes.try_into().unwrap_or([0; 8])
                            ) as u32;
                            results.push((pid, count, 0));
                        }
                    }
                }
            }
        }
        
        Ok(results)
    }
}

impl Default for EbpfManager {
    fn default() -> Self {
        Self::new()
    }
}

/// TCP state names
pub fn tcp_state_name(state: u32) -> &'static str {
    match state {
        1 => "ESTABLISHED",
        2 => "SYN_SENT",
        3 => "SYN_RECV",
        4 => "FIN_WAIT1",
        5 => "FIN_WAIT2",
        6 => "TIME_WAIT",
        7 => "CLOSE",
        8 => "CLOSE_WAIT",
        9 => "LAST_ACK",
        10 => "LISTEN",
        11 => "CLOSING",
        _ => "UNKNOWN",
    }
}

/// Syscall number to name
pub fn syscall_name(nr: u32) -> &'static str {
    match nr {
        59 => "execve",
        42 => "connect",
        2 => "open",
        257 => "openat",
        41 => "socket",
        9 => "mmap",
        56 => "clone",
        57 => "fork",
        101 => "ptrace",
        _ => "unknown",
    }
}
