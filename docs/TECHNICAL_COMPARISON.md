# AncientReport: Technical Architecture & Comparison

## Executive Summary

AncientReport is a **unified observability platform** that combines the capabilities of Prometheus, Grafana, Zabbix, and more into a single, cohesive system with AI-powered analysis.

---

## Traditional Monitoring Stack Overview

### 🔵 Prometheus
**What it is:** A time-series database with a pull-based metrics collection model.

**How it works:**
```
┌─────────────────────────────────────────────────────────────────┐
│                        PROMETHEUS ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐      HTTP GET /metrics      ┌──────────────┐    │
│   │  Target  │ ◄──────────────────────────►│  Prometheus  │    │
│   │  :9100   │   (scrape every 15s)        │   Server     │    │
│   └──────────┘                              │              │    │
│                                             │  ┌────────┐  │    │
│   ┌──────────┐                              │  │ TSDB   │  │    │
│   │  Target  │ ◄───────────────────────────►│  │(local) │  │    │
│   │  :9090   │                              │  └────────┘  │    │
│   └──────────┘                              └──────────────┘    │
│                                                                  │
│   Exporters Required:                                            │
│   • node_exporter (system metrics)                               │
│   • blackbox_exporter (probes)                                   │
│   • custom exporters per application                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Limitations:**
- Pull-only model (requires network access from Prometheus → targets)
- No native visualization (requires Grafana)
- Local storage only (federation for scale)
- PromQL learning curve
- No built-in SNMP support
- No eBPF/deep system visibility
- Requires multiple exporters per target

---

### 🟠 Grafana
**What it is:** A visualization and dashboarding layer (NOT a data collector).

**How it works:**
```
┌─────────────────────────────────────────────────────────────────┐
│                        GRAFANA ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌────────────────┐          ┌────────────────┐                │
│   │   Prometheus   │          │    InfluxDB    │                │
│   └───────┬────────┘          └───────┬────────┘                │
│           │                           │                          │
│           ▼                           ▼                          │
│   ┌───────────────────────────────────────────────┐             │
│   │                  GRAFANA                       │             │
│   │  ┌─────────────────────────────────────────┐  │             │
│   │  │           Visualization Layer           │  │             │
│   │  │  • Dashboards                           │  │             │
│   │  │  • Panels (graphs, tables, gauges)     │  │             │
│   │  │  • Alerts (since Grafana 8+)           │  │             │
│   │  └─────────────────────────────────────────┘  │             │
│   └───────────────────────────────────────────────┘             │
│                                                                  │
│   ⚠️ Grafana is ONLY visualization                               │
│   • Does NOT collect any data                                    │
│   • Does NOT store any metrics                                   │
│   • Requires external datasources                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Limitations:**
- No data collection capability
- Dashboard management overhead
- Complex multi-datasource queries
- No correlation between data sources
- Separate learning curve for each datasource's query language

---

### 🟢 Zabbix / SNMP Monitoring
**What it is:** Traditional agent-based monitoring with SNMP support.

