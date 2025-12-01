use libbpf_cargo::SkeletonBuilder;
use std::env;
use std::path::PathBuf;

const EBPF_SRC: &str = "src/ebpf";

fn main() {
    // eBPF build disabled temporarily due to build environment issues
    // let mut out = PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR not set"));
    // out.push("ebpf");

    // // Build network monitoring eBPF program
    // SkeletonBuilder::new()
    //     .source(format!("{}/network.bpf.c", EBPF_SRC))
    //     .build_and_generate(&out.join("network.skel.rs"))
    //     .expect("Failed to build network eBPF program");

    // // Build disk I/O monitoring eBPF program
    // SkeletonBuilder::new()
    //     .source(format!("{}/diskio.bpf.c", EBPF_SRC))
    //     .build_and_generate(&out.join("diskio.skel.rs"))
    //     .expect("Failed to build disk I/O eBPF program");

    // Tell Cargo to rerun this build script if eBPF sources change
    println!("cargo:rerun-if-changed={}", EBPF_SRC);
}
