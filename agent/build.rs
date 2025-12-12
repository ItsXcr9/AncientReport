use libbpf_cargo::SkeletonBuilder;
use std::env;
use std::path::PathBuf;

const EBPF_SRC: &str = "src/ebpf";

fn main() {
    let mut out = PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR not set"));
    out.push("ebpf");
    
    // Create output directory
    if let Err(e) = std::fs::create_dir_all(&out) {
        eprintln!("Warning: Could not create eBPF output directory: {}", e);
        return;
    }

    // Build syscall monitoring eBPF program (for read/write/send/recv/poll tracking)
    if let Err(e) = SkeletonBuilder::new()
        .source(format!("{}/syscall_monitor.bpf.c", EBPF_SRC))
        .build_and_generate(&out.join("syscall_monitor.skel.rs"))
    {
        eprintln!("Warning: Failed to build syscall_monitor eBPF program: {}", e);
        eprintln!("eBPF syscall tracing will be disabled.");
    }

    // Build process flow eBPF program (for per-process network tracking)
    if let Err(e) = SkeletonBuilder::new()
        .source(format!("{}/process_flow.bpf.c", EBPF_SRC))
        .build_and_generate(&out.join("process_flow.skel.rs"))
    {
        eprintln!("Warning: Failed to build process_flow eBPF program: {}", e);
    }

    // Build network monitoring eBPF program
    if let Err(e) = SkeletonBuilder::new()
        .source(format!("{}/network.bpf.c", EBPF_SRC))
        .build_and_generate(&out.join("network.skel.rs"))
    {
        eprintln!("Warning: Failed to build network eBPF program: {}", e);
        eprintln!("eBPF features will be disabled. This requires:");
        eprintln!("  - clang/LLVM installed");
        eprintln!("  - linux-headers installed");
        eprintln!("  - BPF-capable kernel (5.4+)");
    }

    // Build disk I/O monitoring eBPF program
    if let Err(e) = SkeletonBuilder::new()
        .source(format!("{}/diskio.bpf.c", EBPF_SRC))
        .build_and_generate(&out.join("diskio.skel.rs"))
    {
        eprintln!("Warning: Failed to build diskio eBPF program: {}", e);
    }

    // Tell Cargo to rerun this build script if eBPF sources change
    println!("cargo:rerun-if-changed={}/syscall_monitor.bpf.c", EBPF_SRC);
    println!("cargo:rerun-if-changed={}/process_flow.bpf.c", EBPF_SRC);
    println!("cargo:rerun-if-changed={}/network.bpf.c", EBPF_SRC);
    println!("cargo:rerun-if-changed={}/diskio.bpf.c", EBPF_SRC);
}

