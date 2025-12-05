// SPDX-License-Identifier: GPL-2.0
// Per-Process Network Flow Tracker - Phase 3 Enhanced eBPF
//
// Tracks network traffic (bytes sent/received) per process and container.
// Uses cgroup socket hooks for container-aware tracking.

#include <linux/bpf.h>
#include <linux/socket.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_endian.h>

#define AF_INET  2
#define AF_INET6 10

// Process flow key
struct flow_key {
    __u32 pid;
    __u32 local_ip;
    __u32 remote_ip;
    __u16 local_port;
    __u16 remote_port;
    __u8 protocol;
    __u8 pad[3];
};

// Process flow statistics
struct flow_stats {
    __u64 bytes_sent;
    __u64 bytes_received;
    __u64 packets_sent;
    __u64 packets_received;
    __u64 first_seen;
    __u64 last_seen;
    __u32 container_id_hash;
    char comm[16];
};

// Per-process total traffic
struct process_traffic {
    __u64 bytes_sent_total;
    __u64 bytes_received_total;
    __u64 packets_sent_total;
    __u64 packets_received_total;
    __u32 active_flows;
    __u32 container_id_hash;
    char comm[16];
};

// Flow statistics map
struct {
    __uint(type, BPF_MAP_TYPE_LRU_HASH);
    __uint(max_entries, 100000);
    __type(key, struct flow_key);
    __type(value, struct flow_stats);
} process_flows SEC(".maps");

// Per-process aggregated traffic
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 32768);
    __type(key, __u32);  // PID
    __type(value, struct process_traffic);
} process_traffic_map SEC(".maps");

// Flow events ring buffer
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 512 * 1024);
} flow_events SEC(".maps");

// Flow event for userspace
struct flow_event {
    __u64 timestamp;
    __u32 pid;
    __u32 local_ip;
    __u32 remote_ip;
    __u16 local_port;
    __u16 remote_port;
    __u64 bytes;
    __u8 protocol;
    __u8 direction;  // 0 = ingress, 1 = egress
    char comm[16];
};

// Helper to get container ID hash
static __always_inline __u32 get_container_hash() {
    return (__u32)(bpf_get_current_cgroup_id() & 0xFFFFFFFF);
}

// Update flow statistics
static __always_inline void update_flow_stats(
    struct flow_key *key,
    __u64 bytes,
    int is_egress
) {
    struct flow_stats *stats = bpf_map_lookup_elem(&process_flows, key);
    __u64 now = bpf_ktime_get_ns();

    if (!stats) {
        struct flow_stats new_stats = {};
        new_stats.first_seen = now;
        new_stats.last_seen = now;
        new_stats.container_id_hash = get_container_hash();
        bpf_get_current_comm(&new_stats.comm, sizeof(new_stats.comm));
        
        if (is_egress) {
            new_stats.bytes_sent = bytes;
            new_stats.packets_sent = 1;
        } else {
            new_stats.bytes_received = bytes;
            new_stats.packets_received = 1;
        }
        
        bpf_map_update_elem(&process_flows, key, &new_stats, BPF_ANY);
    } else {
        stats->last_seen = now;
        if (is_egress) {
            __sync_fetch_and_add(&stats->bytes_sent, bytes);
            __sync_fetch_and_add(&stats->packets_sent, 1);
        } else {
            __sync_fetch_and_add(&stats->bytes_received, bytes);
            __sync_fetch_and_add(&stats->packets_received, 1);
        }
    }

    // Update per-process totals
    struct process_traffic *traffic = bpf_map_lookup_elem(&process_traffic_map, &key->pid);
    if (!traffic) {
        struct process_traffic new_traffic = {};
        new_traffic.container_id_hash = get_container_hash();
        bpf_get_current_comm(&new_traffic.comm, sizeof(new_traffic.comm));
        new_traffic.active_flows = 1;
        
        if (is_egress) {
            new_traffic.bytes_sent_total = bytes;
            new_traffic.packets_sent_total = 1;
        } else {
            new_traffic.bytes_received_total = bytes;
            new_traffic.packets_received_total = 1;
        }
        
        bpf_map_update_elem(&process_traffic_map, &key->pid, &new_traffic, BPF_ANY);
    } else {
        if (is_egress) {
            __sync_fetch_and_add(&traffic->bytes_sent_total, bytes);
            __sync_fetch_and_add(&traffic->packets_sent_total, 1);
        } else {
            __sync_fetch_and_add(&traffic->bytes_received_total, bytes);
            __sync_fetch_and_add(&traffic->packets_received_total, 1);
        }
    }

    // Sample 2% of flows for detailed events
    if ((bpf_get_prandom_u32() % 50) == 0) {
        struct flow_event *event = bpf_ringbuf_reserve(&flow_events, sizeof(*event), 0);
        if (event) {
            event->timestamp = now;
            event->pid = key->pid;
            event->local_ip = key->local_ip;
            event->remote_ip = key->remote_ip;
            event->local_port = key->local_port;
            event->remote_port = key->remote_port;
            event->bytes = bytes;
            event->protocol = key->protocol;
            event->direction = is_egress ? 1 : 0;
            bpf_get_current_comm(&event->comm, sizeof(event->comm));
            bpf_ringbuf_submit(event, 0);
        }
    }
}