**How it works:**
```
┌─────────────────────────────────────────────────────────────────┐
│                     ZABBIX / SNMP ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────┐    SNMP GET/WALK     ┌──────────────────┐    │
│   │   Network   │ ◄───────────────────►│                  │    │
│   │   Device    │    UDP 161           │                  │    │
│   │ (Router,SW) │                      │                  │    │
│   └─────────────┘                      │                  │    │
│                                         │   Zabbix Server  │    │
│   ┌─────────────┐    Agent Protocol    │                  │    │
│   │   Server    │ ◄───────────────────►│   ┌──────────┐  │    │
│   │  (Zabbix    │    TCP 10050         │   │ MySQL/   │  │    │
│   │   Agent)    │                      │   │ PostgreSQL│  │    │
│   └─────────────┘                      │   └──────────┘  │    │
│                                         └──────────────────┘    │
│                                                                  │
│   Components Required:                                           │
│   • Zabbix Server                                                │
│   • Zabbix Agent (per host)                                     │
│   • Database (MySQL/PostgreSQL)                                 │
│   • Zabbix Frontend (PHP)                                       │
│   • SNMP Trap receiver                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Limitations:**
- Heavy resource usage (PHP frontend, MySQL)
- Complex template management
- SNMP polling overhead
- Agent installation required on every host
- Limited container visibility
- No eBPF support
- Outdated UI/UX

---

## 🚀 AncientReport Architecture

### Unified Data Pipeline
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ANCIENTREPORT ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   AGENT LAYER (Rust + eBPF)                                                     │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌──────────────┐ │  │
│   │  │  System       │ │  Container    │ │  eBPF         │ │  Service     │ │  │
│   │  │  Collector    │ │  Monitor      │ │  Probes       │ │  Monitors    │ │  │
│   │  │  • CPU/Mem    │ │  • Docker     │ │  • Network    │ │  • Kafka     │ │  │
│   │  │  • Disk       │ │  • K8s Pods   │ │  • Syscalls   │ │  • Redis     │ │  │
│   │  │  • Network    │ │  • States     │ │  • Latency    │ │  • Postgres  │ │  │
│   │  │  • Processes  │ │  • Resources  │ │  • Connections│ │  • MongoDB   │ │  │
│   │  └───────────────┘ └───────────────┘ └───────────────┘ └──────────────┘ │  │
│   │                              │                                            │  │
│   │                              ▼                                            │  │
│   │                  ┌───────────────────────┐                               │  │
│   │                  │   NATS JetStream      │  (message streaming)          │  │
│   │                  │   with persistence    │                               │  │
│   │                  └───────────────────────┘                               │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                             │
│   ANALYSIS LAYER (Python FastAPI)  ▼                                            │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │  ┌──────────────────┐                                                     │  │
│   │  │ Ingestion Gateway│ ◄── Consumes from NATS, batches to ClickHouse     │  │
│   │  └──────────────────┘                                                     │  │
│   │                                                                           │  │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐│  │
│   │  │ Prometheus  │ │ SNMP        │ │ Recording   │ │ AI Analysis         ││  │
│   │  │ Scraper     │ │ Poller      │ │ Rules       │ │ (Gemini/GPT)        ││  │
│   │  │ • /metrics  │ │ • OID polls │ │ • Agg/Alert │ │ • Anomaly detection ││  │
│   │  │ • targets   │ │ • templates │ │ • PromQL-ish│ │ • Chat assistance   ││  │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────┘│  │
│   │                                                                           │  │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐│  │
│   │  │ Alerts      │ │ Dashboards  │ │ Topology    │ │ Auto-Remediation    ││  │
│   │  │ Engine      │ │ API         │ │ Discovery   │ │ Engine              ││  │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────┘│  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                             │
│   STORAGE LAYER                    ▼                                            │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                        ClickHouse                                         │  │
│   │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐               │  │
│   │  │ metrics        │ │ network_flows  │ │ docker_containers│             │  │
│   │  │ (time-series)  │ │ (eBPF data)    │ │ (container state)│             │  │
│   │  └────────────────┘ └────────────────┘ └────────────────┘               │  │
│   │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐               │  │
│   │  │ snmp_metrics   │ │ scraped_metrics│ │ alerts          │             │  │
│   │  │ (SNMP OIDs)    │ │ (Prometheus)   │ │ (events)        │             │  │
│   │  └────────────────┘ └────────────────┘ └────────────────┘               │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                             │
│   UI LAYER (React)                 ▼                                            │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │         Single-Page Application with Real-time Updates                   │  │
│   │  • Unified dashboard for ALL data sources                                │  │
│   │  • Live WebSocket streaming                                              │  │
│   │  • Built-in charting (no Grafana needed)                                │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Technical Deep Dive: Key Components

### 1. Agent (Rust + eBPF)
**Location:** `agent/src/`

The agent is written in **Rust** for:
- Memory safety without garbage collection pauses
- Low CPU overhead (<1% on most systems)
- Native eBPF integration

**Key Collectors:**
| Collector | Data Collected | Technology |
|-----------|----------------|------------|
| `proc_collector.rs` | CPU, Memory, Processes | `/proc` filesystem |
| `network_collector.rs` | Connections, Latency | eBPF + `/proc/net` |
| `docker_collector.rs` | Container states | Docker socket |
| `kafka_monitor.rs` | Topics, Lag, Offsets | JMX/Container inspection |
| `redis_monitor.rs` | Memory, Keys, Clients | Redis INFO command |
| `postgres_monitor.rs` | Connections, Queries | pg_stat views |

**eBPF Integration:**
```rust
// agent/src/ebpf/network_monitor.rs
// Attaches to kernel tracepoints for network visibility

