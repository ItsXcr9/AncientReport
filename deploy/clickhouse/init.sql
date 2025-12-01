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
    created_at DateTime
) ENGINE = MergeTree()
ORDER BY (timestamp, container_id)
TTL timestamp + INTERVAL 30 DAY;
