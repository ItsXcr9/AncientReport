-- =============================================
-- Migration: Add materialized views for pre-aggregated dashboard data
-- Purpose: Speed up dashboard queries by pre-computing hourly aggregations
-- =============================================

-- 1. Create destination table for hourly aggregations
CREATE TABLE IF NOT EXISTS metrics_hourly_agg (
    hour DateTime,
    hostname LowCardinality(String),
    metric_name LowCardinality(String),
    min_value Float64,
    max_value Float64,
    avg_value Float64,
    sum_value Float64,
    count UInt64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (hostname, metric_name, hour)
TTL hour + INTERVAL 90 DAY;

-- 2. Create materialized view to auto-populate from metrics table
-- New data inserted into metrics will automatically be aggregated
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_hourly_mv
TO metrics_hourly_agg
AS SELECT
    toStartOfHour(timestamp) as hour,
    hostname,
    metric_name,
    min(value) as min_value,
    max(value) as max_value,
    avg(value) as avg_value,
    sum(value) as sum_value,
    count() as count
FROM metrics
GROUP BY hour, hostname, metric_name;

-- 3. Create 5-minute aggregation table for more granular dashboards
CREATE TABLE IF NOT EXISTS metrics_5min_agg (
    ts DateTime,
    hostname LowCardinality(String),
    metric_name LowCardinality(String),
    min_value Float64,
    max_value Float64,
    avg_value Float64,
    count UInt64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMMDD(ts)
ORDER BY (hostname, metric_name, ts)
TTL ts + INTERVAL 7 DAY;

-- 4. Materialized view for 5-minute aggregations
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_5min_mv
TO metrics_5min_agg
AS SELECT
    toStartOfFiveMinutes(timestamp) as ts,
    hostname,
    metric_name,
    min(value) as min_value,
    max(value) as max_value,
    avg(value) as avg_value,
    count() as count
FROM metrics
GROUP BY ts, hostname, metric_name;

-- 5. View for quick server health overview
CREATE VIEW IF NOT EXISTS server_health_latest AS
SELECT 
    hostname,
    maxIf(value, metric_name = 'cpu_usage_percent') as cpu_percent,
    maxIf(value, metric_name = 'memory_usage_percent') as memory_percent,
    maxIf(value, metric_name = 'disk_usage_percent') as disk_percent,
    maxIf(value, metric_name = 'network_active_connections') as active_connections,
    max(timestamp) as last_seen
FROM metrics
WHERE timestamp >= now() - INTERVAL 5 MINUTE
GROUP BY hostname;
