// Redis Container Monitor for AncientReport V3
// Collects deep Redis metrics via docker exec redis-cli

use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::process::Command;
use tracing::{debug, error, info, warn};

/// Redis metrics collected from a container
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RedisMetrics {
    pub timestamp: i64,
    pub hostname: String,
    pub container_id: String,
    pub container_name: String,
    pub metrics: HashMap<String, f64>,
    pub keyspace: HashMap<String, KeyspaceInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyspaceInfo {
    pub keys: i64,
    pub expires: i64,
    pub avg_ttl: i64,
}

pub struct RedisMonitor {
    hostname: String,
    clickhouse_url: String,
    docker_path: String,
}

impl RedisMonitor {
    pub fn new(hostname: String, clickhouse_url: String) -> Self {
        let docker_path = Self::find_docker_binary();
        info!("Redis monitor initialized with hostname: {}", hostname);
        Self {
            hostname,
            clickhouse_url,
            docker_path,
        }
    }

    fn find_docker_binary() -> String {
        let paths = vec!["/usr/bin/docker", "/usr/local/bin/docker", "docker"];
        for path in paths {
            if let Ok(output) = Command::new(path).arg("--version").output() {
                if output.status.success() {
                    return path.to_string();
                }
            }
        }
        "/usr/bin/docker".to_string()
    }

    /// Detect Redis containers running on this host
    pub fn detect_redis_containers(&self) -> Vec<(String, String)> {
        let output = Command::new(&self.docker_path)
            .args(&["ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}"])
            .output();

        let output = match output {
            Ok(o) if o.status.success() => o,
            _ => return Vec::new(),
        };

        let stdout = String::from_utf8_lossy(&output.stdout);
        let mut redis_containers = Vec::new();

        for line in stdout.lines() {
            let parts: Vec<&str> = line.split('|').collect();
            if parts.len() < 3 {
                continue;
            }

            let container_id = parts[0];
            let container_name = parts[1];
            let image = parts[2].to_lowercase();

            // Detect Redis containers by image name
            if image.contains("redis") 
                || image.contains("bitnami/redis")
                || image.contains("valkey")
            {
                info!("Detected Redis container: {} ({})", container_name, container_id);
                redis_containers.push((container_id.to_string(), container_name.to_string()));
            }
        }

        redis_containers
    }

    /// Collect all Redis metrics from detected containers
    pub async fn collect_and_send(&self) -> Result<(), Box<dyn std::error::Error>> {
        let containers = self.detect_redis_containers();
        
        if containers.is_empty() {
            debug!("No Redis containers detected");
            return Ok(());
        }

        for (container_id, container_name) in containers {
            match self.collect_container_metrics(&container_id, &container_name).await {
                Ok(metrics) => {
                    if let Err(e) = self.send_to_clickhouse(&metrics).await {
                        error!("Failed to send Redis metrics to ClickHouse: {}", e);
                    } else {
                        info!("Sent Redis metrics for container: {}", container_name);
                    }
                }
                Err(e) => {
                    warn!("Failed to collect Redis metrics from {}: {}", container_name, e);
                }
            }
        }

        Ok(())
    }

    /// Collect metrics from a single Redis container
    async fn collect_container_metrics(
        &self,
        container_id: &str,
        container_name: &str,
    ) -> Result<RedisMetrics, Box<dyn std::error::Error>> {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_secs() as i64;

        // Get Redis INFO output
        let info_output = self.execute_redis_info(container_id)?;
        
        // Parse all sections
        let mut metrics = HashMap::new();
        let mut keyspace = HashMap::new();

        // Parse memory metrics
        self.parse_memory_metrics(&info_output, &mut metrics);
        
        // Parse stats metrics
        self.parse_stats_metrics(&info_output, &mut metrics);
        
        // Parse clients metrics
        self.parse_clients_metrics(&info_output, &mut metrics);
        
        // Parse persistence metrics
        self.parse_persistence_metrics(&info_output, &mut metrics);
        
        // Parse replication metrics
        self.parse_replication_metrics(&info_output, &mut metrics);
        
        // Parse keyspace metrics
        self.parse_keyspace_metrics(&info_output, &mut keyspace);

        // Calculate derived metrics
        self.calculate_derived_metrics(&mut metrics);

        Ok(RedisMetrics {
            timestamp,
            hostname: self.hostname.clone(),
            container_id: container_id.to_string(),
            container_name: container_name.to_string(),
            metrics,
            keyspace,
        })
    }

    /// Execute redis-cli INFO command
    fn execute_redis_info(&self, container_id: &str) -> Result<String, Box<dyn std::error::Error>> {
        // Try without password first
        let output = Command::new(&self.docker_path)
            .args(&["exec", container_id, "redis-cli", "INFO", "ALL"])
            .output()?;

        if output.status.success() {
            return Ok(String::from_utf8_lossy(&output.stdout).to_string());
        }

        // Try with REDISCLI_AUTH environment variable
        let output = Command::new(&self.docker_path)
            .args(&[
                "exec", container_id,
                "sh", "-c", "redis-cli -a \"$REDIS_PASSWORD\" INFO ALL 2>/dev/null || redis-cli INFO ALL"
            ])
            .output()?;

        if output.status.success() {
            return Ok(String::from_utf8_lossy(&output.stdout).to_string());
        }

        Err("Failed to execute redis-cli INFO".into())
    }

    /// Parse memory section from INFO output
    fn parse_memory_metrics(&self, info: &str, metrics: &mut HashMap<String, f64>) {
        let memory_keys = [
            ("used_memory", "used_memory"),
            ("used_memory_rss", "used_memory_rss"),
            ("used_memory_peak", "used_memory_peak"),
            ("maxmemory", "maxmemory"),
            ("mem_fragmentation_ratio", "mem_fragmentation_ratio"),
            ("used_memory_lua", "used_memory_lua"),
            ("used_memory_scripts", "used_memory_scripts"),
        ];

        for (info_key, metric_name) in memory_keys {
            if let Some(value) = self.extract_value(info, info_key) {
                metrics.insert(metric_name.to_string(), value);
            }
        }
    }

    /// Parse stats section from INFO output
    fn parse_stats_metrics(&self, info: &str, metrics: &mut HashMap<String, f64>) {
        let stats_keys = [
            ("total_connections_received", "total_connections_received"),
            ("total_commands_processed", "total_commands_processed"),
            ("instantaneous_ops_per_sec", "ops_per_sec"),
            ("rejected_connections", "rejected_connections"),
            ("sync_full", "sync_full"),
            ("sync_partial_ok", "sync_partial_ok"),
            ("sync_partial_err", "sync_partial_err"),
            ("expired_keys", "expired_keys"),
            ("evicted_keys", "evicted_keys"),
            ("keyspace_hits", "keyspace_hits"),
            ("keyspace_misses", "keyspace_misses"),
            ("pubsub_channels", "pubsub_channels"),
            ("pubsub_patterns", "pubsub_patterns"),
            ("latest_fork_usec", "latest_fork_usec"),
            ("total_reads_processed", "total_reads_processed"),
            ("total_writes_processed", "total_writes_processed"),
        ];

        for (info_key, metric_name) in stats_keys {
            if let Some(value) = self.extract_value(info, info_key) {
                metrics.insert(metric_name.to_string(), value);
            }
        }
    }

    /// Parse clients section from INFO output
    fn parse_clients_metrics(&self, info: &str, metrics: &mut HashMap<String, f64>) {
        let clients_keys = [
            ("connected_clients", "connected_clients"),
            ("blocked_clients", "blocked_clients"),
            ("tracking_clients", "tracking_clients"),
            ("clients_in_timeout_table", "clients_in_timeout_table"),
        ];

        for (info_key, metric_name) in clients_keys {
            if let Some(value) = self.extract_value(info, info_key) {
                metrics.insert(metric_name.to_string(), value);
            }
        }
    }

    /// Parse persistence section from INFO output
    fn parse_persistence_metrics(&self, info: &str, metrics: &mut HashMap<String, f64>) {
        let persistence_keys = [
            ("rdb_changes_since_last_save", "rdb_changes_since_last_save"),
            ("rdb_bgsave_in_progress", "rdb_bgsave_in_progress"),
            ("rdb_last_save_time", "rdb_last_save_time"),
            ("rdb_last_bgsave_time_sec", "rdb_last_bgsave_time_sec"),
            ("rdb_current_bgsave_time_sec", "rdb_current_bgsave_time_sec"),
            ("rdb_last_cow_size", "rdb_last_cow_size"),
            ("aof_enabled", "aof_enabled"),
            ("aof_rewrite_in_progress", "aof_rewrite_in_progress"),
            ("aof_rewrite_scheduled", "aof_rewrite_scheduled"),
            ("aof_last_rewrite_time_sec", "aof_last_rewrite_time_sec"),
            ("aof_current_rewrite_time_sec", "aof_current_rewrite_time_sec"),
            ("aof_last_cow_size", "aof_last_cow_size"),
            ("aof_current_size", "aof_current_size"),
            ("aof_base_size", "aof_base_size"),
            ("aof_delayed_fsync", "aof_delayed_fsync"),
        ];

        for (info_key, metric_name) in persistence_keys {
            if let Some(value) = self.extract_value(info, info_key) {
                metrics.insert(metric_name.to_string(), value);
            }
        }
    }

    /// Parse replication section from INFO output
    fn parse_replication_metrics(&self, info: &str, metrics: &mut HashMap<String, f64>) {
        // Check role
        let role = self.extract_string(info, "role").unwrap_or_else(|| "master".to_string());
        metrics.insert("is_master".to_string(), if role == "master" { 1.0 } else { 0.0 });

        let replication_keys = [
            ("connected_slaves", "connected_slaves"),
            ("master_replid", "master_replid"),
            ("master_repl_offset", "master_repl_offset"),
            ("repl_backlog_active", "repl_backlog_active"),
            ("repl_backlog_size", "repl_backlog_size"),
            ("repl_backlog_first_byte_offset", "repl_backlog_first_byte_offset"),
            ("repl_backlog_histlen", "repl_backlog_histlen"),
        ];

        for (info_key, metric_name) in replication_keys {
            if let Some(value) = self.extract_value(info, info_key) {
                metrics.insert(metric_name.to_string(), value);
            }
        }

        // If this is a replica, get master link status
        if role == "slave" {
            if let Some(value) = self.extract_value(info, "master_link_status") {
                // master_link_status is a string, convert "up" = 1, else = 0
                let status = self.extract_string(info, "master_link_status").unwrap_or_default();
                metrics.insert("master_link_up".to_string(), if status == "up" { 1.0 } else { 0.0 });
            }
            
            if let Some(value) = self.extract_value(info, "slave_repl_offset") {
                metrics.insert("slave_repl_offset".to_string(), value);
            }
        }
    }

    /// Parse keyspace section from INFO output
    fn parse_keyspace_metrics(&self, info: &str, keyspace: &mut HashMap<String, KeyspaceInfo>) {
        // Keyspace lines look like: db0:keys=1000,expires=100,avg_ttl=1000
        for line in info.lines() {
            if line.starts_with("db") && line.contains(":keys=") {
                let parts: Vec<&str> = line.splitn(2, ':').collect();
                if parts.len() != 2 {
                    continue;
                }

                let db_name = parts[0].to_string();
                let stats_str = parts[1];
                
                let mut keys: i64 = 0;
                let mut expires: i64 = 0;
                let mut avg_ttl: i64 = 0;

                for stat in stats_str.split(',') {
                    if let Some(val) = stat.strip_prefix("keys=") {
                        keys = val.parse().unwrap_or(0);
                    } else if let Some(val) = stat.strip_prefix("expires=") {
                        expires = val.parse().unwrap_or(0);
                    } else if let Some(val) = stat.strip_prefix("avg_ttl=") {
                        avg_ttl = val.parse().unwrap_or(0);
                    }
                }

                keyspace.insert(db_name, KeyspaceInfo { keys, expires, avg_ttl });
            }
        }
    }

    /// Calculate derived metrics
    fn calculate_derived_metrics(&self, metrics: &mut HashMap<String, f64>) {
        // Hit rate = hits / (hits + misses)
        let hits = metrics.get("keyspace_hits").copied().unwrap_or(0.0);
        let misses = metrics.get("keyspace_misses").copied().unwrap_or(0.0);
        let total = hits + misses;
        if total > 0.0 {
            let hit_rate = hits / total * 100.0;
            metrics.insert("hit_rate_percent".to_string(), hit_rate);
        }

        // Memory usage percent
        let used = metrics.get("used_memory").copied().unwrap_or(0.0);
        let max = metrics.get("maxmemory").copied().unwrap_or(0.0);
        if max > 0.0 {
            let usage_percent = used / max * 100.0;
            metrics.insert("memory_usage_percent".to_string(), usage_percent);
        }
    }

    /// Extract a numeric value from INFO output
    fn extract_value(&self, info: &str, key: &str) -> Option<f64> {
        for line in info.lines() {
            if line.starts_with(key) {
                let parts: Vec<&str> = line.splitn(2, ':').collect();
                if parts.len() == 2 {
                    return parts[1].trim().parse().ok();
                }
            }
        }
        None
    }

    /// Extract a string value from INFO output
    fn extract_string(&self, info: &str, key: &str) -> Option<String> {
        for line in info.lines() {
            if line.starts_with(key) {
                let parts: Vec<&str> = line.splitn(2, ':').collect();
                if parts.len() == 2 {
                    return Some(parts[1].trim().to_string());
                }
            }
        }
        None
    }

    /// Send metrics to ClickHouse
    async fn send_to_clickhouse(&self, metrics: &RedisMetrics) -> Result<(), Box<dyn std::error::Error>> {
        let client = reqwest::Client::new();

        // Send all metrics
        for (metric_name, value) in &metrics.metrics {
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": metric_name,
                "value": value,
                "db": ""
            });

            let response = client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO redis_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;

            if !response.status().is_success() {
                let body = response.text().await.unwrap_or_default();
                error!("ClickHouse insert failed: {}", body);
            }
        }

        // Send keyspace metrics per database
        for (db_name, ks_info) in &metrics.keyspace {
            // Total keys
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": "keys_total",
                "value": ks_info.keys as f64,
                "db": db_name
            });

            client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO redis_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;

            // Expiring keys
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": "keys_with_expiry",
                "value": ks_info.expires as f64,
                "db": db_name
            });

            client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO redis_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;

            // Average TTL
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": "avg_ttl_ms",
                "value": ks_info.avg_ttl as f64,
                "db": db_name
            });

            client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO redis_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;
        }

        Ok(())
    }
}
