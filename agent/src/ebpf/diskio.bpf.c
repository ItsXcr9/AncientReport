// SPDX-License-Identifier: GPL-2.0
// Disk I/O tracking using eBPF block layer hooks
//
// This eBPF program attaches to the Linux block layer to track
// disk I/O operations with minimal overhead.

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

// I/O operation types
#define IO_READ  0
#define IO_WRITE 1

// Disk I/O statistics structure
struct io_stats {
    __u64 read_ops;
    __u64 write_ops;
    __u64 read_bytes;
    __u64 write_bytes;
    __u64 total_latency_ns;
    __u64 operation_count;
};

// Per-device statistics map
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 256);
    __type(key, __u32);  // Device ID
    __type(value, struct io_stats);
} device_stats SEC(".maps");

// I/O request start times (for latency calculation)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 10240);
    __type(key, __u64);  // Request pointer
    __type(value, __u64);  // Start timestamp
} io_start_times SEC(".maps");

// Ring buffer for detailed I/O events
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 256 * 1024);
} io_events SEC(".maps");

// Detailed I/O event structure
struct io_event {
    __u64 timestamp;
    __u32 device_id;
    __u64 sector;
    __u32 bytes;
    __u32 latency_ns;
    __u8 operation;  // READ or WRITE
};

// Trace I/O request start
SEC("tp/block/block_rq_issue")
int trace_io_start(void *ctx) {
    __u64 ts = bpf_ktime_get_ns();
    __u64 req_ptr = (__u64)ctx;  // Use context as request ID
    
    bpf_map_update_elem(&io_start_times, &req_ptr, &ts, BPF_ANY);
    
    return 0;
}

// Trace I/O request completion
SEC("tp/block/block_rq_complete")
int trace_io_complete(void *ctx) {
    __u64 req_ptr = (__u64)ctx;
    __u64 *start_ts = bpf_map_lookup_elem(&io_start_times, &req_ptr);
    
    if (!start_ts)
        return 0;
    
    __u64 end_ts = bpf_ktime_get_ns();
    __u64 latency = end_ts - *start_ts;
    
    // TODO: Extract device ID, sector, bytes, and operation type from context
    // For now, use placeholder values
    __u32 device_id = 0;
    __u32 bytes = 4096;
    __u8 operation = IO_READ;
    
    // Update device statistics
    struct io_stats *stats = bpf_map_lookup_elem(&device_stats, &device_id);
    
    if (!stats) {
        struct io_stats new_stats = {0};
        bpf_map_update_elem(&device_stats, &device_id, &new_stats, BPF_ANY);
        stats = bpf_map_lookup_elem(&device_stats, &device_id);
        if (!stats)
            goto cleanup;
    }
    
    // Update counters
    if (operation == IO_READ) {
        __sync_fetch_and_add(&stats->read_ops, 1);
        __sync_fetch_and_add(&stats->read_bytes, bytes);
    } else {
        __sync_fetch_and_add(&stats->write_ops, 1);
        __sync_fetch_and_add(&stats->write_bytes, bytes);
    }
    
    __sync_fetch_and_add(&stats->total_latency_ns, latency);
    __sync_fetch_and_add(&stats->operation_count, 1);
    
    // Sample 5% of I/O operations for detailed analysis
    if ((bpf_get_prandom_u32() % 20) == 0) {
        struct io_event *event = bpf_ringbuf_reserve(&io_events, sizeof(*event), 0);
        if (event) {
            event->timestamp = end_ts;
            event->device_id = device_id;
            event->sector = 0;  // TODO: Extract from context
            event->bytes = bytes;
            event->latency_ns = latency;
            event->operation = operation;
            
            bpf_ringbuf_submit(event, 0);
        }
    }

cleanup:
    bpf_map_delete_elem(&io_start_times, &req_ptr);
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
