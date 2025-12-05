// SPDX-License-Identifier: GPL-2.0
// TCP Connection Tracker - Phase 3 Enhanced eBPF
//
// Tracks TCP connection states, RTT, retransmits per process/container.
// Attaches to tcp_connect, tcp_set_state, tcp_retransmit_skb.

#include <linux/bpf.h>
#include <linux/ptrace.h>
#include <linux/tcp.h>
#include <linux/socket.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_endian.h>

// TCP states (from linux/tcp.h)
#define TCP_ESTABLISHED 1
#define TCP_SYN_SENT    2
#define TCP_SYN_RECV    3
#define TCP_FIN_WAIT1   4
#define TCP_FIN_WAIT2   5
#define TCP_TIME_WAIT   6
#define TCP_CLOSE       7
#define TCP_CLOSE_WAIT  8
#define TCP_LAST_ACK    9
#define TCP_LISTEN      10
#define TCP_CLOSING     11

// Connection key
struct conn_key {
    __u32 pid;
    __u32 local_ip;
    __u32 remote_ip;
    __u16 local_port;
    __u16 remote_port;
};

// Connection statistics
struct conn_stats {
    __u64 start_time;
    __u64 bytes_sent;
    __u64 bytes_received;
    __u64 rtt_sum_us;        // Sum of RTT samples in microseconds
    __u32 rtt_count;         // Number of RTT samples
    __u32 retransmits;
    __u32 state;
    char comm[16];           // Process name
    __u32 container_id_hash; // Hash of container ID (from cgroup)
};

// Active connections map
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 65536);
    __type(key, struct conn_key);
    __type(value, struct conn_stats);
} tcp_connections SEC(".maps");

// Per-process connection count
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 4096);
    __type(key, __u32);  // PID
    __type(value, __u64); // Connection count
} process_conn_count SEC(".maps");

// Connection events ring buffer
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 512 * 1024);
} tcp_events SEC(".maps");

// TCP event for userspace
struct tcp_event {
    __u64 timestamp;
    __u32 pid;
    __u32 local_ip;
    __u32 remote_ip;
    __u16 local_port;
    __u16 remote_port;
    __u32 old_state;
    __u32 new_state;
    __u32 rtt_us;
    __u32 retransmits;
    __u64 bytes_sent;
    __u64 bytes_received;
    char comm[16];
};

// Helper to get container ID hash from cgroup
static __always_inline __u32 get_container_id_hash() {
    __u64 cgroup_id = bpf_get_current_cgroup_id();
    return (__u32)(cgroup_id & 0xFFFFFFFF);
}

// Track new TCP connections
SEC("kprobe/tcp_connect")
int trace_tcp_connect(struct pt_regs *ctx) {
    struct sock *sk = (struct sock *)PT_REGS_PARM1(ctx);
    if (!sk)
        return 0;

    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    
    struct conn_key key = {};
    key.pid = pid;
    
    // Read socket addresses
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    // Initialize connection stats
    struct conn_stats stats = {};
    stats.start_time = bpf_ktime_get_ns();
    stats.state = TCP_SYN_SENT;
    stats.container_id_hash = get_container_id_hash();
    bpf_get_current_comm(&stats.comm, sizeof(stats.comm));

    bpf_map_update_elem(&tcp_connections, &key, &stats, BPF_ANY);

    // Update process connection count
    __u64 *count = bpf_map_lookup_elem(&process_conn_count, &pid);
    if (count) {
        __sync_fetch_and_add(count, 1);
    } else {
        __u64 one = 1;
        bpf_map_update_elem(&process_conn_count, &pid, &one, BPF_ANY);
    }

    // Emit event
    struct tcp_event *event = bpf_ringbuf_reserve(&tcp_events, sizeof(*event), 0);
    if (event) {
        event->timestamp = bpf_ktime_get_ns();
        event->pid = pid;
        event->local_ip = key.local_ip;
        event->remote_ip = key.remote_ip;
        event->local_port = key.local_port;
        event->remote_port = key.remote_port;
        event->old_state = 0;
        event->new_state = TCP_SYN_SENT;
        event->rtt_us = 0;
        event->retransmits = 0;
        __builtin_memcpy(event->comm, stats.comm, sizeof(event->comm));
        bpf_ringbuf_submit(event, 0);
    }

    return 0;
}

