// SPDX-License-Identifier: GPL-2.0
// Network packet tracking using eBPF XDP hooks
//
// This eBPF program attaches to network interfaces using XDP (eXpress Data Path)
// to track packet statistics with minimal overhead.

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/in.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

// Packet statistics structure
struct packet_stats {
    __u64 packets_total;
    __u64 packets_dropped;
    __u64 bytes_total;
    __u64 tcp_packets;
    __u64 udp_packets;
    __u64 icmp_packets;
};

// Per-interface statistics map
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 256);
    __type(key, __u32);  // Interface index
    __type(value, struct packet_stats);
} interface_stats SEC(".maps");

// Ring buffer for detailed packet events
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 256 * 1024);
} packet_events SEC(".maps");

// Detailed packet event structure
struct packet_event {
    __u64 timestamp;
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u32 bytes;
    __u8 protocol;
    __u8 flags;
};

// XDP program to track packets
SEC("xdp")
int track_packets(struct xdp_md *ctx) {
    void *data_end = (void *)(long)ctx->data_end;
    void *data = (void *)(long)ctx->data;
    
    // Parse Ethernet header
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end)
        return XDP_PASS;
    
    // Only process IP packets
    if (eth->h_proto != bpf_htons(ETH_P_IP))
        return XDP_PASS;
    
    // Parse IP header
    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return XDP_PASS;
    
    // Update interface statistics
    __u32 ifindex = ctx->ingress_ifindex;
    struct packet_stats *stats = bpf_map_lookup_elem(&interface_stats, &ifindex);
    
    if (!stats) {
        // Initialize stats for this interface
        struct packet_stats new_stats = {0};
        bpf_map_update_elem(&interface_stats, &ifindex, &new_stats, BPF_ANY);
        stats = bpf_map_lookup_elem(&interface_stats, &ifindex);
        if (!stats)
            return XDP_PASS;
    }
    
    // Update counters
    __sync_fetch_and_add(&stats->packets_total, 1);
    __sync_fetch_and_add(&stats->bytes_total, data_end - data);
    
    // Track protocol statistics
    if (ip->protocol == IPPROTO_TCP) {
        __sync_fetch_and_add(&stats->tcp_packets, 1);
    } else if (ip->protocol == IPPROTO_UDP) {
        __sync_fetch_and_add(&stats->udp_packets, 1);
    } else if (ip->protocol == IPPROTO_ICMP) {
        __sync_fetch_and_add(&stats->icmp_packets, 1);
    }
    
    // Sample 1% of packets for detailed analysis
    if ((bpf_get_prandom_u32() % 100) == 0) {
        struct packet_event *event = bpf_ringbuf_reserve(&packet_events, sizeof(*event), 0);
        if (event) {
            event->timestamp = bpf_ktime_get_ns();
            event->src_ip = bpf_ntohl(ip->saddr);
            event->dst_ip = bpf_ntohl(ip->daddr);
            event->bytes = data_end - data;
            event->protocol = ip->protocol;
            event->src_port = 0;
            event->dst_port = 0;
            event->flags = 0;
            
            // Extract port information for TCP/UDP
            if (ip->protocol == IPPROTO_TCP) {
                struct tcphdr *tcp = (void *)(ip + 1);
                if ((void *)(tcp + 1) <= data_end) {
                    event->src_port = bpf_ntohs(tcp->source);
                    event->dst_port = bpf_ntohs(tcp->dest);
                }
            } else if (ip->protocol == IPPROTO_UDP) {
                struct udphdr *udp = (void *)(ip + 1);
                if ((void *)(udp + 1) <= data_end) {
                    event->src_port = bpf_ntohs(udp->source);
                    event->dst_port = bpf_ntohs(udp->dest);
                }
            }
            
            bpf_ringbuf_submit(event, 0);
        }
    }
    
    return XDP_PASS;
}

char LICENSE[] SEC("license") = "GPL";
