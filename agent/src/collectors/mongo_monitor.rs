//! MongoDB Container Monitor
//! Collects metrics from MongoDB containers using mongosh

use std::process::Command;
use tracing::{info, warn, error, debug};
use serde_json::Value;

pub struct MongoMonitor {
    hostname: String,
    clickhouse_url: String,
}

#[derive(Debug, Clone, Default)]
pub struct MongoMetrics {
    pub container_id: String,
    pub container_name: String,
    // Opcounters
    pub opcounters_insert: i64,
    pub opcounters_query: i64,
    pub opcounters_update: i64,
    pub opcounters_delete: i64,
    pub opcounters_command: i64,
    // Connections
    pub connections_current: i64,
    pub connections_available: i64,
    pub connections_total_created: i64,
    // Memory
    pub mem_resident_mb: i64,
    pub mem_virtual_mb: i64,
    // WiredTiger cache
    pub cache_bytes_in_cache: i64,
    pub cache_bytes_max: i64,
    pub cache_evictions: i64,
    pub cache_dirty_bytes: i64,
    // Replication
    pub repl_lag_seconds: f64,
    pub is_primary: bool,
    // Locks
    pub global_lock_current_queue_total: i64,
    pub global_lock_active_clients_total: i64,
}

impl MongoMonitor {
    pub fn new(hostname: String, clickhouse_url: String) -> Self {
        Self { hostname, clickhouse_url }
    }

