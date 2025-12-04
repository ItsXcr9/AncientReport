# AncientReport - Technical Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Data Collection](#data-collection)
5. [Storage Layer](#storage-layer)
6. [Analysis Engine](#analysis-engine)
7. [Frontend](#frontend)
8. [API Reference](#api-reference)
9. [Data Flow](#data-flow)
10. [Metrics Details](#metrics-details)
11. [Process Monitoring](#process-monitoring)
12. [Deployment](#deployment)

---

## System Overview

AncientReport is an AI-powered infrastructure monitoring and analysis system that collects system metrics, stores them in ClickHouse, and provides AI-driven insights through a web dashboard.

### Key Features

- **Real-time Metrics Collection**: System, process, disk I/O, and network metrics
- **Time-Series Storage**: ClickHouse for efficient metric storage and querying
- **AI-Powered Analysis**: Hourly and daily analysis with AI-generated insights
- **Process Monitoring**: Top processes by CPU, memory, and disk I/O
- **Interactive Dashboard**: React-based UI with real-time charts

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AncientReport System                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │   Agent      │─────▶│  ClickHouse  │◀─────│  Analysis │ │
│  │  (Rust)      │      │   Database   │      │  (Python) │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│         │                        │                  │        │
│         │                        │                  │        │
│         ▼                        ▼                  ▼        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              React UI Dashboard                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

- **Agent**: Rust + Tokio (async runtime)
- **Analysis**: Python + FastAPI + APScheduler
- **Storage**: ClickHouse (time-series database)
- **Frontend**: React + TypeScript + Vite + Recharts
- **AI**: Google Gemini API

---

## Components

### 1. Agent (Rust)

**Location**: `agent/src/`

**Purpose**: Collects system metrics and sends them to ClickHouse

**Key Files**:
- `main.rs`: Entry point, orchestrates collectors
- `collectors/proc_collector.rs`: /proc filesystem metrics collection
- `collectors/ebpf_collector.rs`: eBPF-based collection (placeholder)
- `aggregator.rs`: Batches and sends metrics to ClickHouse
- `storage.rs`: ClickHouse client wrapper
- `config.rs`: Configuration management

**Collection Interval**: 60 seconds (1 minute)

**Metrics Collected**:
- System: CPU, memory, load average, process count
- Disk I/O: Reads/sec, writes/sec, latency
- Network: Packets sent/received, bytes, drops
- Processes: Top 3 CPU, memory, disk I/O consumers

### 2. Analysis Engine (Python)

**Location**: `analysis/src/`

**Purpose**: Analyzes metrics, generates reports, provides AI insights

**Key Files**:
- `main.py`: FastAPI application, API endpoints
- `analyzers/hourly.py`: Hourly analysis logic
- `analyzers/daily.py`: Daily analysis logic
- `analyzers/metrics_aggregator.py`: Metric aggregation utilities
- `storage/clickhouse_client.py`: ClickHouse client
- `ai/engine.py`: AI engine wrapper (Gemini)

**Analysis Frequency**:
- Hourly: Every hour at minute 0
- Daily: Every day at 23:55

### 3. Frontend (React)

**Location**: `ui/src/`

**Purpose**: Web dashboard for viewing metrics and reports

**Key Files**:
- `App.tsx`: Main application component
- `components/CPUChart.tsx`: CPU usage chart
- `components/MemoryChart.tsx`: Memory usage chart
- `components/DiskIOChart.tsx`: Disk I/O chart
- `components/NetworkChart.tsx`: Network traffic chart
- `components/MetricsChart.tsx`: Reusable chart component

**Features**:
- Real-time metric charts
- Latest analysis report display
- Top processes visualization
- AI insights and recommendations

### 4. Storage (ClickHouse)

**Location**: `deploy/clickhouse/init.sql`

**Purpose**: Time-series database for metric storage

**Tables**:
- `metrics`: Raw metrics (timestamp, hostname, metric_type, metric_name, value, tags)
- `hourly_reports`: Hourly analysis reports
- `daily_reports`: Daily analysis reports
- `events`: System events and alerts
- `config_audits`: Configuration audit history

---

## Data Collection

### Collection Methods

#### 1. /proc Filesystem Collection

**Implementation**: `agent/src/collectors/proc_collector.rs`

**Sources**:
- `/proc/stat`: CPU statistics
- `/proc/meminfo`: Memory information
- `/proc/loadavg`: Load averages
- `/proc/diskstats`: Disk I/O statistics
- `/proc/net/dev`: Network interface statistics
- `/proc/<pid>/stat`: Process CPU usage
- `/proc/<pid>/status`: Process memory usage
- `/proc/<pid>/io`: Process disk I/O

**Collection Process**:

```rust
// Every 60 seconds:
1. Refresh system information (sysinfo crate)
2. Collect system metrics (CPU, memory, load)
3. Read /proc/diskstats for disk I/O
4. Read /proc/net/dev for network stats
5. Iterate all processes for top consumers
6. Read /proc/<pid>/io for process disk I/O
7. Sort and select top 3 for each category
8. Send metrics to aggregator
```

#### 2. Process Metrics Collection

**CPU Usage**:
- Uses `sysinfo::Process::cpu_usage()`
- Reads `/proc/<pid>/stat` fields 14 (utime) and 15 (stime)
- Calculates percentage: `(cpu_time / total_time) * 100`
- Sorted descending, top 3 stored

**Memory Usage**:
- Uses `sysinfo::Process::memory()`
- Reads `/proc/<pid>/status` `VmRSS` field
- Returns Resident Set Size (RSS) in bytes
- Converted to MB, sorted descending, top 3 stored

**Disk I/O**:
- Reads `/proc/<pid>/io` directly
- Parses `read_bytes:` and `write_bytes:` lines
- Sums read + write for total I/O
- Sorted descending, top 3 stored

**Data Format**:
```rust
Metric {
    timestamp: i64,
    hostname: String,
    metric_type: "process",
    metric_name: "process_cpu_usage" | "process_memory_mb" | "process_disk_io_mb",
    value: f64,
    tags: {
        "process_name": "nginx",
        "pid": "1234",
        "rank": "1"  // 1, 2, or 3
    }
}
```

### Metric Types

#### System Metrics

| Metric Name | Type | Unit | Source |
|------------|------|------|--------|
| `cpu_usage_percent` | system | % | `/proc/stat` |
| `memory_usage_percent` | system | % | `/proc/meminfo` |
| `memory_used_mb` | system | MB | `/proc/meminfo` |
| `memory_total_mb` | system | MB | `/proc/meminfo` |
| `load_avg_1min` | system | float | `/proc/loadavg` |
| `load_avg_5min` | system | float | `/proc/loadavg` |
| `load_avg_15min` | system | float | `/proc/loadavg` |
| `process_count` | system | count | Process enumeration |

#### Disk I/O Metrics

| Metric Name | Type | Unit | Source |
|------------|------|------|--------|
| `disk_reads_per_sec` | disk | ops/sec | `/proc/diskstats` |
| `disk_writes_per_sec` | disk | ops/sec | `/proc/diskstats` |
| `disk_latency_ms` | disk | ms | `/proc/diskstats` |

**Calculation**:
- Reads previous snapshot from `last_disk_stats`
- Calculates rate: `(current - previous) / time_diff`
- Time difference: 60 seconds

#### Network Metrics

| Metric Name | Type | Unit | Source |
|------------|------|------|--------|
| `network_packets_sent` | network | packets/sec | `/proc/net/dev` |
| `network_packets_received` | network | packets/sec | `/proc/net/dev` |
| `network_bytes_sent` | network | bytes/sec | `/proc/net/dev` |
| `network_bytes_received` | network | bytes/sec | `/proc/net/dev` |
| `network_drops` | network | count | `/proc/net/dev` |

**Calculation**:
- Reads previous snapshot from `last_net_stats`
- Calculates rate: `(current - previous) / time_diff`
- Excludes loopback interface

#### Process Metrics

| Metric Name | Type | Unit | Source |
|------------|------|------|--------|
| `process_cpu_usage` | process | % | `/proc/<pid>/stat` |
| `process_memory_mb` | process | MB | `/proc/<pid>/status` |
| `process_disk_io_mb` | process | MB | `/proc/<pid>/io` |

**Tags**:
- `process_name`: Process executable name
- `pid`: Process ID
- `rank`: Ranking (1, 2, or 3)

---

## Storage Layer

### ClickHouse Schema

#### Metrics Table

```sql
CREATE TABLE metrics (
    timestamp DateTime,
    hostname String,
    metric_type String,
    metric_name String,
    value Float64,
    tags Map(String, String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, metric_type, timestamp)
TTL timestamp + INTERVAL 90 DAY;
```

**Indexing**:
- Partitioned by month for efficient queries
- Ordered by hostname, metric_type, timestamp
- 90-day TTL for automatic data retention

**Tags Map**:
- Used for process metadata (process_name, pid, rank)
- Enables filtering: `WHERE tags['process_name'] = 'nginx'`
- Accessed via: `mapGet(tags, 'key')` or `tags['key']`

#### Reports Tables

**Hourly Reports**:
```sql
CREATE TABLE hourly_reports (
    report_id String,
    timestamp DateTime,
    hostname String,
    system_health UInt8,
    metrics String,  -- JSON
    ai_insights String,  -- JSON
    recommendations String,  -- JSON
    capacity_forecast String  -- JSON
) ENGINE = MergeTree()
ORDER BY (hostname, timestamp)
TTL timestamp + INTERVAL 1 YEAR;
```

**Daily Reports**:
```sql
CREATE TABLE daily_reports (
    report_id String,
    date Date,
    hostname String,
    metrics String,  -- JSON
    ai_summary String,  -- JSON
    trends String,  -- JSON
    recommendations String  -- JSON
) ENGINE = MergeTree()
ORDER BY (hostname, date)
TTL timestamp + INTERVAL 2 YEAR;
```

### Query Patterns

#### Aggregation Query

```sql
SELECT 
    metric_name,
    min(value) as min_value,
    max(value) as max_value,
    avg(value) as avg_value,
    quantile(0.5)(value) as p50,
    quantile(0.95)(value) as p95,
    quantile(0.99)(value) as p99,
    stddevPop(value) as std_dev,
    count(*) as sample_count
FROM metrics
WHERE timestamp >= '2025-11-30 18:00:00' 
  AND timestamp <= '2025-11-30 19:00:00'
  AND metric_name = 'cpu_usage_percent'
GROUP BY metric_name
```

#### Top Processes Query

```sql
SELECT 
    mapGet(tags, 'process_name') as process_name,
    mapGet(tags, 'pid') as pid,
    avg(value) as avg_value,
    max(value) as max_value
FROM metrics
WHERE timestamp >= '2025-11-30 18:00:00'
  AND timestamp <= '2025-11-30 19:00:00'
  AND metric_name = 'process_cpu_usage'
  AND has(tags, 'process_name')
GROUP BY process_name, pid
HAVING process_name != ''
ORDER BY avg_value DESC
LIMIT 10
```

#### Raw Metrics Query (for charts)

```sql
SELECT 
    timestamp,
    value
FROM metrics
WHERE timestamp >= '2025-11-30 18:00:00'
  AND timestamp <= '2025-11-30 19:00:00'
  AND metric_name = 'cpu_usage_percent'
ORDER BY timestamp ASC
LIMIT 1000
```

---

## Analysis Engine

### Hourly Analysis

**Trigger**: Every hour at minute 0 (cron: `minute=0`)

**Process**:

1. **Fetch Metrics** (`fetch_metrics`):
   - Time range: Last 1 hour
   - Fallback: Last 15 minutes if no data found
   - Aggregates: CPU, memory, disk I/O, network

2. **Calculate Baseline** (`calculate_baseline`):
   - 7-day historical baseline (currently mock data)
   - Used for anomaly detection

3. **Detect Anomalies** (`detect_anomalies`):
   - Z-score calculation: `(current - mean) / std_dev`
   - Threshold: 2.5 sigma
   - Critical: > 3.5 sigma

4. **Fetch Top Processes** (`fetch_top_processes`):
   - Queries ClickHouse for process metrics
   - Aggregates by process name and PID
   - Returns top 3 for CPU, memory, disk I/O

5. **Generate AI Insights** (`generate_ai_insights`):
   - Builds context from metrics, baseline, anomalies
   - Sends to Gemini API
   - Parses JSON response for insights

6. **Calculate Health Score** (`calculate_health_score`):
   - Base score: 100
   - Deducts for high CPU (>80%: -20, >60%: -10)
   - Deducts for high memory (>85%: -20, >70%: -10)
   - Deducts for anomalies (-5 per anomaly)
   - Clamped: 0-100

7. **Build Report**:
   - Combines all data into report structure
   - Stores in `latest_report` global variable
   - Returns to API endpoint

### Report Structure

```json
{
  "report_id": "2025-11-30T19:00:00",
  "period": "2025-11-30T18:00:00 to 2025-11-30T19:00:00",
  "system_health": {
    "overall_score": 85,
    "status": "healthy",
    "pressure_points": ["cpu", "memory"]
  },
  "resource_usage": {
    "cpu": {"average": 45.2, "peak": 78.3},
    "memory": {"average": 62.1, "peak": 71.8},
    "disk_io": {
      "reads_per_sec": 1234.0,
      "writes_per_sec": 890.0,
      "latency_ms": 12.5
    },
    "network": {
      "packets_sent": 45000.0,
      "packets_received": 89000.0,
      "drops": 23.0
    }
  },
  "top_processes": {
    "cpu": [
      {"name": "nginx", "pid": "1234", "average": 15.2, "peak": 25.3},
      {"name": "python", "pid": "5678", "average": 12.1, "peak": 18.5},
      {"name": "node", "pid": "9012", "average": 8.3, "peak": 12.1}
    ],
    "memory": [...],
    "disk_io": [...]
  },
  "ai_insights": {
    "critical_alerts": ["Network packet drops increased 300%"],
    "recommendations": [
      {
        "title": "Optimize network buffer",
        "description": "...",
        "priority": "high"
      }
    ],
    "capacity_forecast": {...},
    "config_optimizations": [...]
  },
  "anomalies": [...]
}
```

---

## Frontend

### Architecture

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Charts**: Recharts
- **Styling**: Tailwind CSS
- **HTTP**: Fetch API

### Components

#### MetricsChart (Base Component)

**Props**:
- `title`: Chart title
- `endpoint`: API endpoint (e.g., `/api/metrics/cpu`)
- `dataKey`: Data key for single-line charts
- `color`: Line color
- `yAxisLabel`: Y-axis label
- `timeRange`: Time range (1h, 6h, 24h, 7d)

**Features**:
- Auto-refresh every 30 seconds
- Error handling
- Loading states
- Time range selection

#### CPUChart / MemoryChart

Single-line charts using `MetricsChart`:
- CPU: Blue line, percentage format
- Memory: Purple line, percentage format

#### DiskIOChart / NetworkChart

Multi-line charts:
- Disk I/O: Green (reads), Orange (writes)
- Network: Blue (sent), Purple (received)

**Data Format**:
```typescript
[
  {timestamp: "2025-11-30T19:00:00", reads: 1234.5, writes: 890.2},
  {timestamp: "2025-11-30T19:01:00", reads: 1456.7, writes: 923.1},
  ...
]
```

### API Integration

**Base URL**: Configured via nginx proxy
- Development: `http://localhost:6800`
- Production: `/api` proxied to `analysis:8800`

**Endpoints Used**:
- `GET /api/`: Health check
- `GET /api/reports/latest`: Latest hourly report
- `GET /api/metrics/cpu?start=...&end=...`: CPU metrics
- `GET /api/metrics/memory?start=...&end=...`: Memory metrics
- `GET /api/metrics/disk?start=...&end=...`: Disk I/O metrics
- `GET /api/metrics/network?start=...&end=...`: Network metrics
- `POST /api/analysis/trigger/hourly`: Trigger hourly analysis

---

## API Reference

### Health & Status

#### `GET /api/`
Returns service health status.

**Response**:
```json
{
  "status": "running",
  "service": "AncientReport AI Analysis Engine",
  "version": "1.0.0"
}
```

### Reports

#### `GET /api/reports/latest`
Returns the latest hourly analysis report.

**Response**: See [Report Structure](#report-structure)

#### `POST /api/analysis/trigger/hourly`
Manually triggers an hourly analysis.

**Response**:
```json
{
  "status": "success",
  "message": "Hourly analysis triggered",
  "report": {...}
}
```

### Metrics

#### `GET /api/metrics/cpu`
Returns CPU usage metrics for charting.

**Query Parameters**:
- `start` (optional): ISO 8601 timestamp
- `end` (optional): ISO 8601 timestamp

**Response**:
```json
{
  "data": [
    {"timestamp": "2025-11-30T19:00:00", "value": 45.2},
    {"timestamp": "2025-11-30T19:01:00", "value": 46.1},
    ...
  ]
}
```

#### `GET /api/metrics/memory`
Returns memory usage metrics.

**Same format as CPU endpoint.**

#### `GET /api/metrics/disk`
Returns disk I/O metrics.

**Response**:
```json
{
  "data": [
    {"timestamp": "2025-11-30T19:00:00", "reads": 1234.5, "writes": 890.2},
    ...
  ]
}
```

#### `GET /api/metrics/network`
Returns network metrics.

**Response**:
```json
{
  "data": [
    {"timestamp": "2025-11-30T19:00:00", "sent": 45000.0, "received": 89000.0},
    ...
  ]
}
```

### Debug

#### `GET /api/debug/metrics`
Debug endpoint to check if metrics exist in ClickHouse.

**Response**:
```json
{
  "status": "ok",
  "time_range": "2025-11-29 19:00:00 to 2025-11-30 19:00:00",
  "metrics_found": 15,
  "metrics": [
    {
      "metric_name": "cpu_usage_percent",
      "min": 10.2,
      "max": 85.3,
      "avg": 45.1,
      "sample_count": 3600
    },
    ...
  ],
  "recent_cpu_data": true,
  "latest_report": true
}
```

---

## Data Flow

### Metric Collection Flow

```
1. Agent (Rust)
   └─> ProcCollector collects metrics every 60s
       ├─> System metrics (CPU, memory, load)
       ├─> Disk I/O from /proc/diskstats
       ├─> Network from /proc/net/dev
       └─> Top processes from /proc/<pid>/*
       
2. MetricAggregator
   └─> Batches metrics (up to 10000)
       └─> Sends to ClickHouse every 60s
       
3. ClickHouse
   └─> Stores in 'metrics' table
       └─> Partitioned by month
           └─> Indexed by (hostname, metric_type, timestamp)
```

### Analysis Flow

```
1. Scheduler (APScheduler)
   └─> Triggers hourly analysis at :00
       
2. HourlyAnalyzer
   ├─> Fetches metrics from ClickHouse (last hour)
   ├─> Aggregates by metric_name
   ├─> Fetches top processes
   ├─> Detects anomalies (Z-score)
   ├─> Generates AI insights (Gemini API)
   └─> Builds report
       
3. Report Storage
   └─> Stored in 'latest_report' global variable
       └─> Available via /api/reports/latest
```

### Frontend Flow

```
1. App.tsx
   ├─> Fetches /api/reports/latest (every 30s)
   └─> Renders report data
       
2. Chart Components
   ├─> Fetch metrics from /api/metrics/*
   ├─> Parse timestamps and values
   └─> Render with Recharts
       
3. User Interaction
   └─> Click "Trigger Analysis"
       └─> POST /api/analysis/trigger/hourly
           └─> Updates report state
```

---

## Metrics Details

### System Metrics

#### CPU Usage (`cpu_usage_percent`)

**Collection**:
- Source: `sysinfo::System::global_cpu_info().cpu_usage()`
- Reads: `/proc/stat`
- Calculation: `(idle_time / total_time) * 100`
- Range: 0-100%

**Storage**: Every 60 seconds

#### Memory Usage (`memory_usage_percent`)

**Collection**:
- Source: `sysinfo::System::total_memory()` and `used_memory()`
- Reads: `/proc/meminfo`
- Calculation: `(used / total) * 100`
- Range: 0-100%

**Storage**: Every 60 seconds

#### Load Average

**Collection**:
- Source: `sysinfo::System::load_average()`
- Reads: `/proc/loadavg`
- Metrics:
  - `load_avg_1min`: 1-minute average
  - `load_avg_5min`: 5-minute average
  - `load_avg_15min`: 15-minute average

### Disk I/O Metrics

#### Reads/Writes per Second

**Collection**:
- Source: `/proc/diskstats`
- Format: `major minor name reads reads_merged reads_sectors reads_time writes writes_merged writes_sectors writes_time io_in_progress io_time_ms io_time_weighted_ms`
- Calculation:
  ```
  reads_per_sec = (current_reads - previous_reads) / time_diff
  writes_per_sec = (current_writes - previous_writes) / time_diff
  ```
- Time difference: 60 seconds

**Storage**: Every 60 seconds (requires previous snapshot)

#### Latency

**Calculation**:
```
latency_ms = (io_time_diff_ms) / (ops_diff)
```
- `io_time_diff`: Difference in `io_time_ms` between snapshots
- `ops_diff`: Difference in total operations (reads + writes)

### Network Metrics

#### Packets/Bytes per Second

**Collection**:
- Source: `/proc/net/dev`
- Format: `interface rx_bytes rx_packets rx_errs rx_drop ... tx_bytes tx_packets ...`
- Calculation:
  ```
  packets_sent_per_sec = (current_tx_packets - previous_tx_packets) / time_diff
  packets_received_per_sec = (current_rx_packets - previous_rx_packets) / time_diff
  ```
- Excludes: Loopback interface (`lo`)

**Storage**: Every 60 seconds (requires previous snapshot)

### Process Metrics

#### CPU Usage per Process

**Collection**:
- Source: `/proc/<pid>/stat`
- Fields: 14 (utime), 15 (stime)
- Calculation: `(cpu_time / total_time) * 100`
- Stored: Top 3 processes

**Tags**:
- `process_name`: Executable name
- `pid`: Process ID
- `rank`: 1, 2, or 3

#### Memory Usage per Process

**Collection**:
- Source: `/proc/<pid>/status`
- Field: `VmRSS` (Resident Set Size)
- Unit: MB (converted from bytes)
- Stored: Top 3 processes

#### Disk I/O per Process

**Collection**:
- Source: `/proc/<pid>/io`
- Fields: `read_bytes:`, `write_bytes:`
- Calculation: `total_io = read_bytes + write_bytes`
- Unit: MB (converted from bytes)
- Stored: Top 3 processes

**Note**: Cumulative since process start, not rate-based.

---

## Process Monitoring

### Collection Algorithm

```rust
async fn collect_top_processes() {
    // 1. Refresh process list
    system.refresh_processes();
    
    // 2. Collect all processes
    for (pid, process) in system.processes() {
        // CPU
        let cpu = process.cpu_usage();
        cpu_processes.push((cpu, name, pid));
        
        // Memory
        let memory = process.memory();
        memory_processes.push((memory, name, pid));
        
        // Disk I/O
        let io_content = read_file(format!("/proc/{}/io", pid));
        let total_io = parse_read_bytes(io_content) + parse_write_bytes(io_content);
        disk_io_processes.push((total_io, name, pid));
    }
    
    // 3. Sort descending
    cpu_processes.sort_by(|a, b| b.0.partial_cmp(&a.0));
    memory_processes.sort_by(|a, b| b.0.cmp(&a.0));
    disk_io_processes.sort_by(|a, b| b.0.cmp(&a.0));
    
    // 4. Take top 3
    for (rank, process) in cpu_processes.iter().take(3).enumerate() {
        send_metric(process_cpu_usage, value, tags: {rank: rank+1});
    }
}
```

### Aggregation in Analysis

```python
async def fetch_top_processes(start_time, end_time):
    # Query ClickHouse
    sql = """
    SELECT 
        mapGet(tags, 'process_name') as process_name,
        mapGet(tags, 'pid') as pid,
        avg(value) as avg_value,
        max(value) as max_value
    FROM metrics
    WHERE metric_name = 'process_cpu_usage'
      AND timestamp >= start_time AND timestamp <= end_time
    GROUP BY process_name, pid
    ORDER BY avg_value DESC
    LIMIT 10
    """
    
    # Returns top processes by average usage over the hour
    return top_processes
```

---

## Deployment

### Docker Compose

**Services**:
1. **clickhouse**: ClickHouse database
   - Ports: 6123 (HTTP), 6001 (Native)
   - Volume: `clickhouse_data`
   
2. **agent**: Rust agent
   - Network: `host` (for /proc access)
   - Privileged: `true` (for eBPF)
   - Volumes: `/proc`, `/sys/kernel/debug`
   
3. **analysis**: Python analysis engine
   - Port: 6800 (external) → 8800 (internal)
   - Environment: ClickHouse connection, AI API key
   
4. **ui**: React frontend
   - Port: 6080
   - Nginx proxy to analysis service

### Configuration

**Agent Config** (`agent/config.toml`):
```toml
[agent]
hostname = "auto-detect"
collection_interval = "60s"

[clickhouse]
url = "http://clickhouse:8123"
database = "AncientReport"
username = "AncientReport"
password = "AncientReport"

[ai]
provider = "google"
api_key = "..."
model = "gemini-2.5-flash-lite"
```

### Environment Variables

**Analysis Service**:
- `CLICKHOUSE_HOST`: ClickHouse hostname
- `CLICKHOUSE_PORT`: ClickHouse HTTP port
- `CLICKHOUSE_DB`: Database name
- `CLICKHOUSE_USER`: Username
- `CLICKHOUSE_PASSWORD`: Password
- `GEMINI_API_KEY`: Google Gemini API key
- `AI_PROVIDER`: AI provider (google)
- `AI_MODEL`: Model name

### Network Architecture

```
Internet
   │
   ├─> UI (Port 6080)
   │    └─> Nginx
   │         └─> /api/* → Analysis (Port 8800)
   │
   └─> Analysis (Port 6800)
        └─> ClickHouse (Port 6001)
        
Agent (Host Network)
   └─> ClickHouse (Port 6001)
```

---

## Performance Considerations

### Collection Overhead

- **Agent**: < 3% CPU overhead
- **Collection Interval**: 60 seconds (configurable)
- **Batch Size**: Up to 10,000 metrics per batch
- **ClickHouse Insert**: Batched every 60 seconds

### Storage Efficiency

- **Partitioning**: Monthly partitions for efficient queries
- **TTL**: 90 days for metrics, 1 year for hourly reports, 2 years for daily reports
- **Compression**: ClickHouse LZ4 compression
- **Indexing**: Primary key on (hostname, metric_type, timestamp)

### Query Performance

- **Aggregation Queries**: Use GROUP BY on metric_name
- **Time Range Queries**: Leverage timestamp partitioning
- **Top Processes**: Limited to 10 results, ordered by value
- **Chart Queries**: Limited to 1000 data points

---

## Limitations

1. **Network Per-Process**: Not implemented (requires eBPF or complex /proc parsing)
2. **Historical Baseline**: Currently uses mock data (7-day baseline not implemented)
3. **Disk I/O Per-Process**: Cumulative values, not rate-based
4. **eBPF Collection**: Placeholder, not fully implemented
5. **Multi-Host**: Single host monitoring (can be extended)

---

## Future Enhancements

1. **eBPF Integration**: Real-time network and disk I/O per process
2. **Historical Baselines**: 7-day and 30-day baseline calculation
3. **Alerting**: Telegram/Slack notifications for critical alerts
4. **Multi-Host**: Support for multiple hosts in one dashboard
5. **Custom Metrics**: User-defined metric collection
6. **Export**: CSV/JSON export of reports
7. **Real-time Streaming**: WebSocket for real-time metric updates

---

## Troubleshooting

### Metrics Showing Zero

1. Check agent logs: `docker-compose logs agent`
2. Verify ClickHouse connection: `docker-compose logs clickhouse`
3. Check debug endpoint: `GET /api/debug/metrics`
4. Verify data exists: Query ClickHouse directly

### Charts Not Loading

1. Check API endpoints: `curl http://localhost:6800/api/metrics/cpu`
2. Verify nginx proxy: Check `ui/nginx.conf`
3. Check browser console for errors
4. Verify CORS settings in FastAPI

### Analysis Not Running

1. Check scheduler: `docker-compose logs analysis | grep scheduler`
2. Verify cron job: Check APScheduler logs
3. Manual trigger: `POST /api/analysis/trigger/hourly`
4. Check AI API key: Verify Gemini API key is valid

---

## References

- [ClickHouse Documentation](https://clickhouse.com/docs)
- [sysinfo Rust Crate](https://docs.rs/sysinfo/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Recharts Documentation](https://recharts.org/)

---

**Last Updated**: 2025-11-30
**Version**: 1.0.0

