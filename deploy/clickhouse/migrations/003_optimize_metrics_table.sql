-- =============================================
-- Migration: Add indexes and projections for metrics table
-- Purpose: Optimize query performance for time-range and hostname filtering
-- =============================================

-- 1. Add bloom filter index for metric_name filtering
-- This dramatically speeds up queries like: WHERE metric_name = 'cpu_usage_percent'
ALTER TABLE metrics ADD INDEX IF NOT EXISTS idx_metric_name metric_name TYPE bloom_filter GRANULARITY 1;

-- 2. Add bloom filter index for hostname filtering  
-- This speeds up queries like: WHERE hostname = 'xcr9'
ALTER TABLE metrics ADD INDEX IF NOT EXISTS idx_hostname hostname TYPE bloom_filter GRANULARITY 1;

-- 3. Add projection for time-first ordering
-- Current ORDER BY (hostname, metric_type, timestamp) is suboptimal for time-range queries
-- This projection provides an alternative sort order without recreating the table
ALTER TABLE metrics ADD PROJECTION IF NOT EXISTS metrics_by_time (
    SELECT 
        timestamp,
        hostname,
        metric_type,
        metric_name,
        value,
        tags
    ORDER BY (timestamp, hostname, metric_name)
);

-- 4. Materialize the projection for existing data
-- Note: This may take time depending on data volume
ALTER TABLE metrics MATERIALIZE PROJECTION metrics_by_time;

-- 5. Add projection for hostname-first queries (dashboard overview)
ALTER TABLE metrics ADD PROJECTION IF NOT EXISTS metrics_by_host (
    SELECT 
        timestamp,
        hostname,
        metric_name,
        value
    ORDER BY (hostname, timestamp, metric_name)
);

ALTER TABLE metrics MATERIALIZE PROJECTION metrics_by_host;
