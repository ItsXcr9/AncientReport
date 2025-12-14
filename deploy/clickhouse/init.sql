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

-- ============================================
-- V6 TABLES: Recording Rules (Pre-aggregation)
-- ============================================

-- Recording Rules Configuration
-- Similar to Prometheus recording rules - pre-aggregate expensive queries
CREATE TABLE IF NOT EXISTS recording_rules (
    id UUID DEFAULT generateUUIDv4(),
    name String,                      -- Unique name for the recorded metric
    target_id UUID,                   -- Source metric_targets.id
    source_metric String,             -- Original metric name to aggregate
    labels_filter String DEFAULT '{}', -- JSON label filters e.g. {"topic": "orders"}
    aggregation String DEFAULT 'avg', -- sum, avg, max, min
    group_by String DEFAULT '',       -- Comma-separated label keys to group by
    interval_seconds Int32 DEFAULT 60,-- Evaluation interval
    enabled UInt8 DEFAULT 1,
    description String DEFAULT '',
    last_evaluated DateTime,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- Recorded Metrics (pre-aggregated time series)
CREATE TABLE IF NOT EXISTS recorded_metrics (
    timestamp DateTime,
    rule_id UUID,
    rule_name String,
    group_labels String DEFAULT '{}', -- JSON of group-by label values
    value Float64
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (rule_id, timestamp, group_labels)
TTL timestamp + INTERVAL 90 DAY;

-- ============================================
-- V7 TABLES: SNMP Monitoring
-- ============================================

-- SNMP Devices (routers, switches, servers, printers, UPS, etc.)
CREATE TABLE IF NOT EXISTS snmp_devices (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    ip_address String,
    snmp_version String DEFAULT 'v2c',  -- 'v1', 'v2c', 'v3'
    community String DEFAULT 'public',  -- for v1/v2c
    -- SNMPv3 credentials
    username String DEFAULT '',
    auth_protocol String DEFAULT '',    -- MD5, SHA, SHA256
    auth_password String DEFAULT '',
    priv_protocol String DEFAULT '',    -- DES, AES, AES256
    priv_password String DEFAULT '',
    port UInt16 DEFAULT 161,
    device_type String DEFAULT 'unknown',   -- router, switch, server, printer, ups, firewall
    vendor String DEFAULT '',               -- cisco, juniper, hp, dell, apc
    model String DEFAULT '',
    sys_descr String DEFAULT '',
    sys_object_id String DEFAULT '',
    sys_name String DEFAULT '',
    sys_location String DEFAULT '',
    sys_contact String DEFAULT '',
    sys_uptime UInt64 DEFAULT 0,
    template_id Nullable(UUID),
    enabled UInt8 DEFAULT 1,
    poll_interval UInt32 DEFAULT 60,
    timeout_ms UInt32 DEFAULT 5000,
    retries UInt8 DEFAULT 3,
    last_poll Nullable(DateTime),
    last_success Nullable(DateTime),
    status String DEFAULT 'unknown',        -- up, down, degraded, unknown
    error_message String DEFAULT '',
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- SNMP OID Definitions (what to poll per device)
CREATE TABLE IF NOT EXISTS snmp_oids (
    id UUID DEFAULT generateUUIDv4(),
    device_id UUID,
    oid String,
    name String,
    description String DEFAULT '',
    mib_name String DEFAULT '',
    data_type String DEFAULT 'gauge',   -- gauge, counter, counter64, string, timeticks, integer
    unit String DEFAULT '',             -- %, bytes, bps, packets, etc.
    multiplier Float64 DEFAULT 1.0,     -- scale factor for value
    is_delta UInt8 DEFAULT 0,           -- calculate rate of change
    enabled UInt8 DEFAULT 1,
    poll_interval UInt32 DEFAULT 60,
    last_value Float64 DEFAULT 0,
    last_poll Nullable(DateTime),
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (id, device_id);

-- SNMP Device Templates (pre-configured OID sets for common devices)
CREATE TABLE IF NOT EXISTS snmp_templates (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    vendor String,
    device_type String,
    sys_object_id_pattern String DEFAULT '',  -- regex to match sysObjectID
    description String DEFAULT '',
    oids String DEFAULT '[]',           -- JSON array of OID definitions
    icon String DEFAULT 'server',       -- lucide icon name
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- SNMP Polled Metrics (time-series data from polling)
CREATE TABLE IF NOT EXISTS snmp_metrics (
    timestamp DateTime,
    device_id UUID,
    device_name String,
    oid String,
    oid_name String,
    value Float64,
    value_string String DEFAULT '',
    data_type String DEFAULT 'gauge',
    unit String DEFAULT ''
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (device_id, oid, timestamp)
TTL timestamp + INTERVAL 90 DAY;

-- SNMP Traps (unsolicited notifications from devices)
CREATE TABLE IF NOT EXISTS snmp_traps (
    id UUID DEFAULT generateUUIDv4(),
    timestamp DateTime DEFAULT now(),
    source_ip String,
    device_id Nullable(UUID),
    device_name String DEFAULT '',
    trap_oid String,
    trap_name String DEFAULT '',
    trap_type String DEFAULT '',        -- linkDown, linkUp, coldStart, etc.
    enterprise_oid String DEFAULT '',
    generic_trap Int32 DEFAULT 0,
    specific_trap Int32 DEFAULT 0,
    severity String DEFAULT 'info',     -- critical, major, minor, warning, info
    message String DEFAULT '',
    varbinds String DEFAULT '{}',       -- JSON of variable bindings
    acknowledged UInt8 DEFAULT 0,
    acknowledged_by String DEFAULT '',
    acknowledged_at Nullable(DateTime),
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, source_ip)
TTL timestamp + INTERVAL 180 DAY;

-- SNMP Interface Table (cached interface info for network devices)
CREATE TABLE IF NOT EXISTS snmp_interfaces (
    device_id UUID,
    if_index UInt32,
    if_descr String,
    if_type UInt32,
    if_mtu UInt32 DEFAULT 0,
    if_speed UInt64 DEFAULT 0,
    if_phys_address String DEFAULT '',
    if_admin_status UInt8 DEFAULT 1,
    if_oper_status UInt8 DEFAULT 1,
    if_alias String DEFAULT '',
    last_updated DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(last_updated)
ORDER BY (device_id, if_index);

-- ============================================
-- Advanced Analytics Tables
-- ============================================

-- Detected Anomalies (ML/Statistical)
CREATE TABLE IF NOT EXISTS anomalies (
    id UUID DEFAULT generateUUIDv4(),
    timestamp DateTime DEFAULT now(),
    hostname String,
    metric_name String,
    current_value Float64,
    expected_value Float64,
    lower_bound Float64 DEFAULT 0,
    upper_bound Float64 DEFAULT 0,
    deviation_score Float64,
    severity String DEFAULT 'warning',  -- info, warning, critical
    detection_method String DEFAULT 'zscore',  -- zscore, iqr, forecast
    is_acknowledged UInt8 DEFAULT 0,
    acknowledged_by String DEFAULT '',
    acknowledged_at Nullable(DateTime),
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (hostname, metric_name, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- SLO Definitions
CREATE TABLE IF NOT EXISTS slo_definitions (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    service String,
    description String DEFAULT '',
    sli_type String DEFAULT 'availability',  -- availability, latency, throughput, custom
    sli_metric String DEFAULT '',            -- metric name to track
    sli_good_query String DEFAULT '',        -- query for good events
    sli_total_query String DEFAULT '',       -- query for total events
    target Float64,                          -- e.g., 0.999 for 99.9%
    window_days UInt32 DEFAULT 30,
    burn_rate_threshold Float64 DEFAULT 10.0,  -- alert if burn rate exceeds
    enabled UInt8 DEFAULT 1,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- SLO Status History
CREATE TABLE IF NOT EXISTS slo_status (
    id UUID DEFAULT generateUUIDv4(),
    slo_id UUID,
    timestamp DateTime DEFAULT now(),
    current_sli Float64,                  -- 0.0 to 1.0
    target Float64,
    error_budget_total Float64,           -- total allowed errors
    error_budget_remaining Float64,       -- remaining errors allowed
    error_budget_consumed_pct Float64,    -- percentage used
    burn_rate Float64,                    -- errors/hour rate
    burn_rate_1h Float64 DEFAULT 0,
    burn_rate_6h Float64 DEFAULT 0,
    is_breached UInt8 DEFAULT 0,
    events_total UInt64 DEFAULT 0,
    events_good UInt64 DEFAULT 0,
    events_bad UInt64 DEFAULT 0
) ENGINE = MergeTree()
ORDER BY (slo_id, timestamp)
TTL timestamp + INTERVAL 90 DAY;

-- Synthetic Monitors Configuration
CREATE TABLE IF NOT EXISTS synthetic_monitors (
    id UUID DEFAULT generateUUIDv4(),
    name String,
    description String DEFAULT '',
    url String,
    method String DEFAULT 'GET',
    headers String DEFAULT '{}',           -- JSON
    body String DEFAULT '',
    expected_status UInt16 DEFAULT 200,
    expected_body_contains String DEFAULT '',
    timeout_ms UInt32 DEFAULT 10000,
    interval_seconds UInt32 DEFAULT 60,
    locations String DEFAULT '["local"]',  -- JSON array of check locations
    enabled UInt8 DEFAULT 1,
    last_check DateTime DEFAULT toDateTime('1970-01-01 00:00:00'),
    last_status String DEFAULT 'unknown',  -- success, failure, timeout
    last_latency_ms Float64 DEFAULT 0,
    consecutive_failures UInt32 DEFAULT 0,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- Synthetic Check Results
CREATE TABLE IF NOT EXISTS synthetic_results (
    id UUID DEFAULT generateUUIDv4(),
    monitor_id UUID,
    monitor_name String DEFAULT '',
    timestamp DateTime DEFAULT now(),
    success UInt8,
    status_code UInt16 DEFAULT 0,
    latency_ms Float64,
    dns_time_ms Float64 DEFAULT 0,
    connect_time_ms Float64 DEFAULT 0,
    tls_time_ms Float64 DEFAULT 0,
    ttfb_ms Float64 DEFAULT 0,            -- time to first byte
    error_message String DEFAULT '',
    response_size UInt64 DEFAULT 0,
    location String DEFAULT 'local'
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (monitor_id, timestamp)
TTL timestamp + INTERVAL 30 DAY;

-- Alert Incidents (correlated alerts grouped together)
CREATE TABLE IF NOT EXISTS alert_incidents (
    id UUID DEFAULT generateUUIDv4(),
    title String,
    description String DEFAULT '',
    status String DEFAULT 'open',          -- open, acknowledged, resolved
    severity String DEFAULT 'warning',     -- info, warning, critical
    root_cause String DEFAULT '',
    affected_hosts String DEFAULT '[]',    -- JSON array
    affected_services String DEFAULT '[]', -- JSON array
    alert_ids String DEFAULT '[]',         -- JSON array of alert history IDs
    alert_count UInt32 DEFAULT 1,
    first_alert_at DateTime,
    last_alert_at DateTime,
    acknowledged_by String DEFAULT '',
    acknowledged_at Nullable(DateTime),
    resolved_by String DEFAULT '',
    resolved_at Nullable(DateTime),
    resolution_notes String DEFAULT '',
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;

-- Incident-Alert Mapping (for tracking which alerts belong to which incident)
CREATE TABLE IF NOT EXISTS incident_alerts (
    incident_id UUID,
    alert_history_id UUID,
    hostname String DEFAULT '',
    metric_name String DEFAULT '',
    added_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (incident_id, added_at);