#[tracepoint(category = "net", name = "net_dev_xmit")]
fn trace_network_xmit(ctx: TracePointContext) -> u32 {
    // Captures every packet transmitted
    // No kernel modification required
    // Zero-copy access to packet data
}
```

**Why eBPF is superior:**
- Kernel-level visibility without kernel modules
- See ALL network connections (even short-lived)
- Capture syscall latency at microsecond precision
- No application modification required

---

### 2. Message Streaming (NATS JetStream)
**Why NATS instead of direct HTTP:**

```
Traditional (Prometheus):          AncientReport (NATS):
┌───────┐    HTTP     ┌───────┐    ┌───────┐   NATS    ┌───────┐
│ Agent │ ──────────► │Server │    │ Agent │ ────────► │ NATS  │
└───────┘   PULL      └───────┘    └───────┘   PUSH    │Stream │
                                                        │       │
❌ Requires server→agent access     ✅ Agents push     │   │   │
❌ Polling overhead                  ✅ Real-time       ▼   ▼   │
❌ Lost data if server down          ✅ Persistence    ┌───────┐
                                                       │AnalysisService │
                                                       └───────┘
```

**Benefits:**
- **Push-based**: Agents behind NAT/firewalls work seamlessly
- **Persistence**: Messages survive service restarts
- **Back-pressure**: Automatic flow control under load
- **Batching**: Efficient for high-frequency metrics

---

### 3. Storage (ClickHouse)
**Why ClickHouse over Prometheus TSDB:**

| Feature | Prometheus TSDB | ClickHouse |
|---------|-----------------|------------|
| Query Language | PromQL | SQL |
| Compression | ~1.5 bytes/sample | ~0.3 bytes/sample |
| Horizontal Scaling | Limited | Native clusters |
| Join Operations | Not supported | Full SQL JOINs |
| Retention | Single-node | Distributed TTL |
| Ad-hoc Queries | Limited | Full SQL |

**Schema Example:**
```sql
-- All metrics in a single table with efficient columnar storage
CREATE TABLE metrics (
    timestamp DateTime64(3),
    hostname LowCardinality(String),
    metric String,
    value Float64,
    labels String  -- JSON for flexibility
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, metric, timestamp)
TTL timestamp + INTERVAL 90 DAY;
```

---

### 4. Prometheus-Compatible Scraping
**Location:** `analysis/src/api/prometheus.py`

AncientReport can scrape ANY Prometheus-compatible endpoint, replacing your Prometheus server:

```python
# Shared HTTP client with connection pooling
async def get_http_client() -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_keepalive_connections=20,
        max_connections=50,
    )
    return httpx.AsyncClient(limits=limits)

# Scrape loop with concurrency control
async def run_scraper_loop():
    while True:
        for target in enabled_targets:
            asyncio.create_task(_scrape_url(target))
        await asyncio.sleep(5)
```

**You can add:**
- Kafka Exporter endpoints
- Node Exporter endpoints
- Custom application `/metrics`
- ANY Prometheus exposition format

---

### 5. SNMP Monitoring
**Location:** `analysis/src/api/snmp.py`

Full SNMP v1/v2c/v3 support with templates:

```python
# Built-in templates for common devices
DEFAULT_TEMPLATES = [
    {
        "name": "Linux Server",
        "vendor": "Generic",
        "oids": [
            {"oid": "1.3.6.1.4.1.2021.11.9.0", "name": "CPU User", "type": "gauge"},
            {"oid": "1.3.6.1.4.1.2021.4.5.0", "name": "Total Memory", "type": "gauge"},
            # ... 20+ OIDs
        ]
    },
    {"name": "Cisco Router", ...},
    {"name": "APC UPS", ...}
]
```

---

### 6. AI-Powered Analysis
**Location:** `analysis/src/api/ai_chat.py`

```python
# Gemini/GPT integration for intelligent analysis
async def analyze_metrics(metrics_data):
    prompt = f"""
    Analyze these server metrics and identify:
    1. Anomalies
    2. Performance bottlenecks
    3. Capacity planning recommendations
    
    Data: {metrics_data}
    """
    response = await gemini.generate(prompt)
    return response
