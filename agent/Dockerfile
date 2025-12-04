# Stage 1: Build Rust binary
FROM rust:latest AS builder

ENV BPFTOOL=/usr/sbin/bpftool

# Install build dependencies including eBPF tools
RUN apt-get update && apt-get install -y \
    build-essential \
    make \
    clang \
    llvm \
    libelf-dev \
    linux-libc-dev \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    bpftool \
    && ARCH=$(dpkg --print-architecture) && \
    bpftool version && \
    if [ "$ARCH" = "amd64" ] || [ "$ARCH" = "x86_64" ]; then \
        apt-get install -y linux-headers-amd64 || true; \
    elif [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then \
        apt-get install -y linux-headers-arm64 || true; \
    else \
        apt-get install -y linux-headers-${ARCH} || true; \
    fi && \
    rm -rf /var/lib/apt/lists/* && \
    # Find kernel headers directory
    KERNEL_HEADERS=$(ls -d /usr/src/linux-headers-* 2>/dev/null | head -1) && \
    if [ -n "$KERNEL_HEADERS" ] && [ -d "$KERNEL_HEADERS" ]; then \
        # Set up asm includes from kernel headers
        if [ -d "$KERNEL_HEADERS/arch/x86/include/uapi/asm" ]; then \
            mkdir -p /usr/include/asm && \
            ln -sf "$KERNEL_HEADERS/arch/x86/include/uapi/asm"/* /usr/include/asm/ 2>/dev/null || \
            cp -r "$KERNEL_HEADERS/arch/x86/include/uapi/asm"/* /usr/include/asm/ 2>/dev/null || true; \
        fi; \
    fi && \
    # Fallback: use system asm headers
    if [ ! -f /usr/include/asm/types.h ]; then \
        mkdir -p /usr/include/asm && \
        if [ -d /usr/include/x86_64-linux-gnu/asm ]; then \
            for header in /usr/include/x86_64-linux-gnu/asm/*.h; do \
                [ -f "$header" ] && ln -sf "$header" /usr/include/asm/$(basename "$header") 2>/dev/null || true; \
            done; \
        fi && \
        if [ ! -f /usr/include/asm/types.h ] && [ -f /usr/include/asm-generic/types.h ]; then \
            echo '#include <asm-generic/types.h>' > /usr/include/asm/types.h || \
            ln -sf /usr/include/asm-generic/types.h /usr/include/asm/types.h || true; \
        fi; \
    fi

WORKDIR /build

# Install rustfmt for eBPF skeleton generation
RUN rustup component add rustfmt

# Copy Cargo files
COPY Cargo.toml ./
COPY build.rs ./

# Copy source code
COPY src/ ./src/

# Build release binary
RUN cargo build --release

# Stage 2: Runtime image
FROM ubuntu:24.04

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libelf1 \
    ca-certificates \
    docker.io \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    # Ensure docker binary is available at expected path
    && which docker && ln -sf $(which docker) /usr/bin/docker || echo "Docker already at /usr/bin/docker" \
    # Set timezone to Asia/Tehran
    && ln -snf /usr/share/zoneinfo/Asia/Tehran /etc/localtime \
    && echo "Asia/Tehran" > /etc/timezone

# Set environment variable for timezone
ENV TZ=Asia/Tehran

WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/target/release/AncientReport-agent /app/agent

# Create config directory and copy config
RUN mkdir -p /etc/AncientReport
COPY config.example.toml /etc/AncientReport/config.example.toml
COPY config.example.toml /etc/agent/config.toml

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Run the agent
CMD ["/app/agent", "--config", "/etc/AncientReport/config.toml"]
