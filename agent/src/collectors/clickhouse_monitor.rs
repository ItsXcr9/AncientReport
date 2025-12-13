//! ClickHouse Container Monitor
//! Collects metrics from ClickHouse containers using system tables

use std::process::Command;
use std::collections::HashMap;
use tracing::{info, warn, error, debug};

pub struct ClickHouseMonitor {
    hostname: String,
    clickhouse_url: String,
}

#[derive(Debug, Clone, Default)]
pub struct ClickHouseMetrics {
    pub container_id: String,
    pub container_name: String,
    // Queries
    pub query_count: i64,
    pub running_queries: i64,
    pub queries_memory: i64,
    // Memory
    pub memory_tracking: i64,
    pub memory_resident: i64,
    // Merges
    pub merge_count: i64,
    pub merge_memory: i64,
    pub parts_active: i64,
    pub parts_outdated: i64,
    // Connections
    pub tcp_connections: i64,
    pub http_connections: i64,
    // IO
    pub read_bytes: i64,
    pub written_bytes: i64,
    // Replicas
    pub replicas_max_queue_size: i64,
    pub replicas_sum_queue_size: i64,
    // Errors
    pub rejected_inserts: i64,
    pub delayed_inserts: i64,
}

impl ClickHouseMonitor {
    pub fn new(hostname: String, clickhouse_url: String) -> Self {
        Self { hostname, clickhouse_url }
    }

    /// Detect ClickHouse containers
    fn detect_clickhouse_containers(&self) -> Vec<(String, String)> {
        let output = Command::new("docker")
            .args(["ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}"])
            .output();

        match output {
            Ok(out) => {
                let stdout = String::from_utf8_lossy(&out.stdout);
                stdout
                    .lines()
                    .filter_map(|line| {
                        let parts: Vec<&str> = line.split('|').collect();
                        if parts.len() >= 3 {
                            let image = parts[2].to_lowercase();
                            if image.contains("clickhouse") {
                                return Some((parts[0].to_string(), parts[1].to_string()));
                            }
                        }
                        None
                    })
                    .collect()
            }
            Err(e) => {
                warn!("Failed to detect ClickHouse containers: {}", e);
                vec![]
            }
        }
    }

    /// Run clickhouse-client query inside container
    fn run_query(&self, container_id: &str, query: &str) -> Option<String> {
        let output = Command::new("docker")
            .args([
                "exec", container_id, "clickhouse-client", "--query", query
            ])
            .output();

        match output {
            Ok(out) if out.status.success() => {
                Some(String::from_utf8_lossy(&out.stdout).to_string())
            }
            _ => None
        }
    }

    /// Get metrics from system.metrics table
    fn get_system_metrics(&self, container_id: &str) -> HashMap<String, i64> {
        let mut metrics = HashMap::new();

        let output = self.run_query(container_id, 
            "SELECT metric, value FROM system.metrics FORMAT TSV");

        if let Some(data) = output {
            for line in data.lines() {
                let parts: Vec<&str> = line.split('\t').collect();
                if parts.len() >= 2 {
                    if let Ok(value) = parts[1].parse::<i64>() {
                        metrics.insert(parts[0].to_string(), value);
                    }
                }
            }
        }

        metrics
    }

    /// Get metrics from system.async_metrics table
    fn get_async_metrics(&self, container_id: &str) -> HashMap<String, f64> {
        let mut metrics = HashMap::new();

        let output = self.run_query(container_id, 
            "SELECT metric, value FROM system.asynchronous_metrics FORMAT TSV");

        if let Some(data) = output {
            for line in data.lines() {
                let parts: Vec<&str> = line.split('\t').collect();
                if parts.len() >= 2 {
                    if let Ok(value) = parts[1].parse::<f64>() {
                        metrics.insert(parts[0].to_string(), value);
                    }
                }
            }
        }

        metrics
    }

    /// Get parts count
    fn get_parts_count(&self, container_id: &str) -> (i64, i64) {
        let output = self.run_query(container_id, 
            "SELECT \
             countIf(active) as active, \
             countIf(NOT active) as outdated \
             FROM system.parts FORMAT TSV");

        if let Some(data) = output {
            let parts: Vec<&str> = data.trim().split('\t').collect();
            if parts.len() >= 2 {
                let active = parts[0].parse::<i64>().unwrap_or(0);
                let outdated = parts[1].parse::<i64>().unwrap_or(0);
                return (active, outdated);
            }
        }

        (0, 0)
    }