```

---

## Comparison Summary

| Capability | Prometheus + Grafana + Zabbix | AncientReport |
|------------|------------------------------|---------------|
| **Components to deploy** | 5+ (Prometheus, Grafana, Exporters, Zabbix, DB) | 4 (Agent, Analysis, ClickHouse, NATS) |
| **Pull vs Push** | Pull only | Push (survives NAT/firewalls) |
| **SNMP Support** | Requires Zabbix or separate tool | Built-in with templates |
| **Prometheus Scraping** | Native | Compatible (replaces Prometheus) |
| **Container Visibility** | Limited (cAdvisor needed) | Native Docker/K8s integration |
| **eBPF Network** | Not available | Full kernel-level visibility |
| **Storage** | Multiple DBs | Single ClickHouse (SQL queries) |
| **Visualization** | Grafana (separate) | Built-in UI |
| **AI Analysis** | Not available | Gemini/GPT integration |
| **Auto-Remediation** | Manual scripts | Built-in with approval workflow |
| **Query Language** | PromQL (Prometheus) + SQL (Zabbix) | SQL only |
| **Learning Curve** | High (multiple tools) | Low (single platform) |

---

## Why AncientReport is Better

### 1. **Unified Data Model**
All metrics (system, container, SNMP, Prometheus) stored in the same format, queryable with SQL:
```sql
-- Query across ALL data sources with a single query
SELECT hostname, metric, avg(value)
FROM metrics
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY hostname, metric
```

### 2. **No Exporter Hell**
Traditional setup requires:
- node_exporter for system metrics
- cAdvisor for containers
- redis_exporter for Redis
- kafka_exporter for Kafka
- ... one exporter per service

**AncientReport**: Single agent discovers and monitors everything automatically.

### 3. **eBPF Superpowers**
See what other tools can't:
- Per-process network latency
- Connection establishment rates
- Syscall patterns
- Short-lived connections (missed by polling)

### 4. **AI-Native**
Built-in AI assistant that understands your infrastructure context:
- "Why is CPU high?"
- "What changed in the last hour?"
- "Predict disk full time"

### 5. **Auto-Remediation**
Not just monitoring—acting:
```python
# Automatic response to high memory
if memory_usage > 90%:
    await run_remediation("restart_container", container_id)
```

---

## Deployment Comparison

### Traditional Stack
```bash
# Prometheus
docker run -d prom/prometheus

# Grafana  
docker run -d grafana/grafana

# Node Exporter (every host)
docker run -d prom/node-exporter

# Zabbix Server
docker run -d zabbix/zabbix-server-mysql

# Zabbix Frontend
docker run -d zabbix/zabbix-web-nginx-mysql

# MySQL for Zabbix
docker run -d mysql:5.7

# Total: 6+ containers, multiple configurations
```

### AncientReport
```bash
# Complete stack
docker compose up -d

# Total: 4 containers, single docker-compose.yml
```

---

## Conclusion

AncientReport consolidates the functionality of **Prometheus** (metrics scraping), **Grafana** (visualization), **Zabbix** (SNMP + alerting), and adds **eBPF deep visibility** and **AI analysis** into a single, cohesive platform.

**Key advantages:**
1. ✅ Single platform instead of 5+ tools
2. ✅ Push-based architecture (works behind NAT)
3. ✅ eBPF kernel-level visibility
4. ✅ SQL queries instead of multiple query languages
5. ✅ Built-in AI analysis
6. ✅ Auto-remediation capabilities
7. ✅ 10x simpler deployment and maintenance
