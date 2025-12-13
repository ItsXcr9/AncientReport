-- ClickHouse schema for AncientReport AI
-- Time-series metrics storage optimized for fast analytics

-- Raw metrics table (1-minute aggregations)
CREATE TABLE IF NOT EXISTS metrics (
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

-- Hourly analysis reports
CREATE TABLE IF NOT EXISTS hourly_reports (
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

-- Daily analysis reports
CREATE TABLE IF NOT EXISTS daily_reports (
    report_id String,
    date Date,
    hostname String,
    metrics String,  -- JSON
    ai_summary String,  -- JSON
    trends String,  -- JSON
    recommendations String  -- JSON
) ENGINE = MergeTree()
ORDER BY (hostname, date)
TTL date + INTERVAL 2 YEAR;

-- Configuration audit history
CREATE TABLE IF NOT EXISTS config_audits (
    timestamp DateTime,
    hostname String,
    config_type String,
    config_path String,
    config_content String,
    ai_review String,  -- JSON
    suggestions String  -- JSON
) ENGINE = MergeTree()
ORDER BY (hostname, timestamp)
TTL timestamp + INTERVAL 180 DAY;

-- System events and alerts
CREATE TABLE IF NOT EXISTS events (
    timestamp DateTime,
    hostname String,
    event_type String,
    severity Enum8('info' = 1, 'warning' = 2, 'critical' = 3),
    description String,
    metadata String  -- JSON
) ENGINE = MergeTree()
ORDER BY (hostname, timestamp)
TTL timestamp + INTERVAL 90 DAY;

-- Docker container stats
CREATE TABLE IF NOT EXISTS docker_containers (
    timestamp DateTime,
    container_id String,
    container_name String,
    image String,
    status String,
    cpu_percent Float64,
    memory_usage UInt64,
    memory_limit UInt64,
    memory_percent Float64,
    network_rx_bytes UInt64,
    network_tx_bytes UInt64,
    block_read_bytes UInt64,
    block_write_bytes UInt64,
    uptime_seconds UInt64,
    restart_count UInt32,
    created_at DateTime,
    hostname String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (hostname, timestamp, container_id)
TTL timestamp + INTERVAL 30 DAY;

-- Application settings (key-value store)
CREATE TABLE IF NOT EXISTS settings (
    setting_key String,
    setting_value String,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY setting_key;

-- ============================================
-- V3 TABLES: Container Application Monitoring
-- ============================================

-- Kafka Metrics (consumer lag, ISR, partitions)
CREATE TABLE IF NOT EXISTS kafka_metrics (
    timestamp DateTime,
    hostname String,
    broker_id String,
    container_id String,
    container_name String,
    metric_name String,
    value Float64,
    consumer_group String DEFAULT '',
    topic String DEFAULT '',
    partition Int32 DEFAULT -1
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, broker_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- Redis Metrics (memory, hit rate, clients, replication)
CREATE TABLE IF NOT EXISTS redis_metrics (
    timestamp DateTime,
    hostname String,
    container_id String,
    container_name String,
    metric_name String,
    value Float64,
    db String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, container_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- PostgreSQL Metrics (connections, cache ratio, replication, WAL)
CREATE TABLE IF NOT EXISTS postgres_metrics (
    timestamp DateTime,
    hostname String,
    container_id String,
    container_name String,
    database String,
    metric_name String,
    value Float64,
    extra String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, container_id, database, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- NGINX Metrics (connections, requests, status)
CREATE TABLE IF NOT EXISTS nginx_metrics (
    timestamp DateTime,
    hostname String,
    container_id String,
    container_name String,
    metric_name String,
    value Float64
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, container_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- MongoDB Metrics (opcounters, connections, cache, replication)
CREATE TABLE IF NOT EXISTS mongo_metrics (
    timestamp DateTime,
    hostname String,
    container_id String,
    container_name String,
    metric_name String,
    value Float64
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, container_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- ClickHouse Metrics (queries, memory, merges, parts)
CREATE TABLE IF NOT EXISTS clickhouse_metrics (
    timestamp DateTime,
    hostname String,
    container_id String,
    container_name String,
    metric_name String,
    value Float64
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, container_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- ============================================
-- V3 TABLES: Custom Monitoring
-- ============================================

-- Custom Monitors Configuration
CREATE TABLE IF NOT EXISTS custom_monitors (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    type Enum8('port' = 1, 'http' = 2, 'process' = 3, 'script' = 4, 'metric' = 5),
    config String,  -- JSON configuration
    interval_seconds UInt32 DEFAULT 60,
    enabled Bool DEFAULT true,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (name, id);

-- Custom Monitor Results
CREATE TABLE IF NOT EXISTS custom_monitor_results (
    timestamp DateTime,
    monitor_id UUID,
    monitor_name String,
    hostname String,
    status Enum8('ok' = 1, 'warning' = 2, 'critical' = 3, 'unknown' = 4),
    latency_ms Float32,
    response String,
    error String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (monitor_id, hostname, timestamp)
TTL timestamp + INTERVAL 90 DAY;

-- ============================================
-- V3 TABLES: Alert System
-- ============================================

-- Alert Rules Configuration
CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    condition String,  -- DSL expression
    severity Enum8('info' = 1, 'warning' = 2, 'critical' = 3),
    channels Array(String),
    cooldown_minutes UInt16 DEFAULT 15,
    enabled Bool DEFAULT true,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (name, id);

-- Alert History
CREATE TABLE IF NOT EXISTS alert_history (
    timestamp DateTime,
    rule_id UUID,
    rule_name String,
    hostname String,
    severity Enum8('info' = 1, 'warning' = 2, 'critical' = 3),
    message String,
    channels_notified Array(String),
    acknowledged Bool DEFAULT false,
    acknowledged_by String,
    acknowledged_at Nullable(DateTime),
    resolved Bool DEFAULT false,
    resolved_at Nullable(DateTime)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, timestamp)
TTL timestamp + INTERVAL 180 DAY;

-- ============================================
-- V3 TABLES: Container Topology
-- ============================================

-- Container Inventory
CREATE TABLE IF NOT EXISTS containers (
    container_id String,
    hostname String,
    name String,
    image String,
    status String,
    labels Map(String, String),
    ports Array(UInt16),
    networks Array(String),
    service_type String,  -- detected service: mysql, redis, etc.
    created_at DateTime,
    last_seen DateTime
) ENGINE = ReplacingMergeTree(last_seen)
ORDER BY (hostname, container_id);

-- Container Connections (eBPF-captured)
CREATE TABLE IF NOT EXISTS container_connections (
    timestamp DateTime,
    src_container_id String,
    src_container_name String,
    src_hostname String,
    dst_container_id String,
    dst_container_name String,
    dst_ip String,
    dst_port UInt16,
    protocol Enum8('tcp' = 1, 'udp' = 2, 'icmp' = 3),
    bytes_sent UInt64,
    bytes_recv UInt64,
    packets_sent UInt64,
    packets_recv UInt64,
    requests UInt32,
    avg_latency_ms Float32,
    error_count UInt32
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (src_container_id, dst_container_id, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- Service Dependencies (Aggregated)
CREATE TABLE IF NOT EXISTS service_dependencies (
    updated_at DateTime,
    src_service String,
    src_hostname String,
    dst_service String,
    dst_hostname String,
    connection_type String,
    avg_requests_per_min Float32,
    avg_latency_ms Float32,
    error_rate Float32,
    first_seen DateTime,
    last_seen DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (src_service, dst_service, src_hostname);

-- ============================================
-- V3 TABLES: Security Scanning
-- ============================================

-- Security Port Scans
CREATE TABLE IF NOT EXISTS security_scans (
    timestamp DateTime,
    hostname String,
    scan_type Enum8('port' = 1, 'network' = 2, 'container' = 3, 'file' = 4),
    target String,
    results String,  -- JSON: list of findings
    risk_score UInt8,  -- 0-100
    open_ports Array(UInt16),
    risky_ports Array(UInt16)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, timestamp)
TTL timestamp + INTERVAL 90 DAY;

-- Security Scan Results (vulnerability scans)
CREATE TABLE IF NOT EXISTS security_scan_results (
    id String,
    target String,
    scan_type String,
    status String,
    started_at String,
    completed_at Nullable(String),
    vulnerabilities String,  -- JSON array of vulnerabilities
    score UInt8,
    error String DEFAULT ''
) ENGINE = ReplacingMergeTree()
ORDER BY (id, started_at);

-- Security Events & Alerts
CREATE TABLE IF NOT EXISTS security_events (
    timestamp DateTime,
    hostname String,
    event_type Enum8('port_opened' = 1, 'suspicious_connection' = 2, 'file_changed' = 3, 
                      'process_suspicious' = 4, 'container_privileged' = 5, 'threat_detected' = 6),
    severity Enum8('info' = 1, 'warning' = 2, 'critical' = 3),
    source String,  -- ebpf, scanner, fim
    description String,
    details String,  -- JSON
    resolved Bool DEFAULT false
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, severity, timestamp)
TTL timestamp + INTERVAL 180 DAY;

-- File Integrity Monitoring Baseline
CREATE TABLE IF NOT EXISTS fim_baseline (
    hostname String,
    file_path String,
    file_hash String,
    file_size UInt64,
    file_mode UInt32,
    owner String,
    group String,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (hostname, file_path);

-- ============================================
-- V3 TABLES: AI Learning
-- ============================================

-- AI Learning History
CREATE TABLE IF NOT EXISTS ai_learning (
    timestamp DateTime,
    hostname String,
    pattern_type String,  -- baseline, anomaly, prediction
    pattern_data String,  -- JSON
    confidence Float32,
    verified Bool DEFAULT false,
    feedback String  -- user feedback
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, pattern_type, timestamp)
TTL timestamp + INTERVAL 1 YEAR;

-- AI Predictions
CREATE TABLE IF NOT EXISTS ai_predictions (
    timestamp DateTime,
    hostname String,
    prediction_type String,  -- disk_full, oom, service_crash
    predicted_event String,
    predicted_time DateTime,
    confidence Float32,
    current_value Float64,
    predicted_value Float64,
    recommendation String,
    occurred Bool DEFAULT false,
    occurred_at Nullable(DateTime)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, prediction_type, timestamp)
TTL timestamp + INTERVAL 180 DAY;

-- ============================================
-- V3 TABLES: Auto-Remediation
-- ============================================

-- Remediation Actions History
CREATE TABLE IF NOT EXISTS remediation_history (
    timestamp DateTime,
    hostname String,
    action_type String,
    trigger_reason String,
    status Enum8('pending' = 1, 'approved' = 2, 'executed' = 3, 'failed' = 4, 'rolled_back' = 5),
    approved_by String,
    approved_at Nullable(DateTime),
    executed_at Nullable(DateTime),
    result String,
    rollback_executed Bool DEFAULT false
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, timestamp)
TTL timestamp + INTERVAL 1 YEAR;

-- ============================================
-- V4 TABLES: Built-in Metrics Monitoring
-- (Replaces Prometheus + Grafana)
-- ============================================

-- Metric Scrape Targets (replaces prometheus.yml config)
CREATE TABLE IF NOT EXISTS metric_targets (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    url String,                    -- e.g., http://node:9100/metrics
    scrape_interval UInt32 DEFAULT 15,  -- seconds
    timeout UInt32 DEFAULT 10,          -- seconds
    labels String DEFAULT '{}',         -- JSON: static labels to add
    enabled Bool DEFAULT true,
    last_scrape DateTime DEFAULT now(),
    last_status String DEFAULT 'pending',
    last_error String DEFAULT '',
    metrics_count UInt32 DEFAULT 0,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (name, id);

-- Scraped Metrics (replaces Prometheus TSDB)
CREATE TABLE IF NOT EXISTS scraped_metrics (
    timestamp DateTime,
    target_id UUID,
    target_name String,
    metric_name String,
    labels String,            -- JSON: {"instance":"host:9100","job":"node"}
    value Float64
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (target_id, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- ============================================
-- V5 TABLES: Custom Dashboards & Metric Alerts
-- ============================================

-- Custom Dashboards
CREATE TABLE IF NOT EXISTS dashboards (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    description String DEFAULT '',
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- Dashboard Panels (charts)
CREATE TABLE IF NOT EXISTS dashboard_panels (
    id UUID DEFAULT generateUUIDv4(),
    dashboard_id UUID,
    title String,
    target_id UUID,          -- metric_targets.id
    metric_name String,
    chart_type String DEFAULT 'area',  -- 'area', 'line', 'bar'
    color String DEFAULT '#00F3FF',
    position Int32 DEFAULT 0,
    time_range String DEFAULT '1h',  -- '1h', '6h', '24h', '7d'
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (dashboard_id, position);

-- Metric Alert Rules (for scraped Prometheus metrics)
CREATE TABLE IF NOT EXISTS metric_alert_rules (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    target_id UUID,          -- metric_targets.id
    metric_name String,
    condition String,        -- 'gt', 'lt', 'eq', 'gte', 'lte'
    threshold Float64,
    duration_seconds Int32 DEFAULT 60,  -- How long condition must be true
    notification_channel String DEFAULT 'webhook',
    notification_config String DEFAULT '{}',  -- JSON: {url, headers, etc}
    enabled UInt8 DEFAULT 1,
    last_triggered DateTime,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- Metric Alert History
CREATE TABLE IF NOT EXISTS metric_alert_history (
    id UUID DEFAULT generateUUIDv4(),
    rule_id UUID,
    rule_name String,
    triggered_at DateTime DEFAULT now(),
    value Float64,
    threshold Float64,
    status String DEFAULT 'firing',  -- 'firing', 'resolved'
    notified UInt8 DEFAULT 0,
    notification_sent_at Nullable(DateTime)
) ENGINE = MergeTree()
ORDER BY (rule_id, triggered_at)
TTL triggered_at + INTERVAL 30 DAY;