    /// Collect metrics from container
    fn collect_container_metrics(&self, container_id: &str, container_name: &str) -> Result<ClickHouseMetrics, Box<dyn std::error::Error + Send + Sync>> {
        let sys_metrics = self.get_system_metrics(container_id);
        let async_metrics = self.get_async_metrics(container_id);
        let (parts_active, parts_outdated) = self.get_parts_count(container_id);

        let mut metrics = ClickHouseMetrics {
            container_id: container_id.to_string(),
            container_name: container_name.to_string(),
            // From system.metrics
            query_count: *sys_metrics.get("Query").unwrap_or(&0),
            running_queries: *sys_metrics.get("Query").unwrap_or(&0),
            queries_memory: *sys_metrics.get("MemoryTrackingForMerges").unwrap_or(&0),
            memory_tracking: *sys_metrics.get("MemoryTracking").unwrap_or(&0),
            merge_count: *sys_metrics.get("Merge").unwrap_or(&0),
            merge_memory: *sys_metrics.get("MemoryTrackingForMerges").unwrap_or(&0),
            tcp_connections: *sys_metrics.get("TCPConnection").unwrap_or(&0),
            http_connections: *sys_metrics.get("HTTPConnection").unwrap_or(&0),
            read_bytes: *sys_metrics.get("NetworkReceiveBytes").unwrap_or(&0),
            written_bytes: *sys_metrics.get("NetworkSendBytes").unwrap_or(&0),
            replicas_max_queue_size: *sys_metrics.get("ReplicasMaxQueueSize").unwrap_or(&0),
            replicas_sum_queue_size: *sys_metrics.get("ReplicasSumQueueSize").unwrap_or(&0),
            rejected_inserts: *sys_metrics.get("RejectedInserts").unwrap_or(&0),
            delayed_inserts: *sys_metrics.get("DelayedInserts").unwrap_or(&0),
            // From async metrics
            memory_resident: async_metrics.get("OSMemoryTotal").map(|v| *v as i64).unwrap_or(0),
            // Parts
            parts_active,
            parts_outdated,
        };

        Ok(metrics)
    }

    /// Send metrics to ClickHouse (self-monitoring to same or different instance)
    async fn send_to_clickhouse(&self, metrics: &ClickHouseMetrics) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = reqwest::Client::new();
        
        let query = format!(
            "INSERT INTO AncientReport.clickhouse_metrics (timestamp, hostname, container_id, container_name, metric_name, value) VALUES \
             (now(), '{}', '{}', '{}', 'running_queries', {}), \
             (now(), '{}', '{}', '{}', 'memory_tracking', {}), \
             (now(), '{}', '{}', '{}', 'merge_count', {}), \
             (now(), '{}', '{}', '{}', 'tcp_connections', {}), \
             (now(), '{}', '{}', '{}', 'http_connections', {}), \
             (now(), '{}', '{}', '{}', 'parts_active', {}), \
             (now(), '{}', '{}', '{}', 'parts_outdated', {}), \
             (now(), '{}', '{}', '{}', 'read_bytes', {}), \
             (now(), '{}', '{}', '{}', 'written_bytes', {}), \
             (now(), '{}', '{}', '{}', 'replicas_queue_size', {}), \
             (now(), '{}', '{}', '{}', 'rejected_inserts', {}), \
             (now(), '{}', '{}', '{}', 'delayed_inserts', {})",
            self.hostname, metrics.container_id, metrics.container_name, metrics.running_queries,
            self.hostname, metrics.container_id, metrics.container_name, metrics.memory_tracking,
            self.hostname, metrics.container_id, metrics.container_name, metrics.merge_count,
            self.hostname, metrics.container_id, metrics.container_name, metrics.tcp_connections,
            self.hostname, metrics.container_id, metrics.container_name, metrics.http_connections,
            self.hostname, metrics.container_id, metrics.container_name, metrics.parts_active,
            self.hostname, metrics.container_id, metrics.container_name, metrics.parts_outdated,
            self.hostname, metrics.container_id, metrics.container_name, metrics.read_bytes,
            self.hostname, metrics.container_id, metrics.container_name, metrics.written_bytes,
            self.hostname, metrics.container_id, metrics.container_name, metrics.replicas_sum_queue_size,
            self.hostname, metrics.container_id, metrics.container_name, metrics.rejected_inserts,
            self.hostname, metrics.container_id, metrics.container_name, metrics.delayed_inserts
        );

        let response = client
            .post(&self.clickhouse_url)
            .body(query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            error!("ClickHouse insert failed: {}", error_text);
        }

        Ok(())
    }

    /// Main collection loop
    pub async fn collect_and_send(&self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let containers = self.detect_clickhouse_containers();
        
        if containers.is_empty() {
            debug!("No ClickHouse containers found");
            return Ok(());
        }

        info!("Found {} ClickHouse container(s)", containers.len());

        for (container_id, container_name) in containers {
            match self.collect_container_metrics(&container_id, &container_name) {
                Ok(metrics) => {
                    if let Err(e) = self.send_to_clickhouse(&metrics).await {
                        error!("Failed to send ClickHouse metrics: {}", e);
                    } else {
                        info!("Sent ClickHouse metrics for container: {}", container_name);
                    }
                }
                Err(e) => {
                    debug!("Could not collect ClickHouse metrics from {}: {}", container_name, e);
                }
            }
        }

        Ok(())
    }
}