// Track socket send operations
SEC("cgroup_skb/egress")
int track_egress(struct __sk_buff *skb) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (pid == 0)
        return 1;  // Allow packet

    // Build flow key from sk_buff
    struct flow_key key = {};
    key.pid = pid;
    key.local_ip = skb->local_ip4;
    key.remote_ip = skb->remote_ip4;
    key.local_port = skb->local_port;
    key.remote_port = bpf_ntohl(skb->remote_port) >> 16;
    key.protocol = skb->protocol;

    update_flow_stats(&key, skb->len, 1);

    return 1;  // Allow packet
}

// Track socket receive operations
SEC("cgroup_skb/ingress")
int track_ingress(struct __sk_buff *skb) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    if (pid == 0)
        return 1;

    struct flow_key key = {};
    key.pid = pid;
    key.local_ip = skb->local_ip4;
    key.remote_ip = skb->remote_ip4;
    key.local_port = skb->local_port;
    key.remote_port = bpf_ntohl(skb->remote_port) >> 16;
    key.protocol = skb->protocol;

    update_flow_stats(&key, skb->len, 0);

    return 1;
}

// Alternative: socket sendmsg/recvmsg kprobes for broader compatibility
SEC("kprobe/tcp_sendmsg")
int trace_tcp_sendmsg(struct pt_regs *ctx) {
    struct sock *sk = (struct sock *)PT_REGS_PARM1(ctx);
    size_t size = (size_t)PT_REGS_PARM3(ctx);

    if (!sk || size == 0)
        return 0;

    __u32 pid = bpf_get_current_pid_tgid() >> 32;

    struct flow_key key = {};
    key.pid = pid;
    key.protocol = IPPROTO_TCP;
    
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    update_flow_stats(&key, size, 1);

    return 0;
}

SEC("kprobe/tcp_recvmsg")
int trace_tcp_recvmsg(struct pt_regs *ctx) {
    struct sock *sk = (struct sock *)PT_REGS_PARM1(ctx);
    size_t size = (size_t)PT_REGS_PARM3(ctx);

    if (!sk || size == 0)
        return 0;

    __u32 pid = bpf_get_current_pid_tgid() >> 32;

    struct flow_key key = {};
    key.pid = pid;
    key.protocol = IPPROTO_TCP;
    
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    update_flow_stats(&key, size, 0);

    return 0;
}

SEC("kprobe/udp_sendmsg")
int trace_udp_sendmsg(struct pt_regs *ctx) {
    struct sock *sk = (struct sock *)PT_REGS_PARM1(ctx);
    size_t size = (size_t)PT_REGS_PARM3(ctx);

    if (!sk || size == 0)
        return 0;

    __u32 pid = bpf_get_current_pid_tgid() >> 32;

    struct flow_key key = {};
    key.pid = pid;
    key.protocol = IPPROTO_UDP;
    
    BPF_CORE_READ_INTO(&key.local_ip, sk, __sk_common.skc_rcv_saddr);
    BPF_CORE_READ_INTO(&key.remote_ip, sk, __sk_common.skc_daddr);
    BPF_CORE_READ_INTO(&key.local_port, sk, __sk_common.skc_num);
    __u16 dport;
    BPF_CORE_READ_INTO(&dport, sk, __sk_common.skc_dport);
    key.remote_port = bpf_ntohs(dport);

    update_flow_stats(&key, size, 1);

    return 0;
}

char LICENSE[] SEC("license") = "GPL";
