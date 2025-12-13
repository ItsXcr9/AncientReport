// PostgreSQL Container Monitor for AncientReport V3
// Collects deep PostgreSQL metrics via docker exec psql

use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::process::Command;
use tracing::{debug, error, info, warn};

/// PostgreSQL metrics collected from a container
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostgresMetrics {
    pub timestamp: i64,
    pub hostname: String,
    pub container_id: String,
    pub container_name: String,
    pub databases: Vec<DatabaseMetrics>,
    pub global_metrics: HashMap<String, f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseMetrics {
    pub database: String,
    pub metrics: HashMap<String, f64>,
}

pub struct PostgresMonitor {
    hostname: String,
    clickhouse_url: String,
    docker_path: String,
}

impl PostgresMonitor {
    pub fn new(hostname: String, clickhouse_url: String) -> Self {
        let docker_path = Self::find_docker_binary();
        info!("PostgreSQL monitor initialized with hostname: {}", hostname);
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

    /// Detect PostgreSQL containers running on this host
    pub fn detect_postgres_containers(&self) -> Vec<(String, String)> {
        let output = Command::new(&self.docker_path)
            .args(&["ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}"])
            .output();

        let output = match output {
            Ok(o) if o.status.success() => o,
            _ => return Vec::new(),
        };

        let stdout = String::from_utf8_lossy(&output.stdout);
        let mut postgres_containers = Vec::new();

        for line in stdout.lines() {
            let parts: Vec<&str> = line.split('|').collect();
            if parts.len() < 3 {
                continue;
            }

            let container_id = parts[0];
            let container_name = parts[1];
            let image = parts[2].to_lowercase();

            // Detect PostgreSQL containers by image name
            if image.contains("postgres") 
                || image.contains("postgresql")
                || image.contains("bitnami/postgresql")
                || image.contains("timescale")
                || image.contains("supabase")
            {
                info!("Detected PostgreSQL container: {} ({})", container_name, container_id);
                postgres_containers.push((container_id.to_string(), container_name.to_string()));
            }
        }

        postgres_containers
    }

    /// Collect all PostgreSQL metrics from detected containers
    pub async fn collect_and_send(&self) -> Result<(), Box<dyn std::error::Error>> {
        let containers = self.detect_postgres_containers();
        
        if containers.is_empty() {
            debug!("No PostgreSQL containers detected");
            return Ok(());
        }

        for (container_id, container_name) in containers {
            match self.collect_container_metrics(&container_id, &container_name).await {
                Ok(metrics) => {
                    if let Err(e) = self.send_to_clickhouse(&metrics).await {
                        error!("Failed to send PostgreSQL metrics to ClickHouse: {}", e);
                    } else {
                        info!("Sent PostgreSQL metrics for container: {}", container_name);
                    }
                }
                Err(e) => {
                    warn!("Failed to collect PostgreSQL metrics from {}: {}", container_name, e);
                }
            }
        }

        Ok(())
    }

    /// Collect metrics from a single PostgreSQL container
    async fn collect_container_metrics(
        &self,
        container_id: &str,
        container_name: &str,
    ) -> Result<PostgresMetrics, Box<dyn std::error::Error>> {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_secs() as i64;

        let mut global_metrics = HashMap::new();
        let mut databases = Vec::new();

        // Collect connection metrics
        self.collect_connection_metrics(container_id, &mut global_metrics);

        // Collect max_connections setting
        self.collect_settings(container_id, &mut global_metrics);

        // Collect replication metrics
        self.collect_replication_metrics(container_id, &mut global_metrics);

        // Collect bgwriter metrics (checkpoint stats)
        self.collect_bgwriter_metrics(container_id, &mut global_metrics);

        // Collect WAL metrics
        self.collect_wal_metrics(container_id, &mut global_metrics);

        // Collect per-database metrics
        let db_names = self.list_databases(container_id);
        for db_name in db_names {
            if let Some(db_metrics) = self.collect_database_metrics(container_id, &db_name) {
                databases.push(DatabaseMetrics {
                    database: db_name,
                    metrics: db_metrics,
                });
            }
        }

        Ok(PostgresMetrics {
            timestamp,
            hostname: self.hostname.clone(),
            container_id: container_id.to_string(),
            container_name: container_name.to_string(),
            databases,
            global_metrics,
        })
    }

    /// Execute a psql query against the container
    fn execute_psql(&self, container_id: &str, query: &str) -> Option<String> {
        // Try with POSTGRES_USER env var first
        let output = Command::new(&self.docker_path)
            .args(&[
                "exec", container_id,
                "sh", "-c",
                &format!("psql -U \"${{POSTGRES_USER:-postgres}}\" -d postgres -At -c \"{}\"", query)
            ])
            .output();

        if let Ok(output) = output {
            if output.status.success() {
                return Some(String::from_utf8_lossy(&output.stdout).to_string());
            }
        }

        // Fallback to direct psql
        let output = Command::new(&self.docker_path)
            .args(&["exec", container_id, "psql", "-U", "postgres", "-At", "-c", query])
            .output();

        if let Ok(output) = output {
            if output.status.success() {
                return Some(String::from_utf8_lossy(&output.stdout).to_string());
            }
        }

        None
    }

    /// Execute a psql query for a specific database
    fn execute_psql_db(&self, container_id: &str, database: &str, query: &str) -> Option<String> {
        let output = Command::new(&self.docker_path)
            .args(&[
                "exec", container_id,
                "sh", "-c",
                &format!("psql -U \"${{POSTGRES_USER:-postgres}}\" -d \"{}\" -At -c \"{}\"", database, query)
            ])
            .output();

        if let Ok(output) = output {
            if output.status.success() {
                return Some(String::from_utf8_lossy(&output.stdout).to_string());
            }
        }

        None
    }

    /// List all databases
    fn list_databases(&self, container_id: &str) -> Vec<String> {
        let query = "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres'";
        
        if let Some(output) = self.execute_psql(container_id, query) {
            return output
                .lines()
                .filter(|l| !l.is_empty())
                .map(|s| s.trim().to_string())
                .collect();
        }

        Vec::new()
    }

    /// Collect connection metrics from pg_stat_activity
    fn collect_connection_metrics(&self, container_id: &str, metrics: &mut HashMap<String, f64>) {
        // Total connections by state
        let query = r#"
            SELECT 
                state,
                COUNT(*) as count
            FROM pg_stat_activity 
            WHERE pid != pg_backend_pid()
            GROUP BY state
        "#;

        if let Some(output) = self.execute_psql(container_id, query) {
            for line in output.lines() {
                let parts: Vec<&str> = line.split('|').collect();
                if parts.len() == 2 {
                    let state = parts[0].trim();
                    let count: f64 = parts[1].trim().parse().unwrap_or(0.0);
                    
                    match state {
                        "active" => { metrics.insert("connections_active".to_string(), count); }
                        "idle" => { metrics.insert("connections_idle".to_string(), count); }
                        "idle in transaction" => { metrics.insert("connections_idle_in_transaction".to_string(), count); }
                        "idle in transaction (aborted)" => { metrics.insert("connections_idle_in_transaction_aborted".to_string(), count); }
                        "fastpath function call" => { metrics.insert("connections_fastpath".to_string(), count); }
                        "disabled" => { metrics.insert("connections_disabled".to_string(), count); }
                        _ => {}
                    }
                }
            }
        }

        // Total connection count
        let query = "SELECT COUNT(*) FROM pg_stat_activity WHERE pid != pg_backend_pid()";
        if let Some(output) = self.execute_psql(container_id, query) {
            if let Ok(count) = output.trim().parse::<f64>() {
                metrics.insert("connections_total".to_string(), count);
            }
        }

        // Waiting on locks
        let query = "SELECT COUNT(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'";
        if let Some(output) = self.execute_psql(container_id, query) {
            if let Ok(count) = output.trim().parse::<f64>() {
                metrics.insert("connections_waiting_on_lock".to_string(), count);
            }
        }
    }

    /// Collect PostgreSQL settings
    fn collect_settings(&self, container_id: &str, metrics: &mut HashMap<String, f64>) {
        // max_connections
        let query = "SHOW max_connections";
        if let Some(output) = self.execute_psql(container_id, query) {
            if let Ok(value) = output.trim().parse::<f64>() {
                metrics.insert("max_connections".to_string(), value);
            }
        }

        // shared_buffers (in 8KB pages)
        let query = "SELECT setting::bigint * 8192 FROM pg_settings WHERE name = 'shared_buffers'";
        if let Some(output) = self.execute_psql(container_id, query) {
            if let Ok(value) = output.trim().parse::<f64>() {
                metrics.insert("shared_buffers_bytes".to_string(), value);
            }
        }

        // effective_cache_size
        let query = "SELECT setting::bigint * 8192 FROM pg_settings WHERE name = 'effective_cache_size'";
        if let Some(output) = self.execute_psql(container_id, query) {
            if let Ok(value) = output.trim().parse::<f64>() {
                metrics.insert("effective_cache_size_bytes".to_string(), value);
            }
        }
    }

    /// Collect replication metrics
    fn collect_replication_metrics(&self, container_id: &str, metrics: &mut HashMap<String, f64>) {
        // Check if this is a primary with replicas
        let query = r#"
            SELECT 
                client_addr,
                state,
                pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) as send_lag,
                pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) as write_lag,
                pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) as flush_lag,
                pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as replay_lag
            FROM pg_stat_replication
        "#;

        if let Some(output) = self.execute_psql(container_id, query) {
            let mut replica_count = 0;
            let mut max_replay_lag: f64 = 0.0;

            for line in output.lines() {
                if line.is_empty() {
                    continue;
                }
                let parts: Vec<&str> = line.split('|').collect();
                if parts.len() >= 6 {
                    replica_count += 1;
                    if let Ok(lag) = parts[5].trim().parse::<f64>() {
                        if lag > max_replay_lag {
                            max_replay_lag = lag;
                        }
                    }
                }
            }

            metrics.insert("replication_replicas_connected".to_string(), replica_count as f64);
            metrics.insert("replication_max_lag_bytes".to_string(), max_replay_lag);
        }

        // Check if this is a replica
        let query = "SELECT pg_is_in_recovery()";
        if let Some(output) = self.execute_psql(container_id, query) {
            let is_replica = output.trim() == "t";
            metrics.insert("is_replica".to_string(), if is_replica { 1.0 } else { 0.0 });

            if is_replica {
                // Get replay lag in seconds
                let query = "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())), 0)";
                if let Some(output) = self.execute_psql(container_id, query) {
                    if let Ok(lag) = output.trim().parse::<f64>() {
                        metrics.insert("replica_lag_seconds".to_string(), lag);
                    }
                }
            }
        }
    }

    /// Collect bgwriter metrics (checkpoints)
    fn collect_bgwriter_metrics(&self, container_id: &str, metrics: &mut HashMap<String, f64>) {
        let query = r#"
            SELECT 
                checkpoints_timed,
                checkpoints_req,
                checkpoint_write_time,
                checkpoint_sync_time,
                buffers_checkpoint,
                buffers_clean,
                maxwritten_clean,
                buffers_backend,
                buffers_backend_fsync,
                buffers_alloc
            FROM pg_stat_bgwriter
        "#;

        if let Some(output) = self.execute_psql(container_id, query) {
            let parts: Vec<&str> = output.trim().split('|').collect();
            if parts.len() >= 10 {
                if let Ok(v) = parts[0].trim().parse::<f64>() { metrics.insert("checkpoints_timed".to_string(), v); }
                if let Ok(v) = parts[1].trim().parse::<f64>() { metrics.insert("checkpoints_requested".to_string(), v); }
                if let Ok(v) = parts[2].trim().parse::<f64>() { metrics.insert("checkpoint_write_time_ms".to_string(), v); }
                if let Ok(v) = parts[3].trim().parse::<f64>() { metrics.insert("checkpoint_sync_time_ms".to_string(), v); }
                if let Ok(v) = parts[4].trim().parse::<f64>() { metrics.insert("buffers_checkpoint".to_string(), v); }
                if let Ok(v) = parts[5].trim().parse::<f64>() { metrics.insert("buffers_clean".to_string(), v); }
                if let Ok(v) = parts[6].trim().parse::<f64>() { metrics.insert("maxwritten_clean".to_string(), v); }
                if let Ok(v) = parts[7].trim().parse::<f64>() { metrics.insert("buffers_backend".to_string(), v); }
                if let Ok(v) = parts[8].trim().parse::<f64>() { metrics.insert("buffers_backend_fsync".to_string(), v); }
                if let Ok(v) = parts[9].trim().parse::<f64>() { metrics.insert("buffers_alloc".to_string(), v); }
            }
        }
    }

    /// Collect WAL metrics
    fn collect_wal_metrics(&self, container_id: &str, metrics: &mut HashMap<String, f64>) {
        // pg_stat_wal (PostgreSQL 14+)
        let query = r#"
            SELECT 
                wal_records,
                wal_fpi,
                wal_bytes,
                wal_buffers_full,
                wal_write,
                wal_sync,
                wal_write_time,
                wal_sync_time
            FROM pg_stat_wal
        "#;

        if let Some(output) = self.execute_psql(container_id, query) {
            let parts: Vec<&str> = output.trim().split('|').collect();
            if parts.len() >= 8 {
                if let Ok(v) = parts[0].trim().parse::<f64>() { metrics.insert("wal_records".to_string(), v); }
                if let Ok(v) = parts[1].trim().parse::<f64>() { metrics.insert("wal_fpi".to_string(), v); }
                if let Ok(v) = parts[2].trim().parse::<f64>() { metrics.insert("wal_bytes".to_string(), v); }
                if let Ok(v) = parts[3].trim().parse::<f64>() { metrics.insert("wal_buffers_full".to_string(), v); }
                if let Ok(v) = parts[4].trim().parse::<f64>() { metrics.insert("wal_write".to_string(), v); }
                if let Ok(v) = parts[5].trim().parse::<f64>() { metrics.insert("wal_sync".to_string(), v); }
                if let Ok(v) = parts[6].trim().parse::<f64>() { metrics.insert("wal_write_time_ms".to_string(), v); }
                if let Ok(v) = parts[7].trim().parse::<f64>() { metrics.insert("wal_sync_time_ms".to_string(), v); }
            }
        }

        // Current WAL position
        let query = "SELECT pg_current_wal_lsn()::text";
        if let Some(output) = self.execute_psql(container_id, query) {
            // LSN is in format like "0/1234567890" - we can store the numeric part
            let lsn_str = output.trim();
            if let Some(pos) = lsn_str.find('/') {
                if let Ok(lsn) = i64::from_str_radix(&lsn_str[pos+1..], 16) {
                    metrics.insert("current_wal_lsn".to_string(), lsn as f64);
                }
            }
        }
    }

    /// Collect per-database metrics
    fn collect_database_metrics(&self, container_id: &str, database: &str) -> Option<HashMap<String, f64>> {
        let mut db_metrics = HashMap::new();

        // Database stats from pg_stat_database
        let query = format!(r#"
            SELECT 
                numbackends,
                xact_commit,
                xact_rollback,
                blks_read,
                blks_hit,
                tup_returned,
                tup_fetched,
                tup_inserted,
                tup_updated,
                tup_deleted,
                conflicts,
                temp_files,
                temp_bytes,
                deadlocks,
                checksum_failures,
                blk_read_time,
                blk_write_time
            FROM pg_stat_database 
            WHERE datname = '{}'
        "#, database);

        if let Some(output) = self.execute_psql(container_id, &query) {
            let parts: Vec<&str> = output.trim().split('|').collect();
            if parts.len() >= 17 {
                if let Ok(v) = parts[0].trim().parse::<f64>() { db_metrics.insert("backends".to_string(), v); }
                if let Ok(v) = parts[1].trim().parse::<f64>() { db_metrics.insert("xact_commit".to_string(), v); }
                if let Ok(v) = parts[2].trim().parse::<f64>() { db_metrics.insert("xact_rollback".to_string(), v); }
                if let Ok(v) = parts[3].trim().parse::<f64>() { db_metrics.insert("blks_read".to_string(), v); }
                if let Ok(v) = parts[4].trim().parse::<f64>() { db_metrics.insert("blks_hit".to_string(), v); }
                if let Ok(v) = parts[5].trim().parse::<f64>() { db_metrics.insert("tup_returned".to_string(), v); }
                if let Ok(v) = parts[6].trim().parse::<f64>() { db_metrics.insert("tup_fetched".to_string(), v); }
                if let Ok(v) = parts[7].trim().parse::<f64>() { db_metrics.insert("tup_inserted".to_string(), v); }
                if let Ok(v) = parts[8].trim().parse::<f64>() { db_metrics.insert("tup_updated".to_string(), v); }
                if let Ok(v) = parts[9].trim().parse::<f64>() { db_metrics.insert("tup_deleted".to_string(), v); }
                if let Ok(v) = parts[10].trim().parse::<f64>() { db_metrics.insert("conflicts".to_string(), v); }
                if let Ok(v) = parts[11].trim().parse::<f64>() { db_metrics.insert("temp_files".to_string(), v); }
                if let Ok(v) = parts[12].trim().parse::<f64>() { db_metrics.insert("temp_bytes".to_string(), v); }
                if let Ok(v) = parts[13].trim().parse::<f64>() { db_metrics.insert("deadlocks".to_string(), v); }
                // checksum_failures might be null
                if let Ok(v) = parts[14].trim().parse::<f64>() { db_metrics.insert("checksum_failures".to_string(), v); }
                if let Ok(v) = parts[15].trim().parse::<f64>() { db_metrics.insert("blk_read_time_ms".to_string(), v); }
                if let Ok(v) = parts[16].trim().parse::<f64>() { db_metrics.insert("blk_write_time_ms".to_string(), v); }

                // Calculate cache hit ratio
                let blks_hit = db_metrics.get("blks_hit").copied().unwrap_or(0.0);
                let blks_read = db_metrics.get("blks_read").copied().unwrap_or(0.0);
                let total = blks_hit + blks_read;
                if total > 0.0 {
                    let hit_ratio = blks_hit / total * 100.0;
                    db_metrics.insert("cache_hit_ratio".to_string(), hit_ratio);
                }
            }
        }

        // Dead tuples and autovacuum info
        let query = format!(r#"
            SELECT 
                COALESCE(SUM(n_dead_tup), 0) as dead_tuples,
                COALESCE(SUM(n_live_tup), 0) as live_tuples,
                COUNT(*) as table_count
            FROM pg_stat_user_tables
        "#);

        if let Some(output) = self.execute_psql_db(container_id, database, &query) {
            let parts: Vec<&str> = output.trim().split('|').collect();
            if parts.len() >= 3 {
                if let Ok(v) = parts[0].trim().parse::<f64>() { db_metrics.insert("dead_tuples".to_string(), v); }
                if let Ok(v) = parts[1].trim().parse::<f64>() { db_metrics.insert("live_tuples".to_string(), v); }
                if let Ok(v) = parts[2].trim().parse::<f64>() { db_metrics.insert("table_count".to_string(), v); }

                // Dead tuple ratio
                let dead = db_metrics.get("dead_tuples").copied().unwrap_or(0.0);
                let live = db_metrics.get("live_tuples").copied().unwrap_or(0.0);
                let total = dead + live;
                if total > 0.0 {
                    let dead_ratio = dead / total * 100.0;
                    db_metrics.insert("dead_tuple_ratio".to_string(), dead_ratio);
                }
            }
        }

        // Database size
        let query = format!("SELECT pg_database_size('{}')", database);
        if let Some(output) = self.execute_psql(container_id, &query) {
            if let Ok(size) = output.trim().parse::<f64>() {
                db_metrics.insert("database_size_bytes".to_string(), size);
            }
        }

        // Lock info
        let query = format!(r#"
            SELECT COUNT(*) FROM pg_locks 
            WHERE database = (SELECT oid FROM pg_database WHERE datname = '{}')
            AND granted = false
        "#, database);

        if let Some(output) = self.execute_psql(container_id, &query) {
            if let Ok(count) = output.trim().parse::<f64>() {
                db_metrics.insert("locks_waiting".to_string(), count);
            }
        }

        if db_metrics.is_empty() {
            None
        } else {
            Some(db_metrics)
        }
    }

    /// Send metrics to ClickHouse
    async fn send_to_clickhouse(&self, metrics: &PostgresMetrics) -> Result<(), Box<dyn std::error::Error>> {
        let client = reqwest::Client::new();

        // Send global metrics
        for (metric_name, value) in &metrics.global_metrics {
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "database": "_global",
                "metric_name": metric_name,
                "value": value,
                "extra": ""
            });

            let response = client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO postgres_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;

            if !response.status().is_success() {
                let body = response.text().await.unwrap_or_default();
                error!("ClickHouse insert failed: {}", body);
            }
        }

        // Send per-database metrics
        for db in &metrics.databases {
            for (metric_name, value) in &db.metrics {
                let data = json!({
                    "timestamp": metrics.timestamp,
                    "hostname": metrics.hostname,
                    "container_id": metrics.container_id,
                    "container_name": metrics.container_name,
                    "database": db.database,
                    "metric_name": metric_name,
                    "value": value,
                    "extra": ""
                });

                client
                    .post(&self.clickhouse_url)
                    .query(&[("query", "INSERT INTO postgres_metrics FORMAT JSONEachRow")])
                    .json(&data)
                    .send()
                    .await?;
            }
        }

        Ok(())
    }
}
