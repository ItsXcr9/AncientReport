// SPDX-License-Identifier: GPL-2.0
// Syscall Monitor - Phase 3 Enhanced eBPF
//
// Monitors security-relevant syscalls for anomaly detection.
// Tracks: exec, connect, open, socket, mmap with exec permissions.

#include <linux/bpf.h>
#include <linux/ptrace.h>
#include <linux/sched.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#define MAX_FILENAME_LEN 256
#define MAX_ARGS 6

// Syscall types we track
#define SYSCALL_READ        0
#define SYSCALL_WRITE       1
#define SYSCALL_EXECVE      59
#define SYSCALL_CONNECT     42
#define SYSCALL_OPEN        2
#define SYSCALL_OPENAT      257
#define SYSCALL_SOCKET      41
#define SYSCALL_MMAP        9
#define SYSCALL_CLONE       56
#define SYSCALL_FORK        57
#define SYSCALL_PTRACE      101
#define SYSCALL_POLL        7
#define SYSCALL_RECVMSG     47
#define SYSCALL_SENDMSG     46

// Syscall event for userspace
struct syscall_event {
    __u64 timestamp;
    __u32 pid;
    __u32 ppid;
    __u32 uid;
    __u32 gid;
    __u32 syscall_nr;
    __s64 ret;
    __u32 container_id_hash;
    char comm[16];
    char filename[MAX_FILENAME_LEN];
    __u64 args[MAX_ARGS];
};

// Per-process syscall counts
struct syscall_count {
    __u64 read_count;
    __u64 write_count;
    __u64 sendmsg_count;
    __u64 recvmsg_count;
    __u64 poll_count;
    __u64 execve_count;
    __u64 connect_count;
    __u64 open_count;
    __u64 socket_count;
    __u64 mmap_exec_count;
    __u64 ptrace_count;
    __u64 total_count;
    __u64 last_activity;
};

// Syscall events ring buffer
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1024 * 1024);
} syscall_events SEC(".maps");

// Per-process syscall statistics
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 32768);
    __type(key, __u32);  // PID
    __type(value, struct syscall_count);
} process_syscalls SEC(".maps");

// Suspicious activity thresholds (per 10 seconds)
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct syscall_count);  // Used as thresholds
} syscall_thresholds SEC(".maps");

// Helper to get container ID hash
static __always_inline __u32 get_container_hash() {
    return (__u32)(bpf_get_current_cgroup_id() & 0xFFFFFFFF);
}

// Emit syscall event
static __always_inline void emit_syscall_event(
    __u32 syscall_nr,
    const char *filename,
    __u64 *args,
    __s64 ret
) {
    struct syscall_event *event = bpf_ringbuf_reserve(&syscall_events, sizeof(*event), 0);
    if (!event)
        return;

    event->timestamp = bpf_ktime_get_ns();
    event->pid = bpf_get_current_pid_tgid() >> 32;
    event->syscall_nr = syscall_nr;
    event->ret = ret;
    event->container_id_hash = get_container_hash();

    // Get process info
    struct task_struct *task = (struct task_struct *)bpf_get_current_task();
    BPF_CORE_READ_INTO(&event->ppid, task, real_parent, tgid);
    event->uid = bpf_get_current_uid_gid() & 0xFFFFFFFF;
    event->gid = bpf_get_current_uid_gid() >> 32;
    
    bpf_get_current_comm(&event->comm, sizeof(event->comm));

    if (filename) {
        bpf_probe_read_user_str(&event->filename, sizeof(event->filename), filename);
    }

    if (args) {
        #pragma unroll
        for (int i = 0; i < MAX_ARGS; i++) {
            event->args[i] = args[i];
        }
    }

    bpf_ringbuf_submit(event, 0);
}

