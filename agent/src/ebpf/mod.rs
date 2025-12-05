//! eBPF Module - Phase 3 Enhanced eBPF Support
//! 
//! Provides deep system observability via eBPF:
//! - TCP connection tracking (RTT, states, retransmits)
//! - Per-process network flows (bandwidth)  
//! - Syscall monitoring (security events)
//! - Disk I/O per process

pub mod manager;

pub use manager::{
    EbpfManager,
    TcpConnectionEvent,
    FlowEvent,
    SyscallEvent,
    ProcessTraffic,
    tcp_state_name,
    syscall_name,
};