    /// Detect MongoDB containers
    fn detect_mongo_containers(&self) -> Vec<(String, String)> {
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
                            if image.contains("mongo") && !image.contains("mongosh") {
                                return Some((parts[0].to_string(), parts[1].to_string()));
                            }
                        }
                        None
                    })
                    .collect()
            }
            Err(e) => {
                warn!("Failed to detect MongoDB containers: {}", e);
                vec![]
            }
        }
    }

    /// Get serverStatus from MongoDB
    fn get_server_status(&self, container_id: &str) -> Option<Value> {
        // Try mongosh first (MongoDB 5.0+)
        let output = Command::new("docker")
            .args([
                "exec", container_id, "mongosh", "--quiet", "--eval",
                "JSON.stringify(db.serverStatus())"
            ])
            .output();

        if let Ok(out) = output {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout);
                if let Ok(json) = serde_json::from_str::<Value>(&stdout) {
                    return Some(json);
                }
            }
        }

        // Fallback to mongo shell (older versions)
        let output = Command::new("docker")
            .args([
                "exec", container_id, "mongo", "--quiet", "--eval",
                "JSON.stringify(db.serverStatus())"
            ])
            .output();

        if let Ok(out) = output {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout);
                if let Ok(json) = serde_json::from_str::<Value>(&stdout) {
                    return Some(json);
                }
            }
        }

        None
    }

    /// Parse serverStatus JSON
    fn parse_server_status(&self, status: &Value) -> MongoMetrics {
        let mut metrics = MongoMetrics::default();

        // Opcounters
        if let Some(opcounters) = status.get("opcounters") {
            metrics.opcounters_insert = opcounters.get("insert").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.opcounters_query = opcounters.get("query").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.opcounters_update = opcounters.get("update").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.opcounters_delete = opcounters.get("delete").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.opcounters_command = opcounters.get("command").and_then(|v| v.as_i64()).unwrap_or(0);
        }

        // Connections
        if let Some(connections) = status.get("connections") {
            metrics.connections_current = connections.get("current").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.connections_available = connections.get("available").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.connections_total_created = connections.get("totalCreated").and_then(|v| v.as_i64()).unwrap_or(0);
        }

        // Memory
        if let Some(mem) = status.get("mem") {
            metrics.mem_resident_mb = mem.get("resident").and_then(|v| v.as_i64()).unwrap_or(0);
            metrics.mem_virtual_mb = mem.get("virtual").and_then(|v| v.as_i64()).unwrap_or(0);
        }

        // WiredTiger cache
        if let Some(wt) = status.get("wiredTiger") {
            if let Some(cache) = wt.get("cache") {
                metrics.cache_bytes_in_cache = cache.get("bytes currently in the cache")
                    .and_then(|v| v.as_i64()).unwrap_or(0);
                metrics.cache_bytes_max = cache.get("maximum bytes configured")
                    .and_then(|v| v.as_i64()).unwrap_or(0);
                metrics.cache_evictions = cache.get("pages evicted by application threads")
                    .and_then(|v| v.as_i64()).unwrap_or(0);
                metrics.cache_dirty_bytes = cache.get("tracked dirty bytes in the cache")
                    .and_then(|v| v.as_i64()).unwrap_or(0);
            }
        }

        // Global lock
        if let Some(global_lock) = status.get("globalLock") {
            if let Some(current_queue) = global_lock.get("currentQueue") {
                metrics.global_lock_current_queue_total = current_queue.get("total")
                    .and_then(|v| v.as_i64()).unwrap_or(0);
            }
            if let Some(active_clients) = global_lock.get("activeClients") {
                metrics.global_lock_active_clients_total = active_clients.get("total")
                    .and_then(|v| v.as_i64()).unwrap_or(0);
            }
        }

        // Replication status
        if let Some(repl) = status.get("repl") {
            metrics.is_primary = repl.get("ismaster").and_then(|v| v.as_bool()).unwrap_or(false)
                || repl.get("isWritablePrimary").and_then(|v| v.as_bool()).unwrap_or(false);
        }

        metrics
    }

    /// Collect metrics from a container
    fn collect_container_metrics(&self, container_id: &str, container_name: &str) -> Result<MongoMetrics, Box<dyn std::error::Error + Send + Sync>> {
        let status = self.get_server_status(container_id)
            .ok_or("Could not get serverStatus")?;

        let mut metrics = self.parse_server_status(&status);
        metrics.container_id = container_id.to_string();
        metrics.container_name = container_name.to_string();

        Ok(metrics)
    }

    /// Send metrics to ClickHouse
    async fn send_to_clickhouse(&self, metrics: &MongoMetrics) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = reqwest::Client::new();
        
        let query = format!(
            "INSERT INTO AncientReport.mongo_metrics (timestamp, hostname, container_id, container_name, metric_name, value) VALUES \
             (now(), '{}', '{}', '{}', 'opcounters_insert', {}), \
             (now(), '{}', '{}', '{}', 'opcounters_query', {}), \
             (now(), '{}', '{}', '{}', 'opcounters_update', {}), \
             (now(), '{}', '{}', '{}', 'opcounters_delete', {}), \
             (now(), '{}', '{}', '{}', 'connections_current', {}), \
             (now(), '{}', '{}', '{}', 'connections_available', {}), \
             (now(), '{}', '{}', '{}', 'mem_resident_mb', {}), \
             (now(), '{}', '{}', '{}', 'cache_bytes_in_cache', {}), \
             (now(), '{}', '{}', '{}', 'cache_bytes_max', {}), \
             (now(), '{}', '{}', '{}', 'cache_evictions', {}), \
             (now(), '{}', '{}', '{}', 'global_lock_queue', {}), \
             (now(), '{}', '{}', '{}', 'is_primary', {})",
            self.hostname, metrics.container_id, metrics.container_name, metrics.opcounters_insert,
            self.hostname, metrics.container_id, metrics.container_name, metrics.opcounters_query,
            self.hostname, metrics.container_id, metrics.container_name, metrics.opcounters_update,
            self.hostname, metrics.container_id, metrics.container_name, metrics.opcounters_delete,
            self.hostname, metrics.container_id, metrics.container_name, metrics.connections_current,
            self.hostname, metrics.container_id, metrics.container_name, metrics.connections_available,
            self.hostname, metrics.container_id, metrics.container_name, metrics.mem_resident_mb,
            self.hostname, metrics.container_id, metrics.container_name, metrics.cache_bytes_in_cache,
            self.hostname, metrics.container_id, metrics.container_name, metrics.cache_bytes_max,
            self.hostname, metrics.container_id, metrics.container_name, metrics.cache_evictions,
            self.hostname, metrics.container_id, metrics.container_name, metrics.global_lock_current_queue_total,
            self.hostname, metrics.container_id, metrics.container_name, if metrics.is_primary { 1 } else { 0 }
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
        let containers = self.detect_mongo_containers();
        
        if containers.is_empty() {
            debug!("No MongoDB containers found");
            return Ok(());
        }

        info!("Found {} MongoDB container(s)", containers.len());

        for (container_id, container_name) in containers {
            match self.collect_container_metrics(&container_id, &container_name) {
                Ok(metrics) => {
                    if let Err(e) = self.send_to_clickhouse(&metrics).await {
                        error!("Failed to send MongoDB metrics: {}", e);
                    } else {
                        info!("Sent MongoDB metrics for container: {}", container_name);
                    }
                }
                Err(e) => {
                    debug!("Could not collect MongoDB metrics from {}: {}", container_name, e);
                }
            }
        }

        Ok(())
    }
}