// Update syscall counts
static __always_inline void update_syscall_count(__u32 syscall_nr) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    
    struct syscall_count *count = bpf_map_lookup_elem(&process_syscalls, &pid);
    if (!count) {
        struct syscall_count new_count = {};
        new_count.total_count = 1;
        new_count.last_activity = bpf_ktime_get_ns();
        
        switch (syscall_nr) {
            case SYSCALL_READ: new_count.read_count = 1; break;
            case SYSCALL_WRITE: new_count.write_count = 1; break;
            case SYSCALL_SENDMSG: new_count.sendmsg_count = 1; break;
            case SYSCALL_RECVMSG: new_count.recvmsg_count = 1; break;
            case SYSCALL_POLL: new_count.poll_count = 1; break;
            case SYSCALL_EXECVE: new_count.execve_count = 1; break;
            case SYSCALL_CONNECT: new_count.connect_count = 1; break;
            case SYSCALL_OPEN:
            case SYSCALL_OPENAT: new_count.open_count = 1; break;
            case SYSCALL_SOCKET: new_count.socket_count = 1; break;
            case SYSCALL_MMAP: new_count.mmap_exec_count = 1; break;
            case SYSCALL_PTRACE: new_count.ptrace_count = 1; break;
        }
        
        bpf_map_update_elem(&process_syscalls, &pid, &new_count, BPF_ANY);
    } else {
        __sync_fetch_and_add(&count->total_count, 1);
        count->last_activity = bpf_ktime_get_ns();
        
        switch (syscall_nr) {
            case SYSCALL_READ: 
                __sync_fetch_and_add(&count->read_count, 1); 
                break;
            case SYSCALL_WRITE: 
                __sync_fetch_and_add(&count->write_count, 1); 
                break;
            case SYSCALL_SENDMSG: 
                __sync_fetch_and_add(&count->sendmsg_count, 1); 
                break;
            case SYSCALL_RECVMSG: 
                __sync_fetch_and_add(&count->recvmsg_count, 1); 
                break;
            case SYSCALL_POLL: 
                __sync_fetch_and_add(&count->poll_count, 1); 
                break;
            case SYSCALL_EXECVE: 
                __sync_fetch_and_add(&count->execve_count, 1); 
                break;
            case SYSCALL_CONNECT: 
                __sync_fetch_and_add(&count->connect_count, 1); 
                break;
            case SYSCALL_OPEN:
            case SYSCALL_OPENAT: 
                __sync_fetch_and_add(&count->open_count, 1); 
                break;
            case SYSCALL_SOCKET: 
                __sync_fetch_and_add(&count->socket_count, 1); 
                break;
            case SYSCALL_MMAP: 
                __sync_fetch_and_add(&count->mmap_exec_count, 1); 
                break;
            case SYSCALL_PTRACE: 
                __sync_fetch_and_add(&count->ptrace_count, 1); 
                break;
        }
    }
}

// Track execve syscalls
SEC("tracepoint/syscalls/sys_enter_execve")
int trace_execve_enter(struct trace_event_raw_sys_enter *ctx) {
    const char *filename = (const char *)ctx->args[0];
    __u64 args[MAX_ARGS] = {};
    args[0] = ctx->args[0];
    args[1] = ctx->args[1];
    args[2] = ctx->args[2];
    
    emit_syscall_event(SYSCALL_EXECVE, filename, args, 0);
    update_syscall_count(SYSCALL_EXECVE);
    
    return 0;
}

// Track connect syscalls - potential network activity
SEC("tracepoint/syscalls/sys_enter_connect")
int trace_connect_enter(struct trace_event_raw_sys_enter *ctx) {
    __u64 args[MAX_ARGS] = {};
    args[0] = ctx->args[0];  // sockfd
    args[1] = ctx->args[1];  // addr
    args[2] = ctx->args[2];  // addrlen
    
    emit_syscall_event(SYSCALL_CONNECT, NULL, args, 0);
    update_syscall_count(SYSCALL_CONNECT);
    
    return 0;
}

// Track openat syscalls - file access patterns
SEC("tracepoint/syscalls/sys_enter_openat")
int trace_openat_enter(struct trace_event_raw_sys_enter *ctx) {
    const char *filename = (const char *)ctx->args[1];
    __u64 args[MAX_ARGS] = {};
    args[0] = ctx->args[0];  // dirfd
    args[1] = ctx->args[1];  // filename
    args[2] = ctx->args[2];  // flags
    args[3] = ctx->args[3];  // mode
    
    // Sample 10% of file opens
    if ((bpf_get_prandom_u32() % 10) == 0) {
        emit_syscall_event(SYSCALL_OPENAT, filename, args, 0);
    }
    update_syscall_count(SYSCALL_OPENAT);
    
    return 0;
}

