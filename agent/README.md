# AncientReport AI Agent

Rust-based monitoring agent with eBPF probes for low-overhead system observability.

## Features

- **eBPF-based monitoring** (<3% overhead)
  - Network packet tracking (XDP hooks)
  - Disk I/O monitoring (block layer tracepoints)
- **/proc metrics collection**
  - CPU, memory, load average
  - Process statistics
- **ClickHouse integration** for time-series storage
- **10-second collection interval**

## Building

```bash
# Install dependencies (Ubuntu/Debian)
sudo apt-get install -y \
  build-essential \
  clang \
  llvm \
  libelf-dev \
  linux-headers-$(uname -r)

# Build the agent
cargo build --release

# Binary will be at: target/release/AncientReport-agent
```

## Configuration

Create `/etc/AncientReport/config.toml`:

```toml
[agent]
hostname = "auto-detect"
collection_interval = "10s"

[clickhouse]
url = "http://localhost:8123"
database = "AncientReport"

[ai]
provider = "anthropic"
api_key = "your-api-key"
model = "claude-3-5-sonnet-20241022"

[alerts]
telegram_token = "your-bot-token"
telegram_chat_id = "your-chat-id"
```

## Running

```bash
# Run directly
sudo ./target/release/AncientReport-agent

# Or install as systemd service
sudo cp target/release/AncientReport-agent /usr/local/bin/
sudo systemctl enable --now AncientReport
```

## Development Status

- [x] Project structure
- [x] Configuration system
- [/] eBPF probes (network, disk I/O)
- [/] /proc collector
- [ ] ClickHouse integration
- [ ] Full eBPF implementation

## Requirements

- Linux kernel 5.4+ (for eBPF CO-RE support)
- Rust 1.70+
- ClickHouse server