// Track TCP state changes
SEC("tracepoint/tcp/tcp_set_state")
int trace_tcp_set_state(struct trace_event_raw_tcp_set_state *ctx) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    
    // Read old and new states
    int old_state = ctx->oldstate;
    int new_state = ctx->newstate;
    
    // Read socket info from context
    const struct sock *sk = ctx->skaddr;
    if (!sk)
        return 0;

    struct conn_key key = {};
    key.pid = pid;
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    // Update connection state
    struct conn_stats *stats = bpf_map_lookup_elem(&tcp_connections, &key);
    if (stats) {
        stats->state = new_state;

        // If connection closed, emit final event
        if (new_state == TCP_CLOSE || new_state == TCP_TIME_WAIT) {
            struct tcp_event *event = bpf_ringbuf_reserve(&tcp_events, sizeof(*event), 0);
            if (event) {
                event->timestamp = bpf_ktime_get_ns();
                event->pid = pid;
                event->local_ip = key.local_ip;
                event->remote_ip = key.remote_ip;
                event->local_port = key.local_port;
                event->remote_port = key.remote_port;
                event->old_state = old_state;
                event->new_state = new_state;
                event->bytes_sent = stats->bytes_sent;
                event->bytes_received = stats->bytes_received;
                event->rtt_us = stats->rtt_count > 0 ? 
                    (stats->rtt_sum_us / stats->rtt_count) : 0;
                event->retransmits = stats->retransmits;
                __builtin_memcpy(event->comm, stats->comm, sizeof(event->comm));
                bpf_ringbuf_submit(event, 0);
            }

            // Clean up connection
            bpf_map_delete_elem(&tcp_connections, &key);

            // Update process connection count
            __u64 *count = bpf_map_lookup_elem(&process_conn_count, &pid);
            if (count && *count > 0) {
                __sync_fetch_and_add(count, -1);
            }
        }
    }

    return 0;
}

// Track TCP retransmits
SEC("kprobe/tcp_retransmit_skb")  
int trace_tcp_retransmit(struct pt_regs *ctx) {
    struct sock *sk = (struct sock *)PT_REGS_PARM1(ctx);
    if (!sk)
        return 0;

    __u32 pid = bpf_get_current_pid_tgid() >> 32;

    struct conn_key key = {};
    key.pid = pid;
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    // Increment retransmit counter
    struct conn_stats *stats = bpf_map_lookup_elem(&tcp_connections, &key);
    if (stats) {
        __sync_fetch_and_add(&stats->retransmits, 1);
    }

    return 0;
}

// Track RTT updates
SEC("fentry/tcp_rtt_estimator")
int BPF_PROG(trace_tcp_rtt, struct sock *sk) {
    if (!sk)
        return 0;

    __u32 pid = bpf_get_current_pid_tgid() >> 32;

    struct conn_key key = {};
    key.pid = pid;
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    // Read smoothed RTT
    struct tcp_sock *tp = (struct tcp_sock *)sk;
    __u32 srtt_us;
    BPF_CORE_READ_INTO(&srtt_us, tp, srtt_us);
    srtt_us >>= 3;  // Convert to microseconds

    // Update RTT stats
    struct conn_stats *stats = bpf_map_lookup_elem(&tcp_connections, &key);
    if (stats) {
        __sync_fetch_and_add(&stats->rtt_sum_us, srtt_us);
        __sync_fetch_and_add(&stats->rtt_count, 1);
    }

    return 0;
}

char LICENSE[] SEC("license") = "GPL";