// Track socket creation
SEC("tracepoint/syscalls/sys_enter_socket")
int trace_socket_enter(struct trace_event_raw_sys_enter *ctx) {
    __u64 args[MAX_ARGS] = {};
    args[0] = ctx->args[0];  // domain
    args[1] = ctx->args[1];  // type
    args[2] = ctx->args[2];  // protocol
    
    emit_syscall_event(SYSCALL_SOCKET, NULL, args, 0);
    update_syscall_count(SYSCALL_SOCKET);
    
    return 0;
}

// Track ptrace - potential debugging/injection
SEC("tracepoint/syscalls/sys_enter_ptrace")
int trace_ptrace_enter(struct trace_event_raw_sys_enter *ctx) {
    __u64 args[MAX_ARGS] = {};
    args[0] = ctx->args[0];  // request
    args[1] = ctx->args[1];  // pid
    args[2] = ctx->args[2];  // addr
    args[3] = ctx->args[3];  // data
    
    // Always emit ptrace events - security critical
    emit_syscall_event(SYSCALL_PTRACE, NULL, args, 0);
    update_syscall_count(SYSCALL_PTRACE);
    
    return 0;
}

// Track mmap with PROT_EXEC - potential code injection
SEC("tracepoint/syscalls/sys_enter_mmap")
int trace_mmap_enter(struct trace_event_raw_sys_enter *ctx) {
    __u64 prot = ctx->args[2];
    
    // Only track executable mappings
    if (prot & 0x4) {  // PROT_EXEC
        __u64 args[MAX_ARGS] = {};
        args[0] = ctx->args[0];  // addr
        args[1] = ctx->args[1];  // length
        args[2] = ctx->args[2];  // prot
        args[3] = ctx->args[3];  // flags
        args[4] = ctx->args[4];  // fd
        args[5] = ctx->args[5];  // offset
        
        emit_syscall_event(SYSCALL_MMAP, NULL, args, 0);
        update_syscall_count(SYSCALL_MMAP);
    }
    
    return 0;
}

// Track process creation
SEC("tracepoint/syscalls/sys_enter_clone")
int trace_clone_enter(struct trace_event_raw_sys_enter *ctx) {
    __u64 args[MAX_ARGS] = {};
    args[0] = ctx->args[0];  // flags
    
    // Sample 50% of clones
    if ((bpf_get_prandom_u32() % 2) == 0) {
        emit_syscall_event(SYSCALL_CLONE, NULL, args, 0);
    }
    
    return 0;
}

// Track read syscalls - disk I/O
SEC("tracepoint/syscalls/sys_enter_read")
int trace_read_enter(struct trace_event_raw_sys_enter *ctx) {
    update_syscall_count(SYSCALL_READ);
    return 0;
}

// Track write syscalls - disk I/O
SEC("tracepoint/syscalls/sys_enter_write")
int trace_write_enter(struct trace_event_raw_sys_enter *ctx) {
    update_syscall_count(SYSCALL_WRITE);
    return 0;
}

// Track sendmsg syscalls - network send
SEC("tracepoint/syscalls/sys_enter_sendmsg")
int trace_sendmsg_enter(struct trace_event_raw_sys_enter *ctx) {
    update_syscall_count(SYSCALL_SENDMSG);
    return 0;
}

// Track recvmsg syscalls - network receive
SEC("tracepoint/syscalls/sys_enter_recvmsg")
int trace_recvmsg_enter(struct trace_event_raw_sys_enter *ctx) {
    update_syscall_count(SYSCALL_RECVMSG);
    return 0;
}

// Track poll/epoll syscalls - I/O multiplexing
SEC("tracepoint/syscalls/sys_enter_poll")
int trace_poll_enter(struct trace_event_raw_sys_enter *ctx) {
    update_syscall_count(SYSCALL_POLL);
    return 0;
}

SEC("tracepoint/syscalls/sys_enter_epoll_wait")
int trace_epoll_wait_enter(struct trace_event_raw_sys_enter *ctx) {
    update_syscall_count(SYSCALL_POLL);
    return 0;
}

char LICENSE[] SEC("license") = "GPL";

