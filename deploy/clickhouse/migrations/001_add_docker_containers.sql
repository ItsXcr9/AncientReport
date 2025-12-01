
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
