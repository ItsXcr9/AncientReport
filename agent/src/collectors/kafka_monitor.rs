// Kafka Container Monitor for AncientReport V3
// Collects deep Kafka metrics via docker exec

use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::process::Command;
use tracing::{debug, error, info, warn};

/// Kafka metrics collected from a broker
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KafkaMetrics {
    pub timestamp: i64,
    pub hostname: String,
    pub container_id: String,
    pub container_name: String,
    pub broker_id: String,
    pub metrics: HashMap<String, f64>,
    pub consumer_groups: Vec<ConsumerGroupLag>,
    pub topics: Vec<TopicMetrics>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsumerGroupLag {
    pub group: String,
    pub topic: String,
    pub partition: i32,
    pub current_offset: i64,
    pub log_end_offset: i64,
    pub lag: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TopicMetrics {
    pub topic: String,
    pub partitions: i32,
    pub replication_factor: i32,
    pub under_replicated: i32,
    pub isr_count: i32,
}

pub struct KafkaMonitor {
    hostname: String,
    clickhouse_url: String,
    docker_path: String,
}

impl KafkaMonitor {
    pub fn new(hostname: String, clickhouse_url: String) -> Self {
        let docker_path = Self::find_docker_binary();
        info!("Kafka monitor initialized with hostname: {}", hostname);
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

    /// Detect Kafka containers running on this host
    pub fn detect_kafka_containers(&self) -> Vec<(String, String)> {
        let output = Command::new(&self.docker_path)
            .args(&["ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}"])
            .output();

        let output = match output {
            Ok(o) if o.status.success() => o,
            _ => return Vec::new(),
        };

        let stdout = String::from_utf8_lossy(&output.stdout);
        let mut kafka_containers = Vec::new();

        for line in stdout.lines() {
            let parts: Vec<&str> = line.split('|').collect();
            if parts.len() < 3 {
                continue;
            }

            let container_id = parts[0];
            let container_name = parts[1];
            let image = parts[2].to_lowercase();

            // Detect Kafka containers by image name
            if image.contains("kafka") 
                || image.contains("confluentinc") 
                || image.contains("bitnami/kafka")
                || image.contains("wurstmeister/kafka")
            {
                info!("Detected Kafka container: {} ({})", container_name, container_id);
                kafka_containers.push((container_id.to_string(), container_name.to_string()));
            }
        }

        kafka_containers
    }

    /// Collect all Kafka metrics from detected containers
    pub async fn collect_and_send(&self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let containers = self.detect_kafka_containers();
        
        if containers.is_empty() {
            debug!("No Kafka containers detected");
            return Ok(());
        }

        for (container_id, container_name) in containers {
            match self.collect_container_metrics(&container_id, &container_name).await {
                Ok(metrics) => {
                    if let Err(e) = self.send_to_clickhouse(&metrics).await {
                        error!("Failed to send Kafka metrics to ClickHouse: {}", e);
                    } else {
                        info!("Sent Kafka metrics for container: {}", container_name);
                    }
                }
                Err(e) => {
                    warn!("Failed to collect Kafka metrics from {}: {}", container_name, e);
                }
            }
        }

        Ok(())
    }

    /// Collect metrics from a single Kafka container
    async fn collect_container_metrics(
        &self,
        container_id: &str,
        container_name: &str,
    ) -> Result<KafkaMetrics, Box<dyn std::error::Error + Send + Sync>> {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_secs() as i64;

        let mut metrics = HashMap::new();
        
        // Get broker ID from broker.id file or environment
        let broker_id = self.get_broker_id(container_id).unwrap_or_else(|| "0".to_string());

        // Collect consumer group lag
        let consumer_groups = self.collect_consumer_lag(container_id);

        // Collect topic metrics (under-replicated partitions, ISR)
        let topics = self.collect_topic_metrics(container_id);

        // Calculate aggregate metrics
        let total_lag: i64 = consumer_groups.iter().map(|g| g.lag).sum();
        metrics.insert("total_consumer_lag".to_string(), total_lag as f64);

        let under_replicated: i32 = topics.iter().map(|t| t.under_replicated).sum();
        metrics.insert("under_replicated_partitions".to_string(), under_replicated as f64);

        let total_partitions: i32 = topics.iter().map(|t| t.partitions).sum();
        metrics.insert("total_partitions".to_string(), total_partitions as f64);

        // Get JMX metrics if available (via kafka-run-class.sh)
        if let Some(jmx_metrics) = self.collect_jmx_metrics(container_id) {
            for (k, v) in jmx_metrics {
                metrics.insert(k, v);
            }
        }

        // Get disk usage
        if let Some(disk_bytes) = self.get_disk_usage(container_id) {
            metrics.insert("disk_usage_bytes".to_string(), disk_bytes);
        }

        Ok(KafkaMetrics {
            timestamp,
            hostname: self.hostname.clone(),
            container_id: container_id.to_string(),
            container_name: container_name.to_string(),
            broker_id,
            metrics,
            consumer_groups,
            topics,
        })
    }

    /// Get broker ID from the container
    fn get_broker_id(&self, container_id: &str) -> Option<String> {
        // Try getting from environment variable first
        let output = Command::new(&self.docker_path)
            .args(&["exec", container_id, "printenv", "KAFKA_BROKER_ID"])
            .output()
            .ok()?;

        if output.status.success() {
            let broker_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !broker_id.is_empty() {
                return Some(broker_id);
            }
        }

        // Try KAFKA_CFG_BROKER_ID (Bitnami)
        let output = Command::new(&self.docker_path)
            .args(&["exec", container_id, "printenv", "KAFKA_CFG_BROKER_ID"])
            .output()
            .ok()?;

        if output.status.success() {
            let broker_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !broker_id.is_empty() {
                return Some(broker_id);
            }
        }

        None
    }

    /// Collect consumer group lag using kafka-consumer-groups.sh
    fn collect_consumer_lag(&self, container_id: &str) -> Vec<ConsumerGroupLag> {
        let mut lags = Vec::new();

        // First, list all consumer groups
        let groups = self.list_consumer_groups(container_id);
        
        for group in groups {
            if let Some(group_lags) = self.get_consumer_group_lag(container_id, &group) {
                lags.extend(group_lags);
            }
        }

        lags
    }

    /// List all consumer groups
    fn list_consumer_groups(&self, container_id: &str) -> Vec<String> {
        // Try different paths for kafka-consumer-groups.sh
        // First check if the script exists to avoid spamming docker daemon with errors
        let scripts = vec![
            "/opt/kafka/bin/kafka-consumer-groups.sh",
            "/opt/bitnami/kafka/bin/kafka-consumer-groups.sh",
            "/usr/bin/kafka-consumer-groups",
            "kafka-consumer-groups.sh",
        ];

        for script in scripts {
            // First check if script exists to avoid error spam
            let check = Command::new(&self.docker_path)
                .args(&["exec", container_id, "test", "-x", script])
                .output();
            
            if let Ok(check_output) = check {
                if !check_output.status.success() {
                    continue; // Script doesn't exist, try next
                }
            } else {
                continue;
            }

            // Script exists, now run it
            let output = Command::new(&self.docker_path)
                .args(&[
                    "exec", container_id, script,
                    "--bootstrap-server", "localhost:9092",
                    "--list"
                ])
                .output();

            if let Ok(output) = output {
                if output.status.success() {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    return stdout
                        .lines()
                        .filter(|l| !l.is_empty() && !l.starts_with("Consumer"))
                        .map(|s| s.trim().to_string())
                        .collect();
                }
            }
        }

        Vec::new()
    }

    /// Get lag for a specific consumer group
    fn get_consumer_group_lag(&self, container_id: &str, group: &str) -> Option<Vec<ConsumerGroupLag>> {
        let scripts = vec![
            "/opt/kafka/bin/kafka-consumer-groups.sh",
            "/opt/bitnami/kafka/bin/kafka-consumer-groups.sh",
            "/usr/bin/kafka-consumer-groups",
            "kafka-consumer-groups.sh",
        ];

        for script in scripts {
            // First check if script exists to avoid error spam
            let check = Command::new(&self.docker_path)
                .args(&["exec", container_id, "test", "-x", script])
                .output();
            
            if let Ok(check_output) = check {
                if !check_output.status.success() {
                    continue; // Script doesn't exist, try next
                }
            } else {
                continue;
            }

            // Script exists, now run it
            let output = Command::new(&self.docker_path)
                .args(&[
                    "exec", container_id, script,
                    "--bootstrap-server", "localhost:9092",
                    "--describe", "--group", group
                ])
                .output();

            if let Ok(output) = output {
                if output.status.success() {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    return Some(self.parse_consumer_group_output(&stdout, group));
                }
            }
        }

        None
    }

    /// Parse kafka-consumer-groups.sh --describe output
    fn parse_consumer_group_output(&self, output: &str, group: &str) -> Vec<ConsumerGroupLag> {
        let mut lags = Vec::new();

        for line in output.lines().skip(1) {
            // Skip header and empty lines
            if line.is_empty() || line.starts_with("GROUP") || line.starts_with("Consumer") {
                continue;
            }

            let parts: Vec<&str> = line.split_whitespace().collect();
            // Expected format: GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG ...
            if parts.len() >= 6 {
                let topic = parts[1].to_string();
                let partition = parts[2].parse().unwrap_or(0);
                let current_offset = parts[3].parse().unwrap_or(0);
                let log_end_offset = parts[4].parse().unwrap_or(0);
                let lag = parts[5].parse().unwrap_or(0);

                lags.push(ConsumerGroupLag {
                    group: group.to_string(),
                    topic,
                    partition,
                    current_offset,
                    log_end_offset,
                    lag,
                });
            }
        }

        lags
    }

    /// Collect topic metrics (under-replicated partitions, ISR)
    fn collect_topic_metrics(&self, container_id: &str) -> Vec<TopicMetrics> {
        let scripts = vec![
            "/opt/kafka/bin/kafka-topics.sh",
            "/opt/bitnami/kafka/bin/kafka-topics.sh",
            "/usr/bin/kafka-topics",
            "kafka-topics.sh",
        ];

        for script in scripts {
            // First check if script exists to avoid error spam
            let check = Command::new(&self.docker_path)
                .args(&["exec", container_id, "test", "-x", script])
                .output();
            
            if let Ok(check_output) = check {
                if !check_output.status.success() {
                    continue; // Script doesn't exist, try next
                }
            } else {
                continue;
            }

            // Script exists, now run it
            let output = Command::new(&self.docker_path)
                .args(&[
                    "exec", container_id, script,
                    "--bootstrap-server", "localhost:9092",
                    "--describe"
                ])
                .output();

            if let Ok(output) = output {
                if output.status.success() {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    return self.parse_topic_describe(&stdout);
                }
            }
        }

        Vec::new()
    }

    /// Parse kafka-topics.sh --describe output
    fn parse_topic_describe(&self, output: &str) -> Vec<TopicMetrics> {
        let mut topics: HashMap<String, TopicMetrics> = HashMap::new();

        for line in output.lines() {
            if line.starts_with("Topic:") {
                // Parse topic line: Topic: foo	PartitionCount: 3	ReplicationFactor: 2
                let parts: Vec<&str> = line.split('\t').collect();
                
                let mut topic_name = String::new();
                let mut partition_count = 0;
                let mut replication_factor = 0;

                for part in parts {
                    if let Some(name) = part.strip_prefix("Topic:") {
                        topic_name = name.trim().to_string();
                    } else if let Some(count) = part.strip_prefix("PartitionCount:") {
                        partition_count = count.trim().parse().unwrap_or(0);
                    } else if let Some(rf) = part.strip_prefix("ReplicationFactor:") {
                        replication_factor = rf.trim().parse().unwrap_or(0);
                    }
                }

                if !topic_name.is_empty() {
                    topics.insert(topic_name.clone(), TopicMetrics {
                        topic: topic_name,
                        partitions: partition_count,
                        replication_factor,
                        under_replicated: 0,
                        isr_count: 0,
                    });
                }
            } else if line.contains("Partition:") && line.contains("Isr:") {
                // Parse partition line for ISR and under-replicated status
                // Partition: 0  Leader: 1  Replicas: 1,2  Isr: 1,2
                let parts: Vec<&str> = line.split('\t').collect();
                
                let mut topic_name = String::new();
                let mut replicas_count = 0;
                let mut isr_count = 0;

                for part in parts {
                    if let Some(name) = part.strip_prefix("Topic:") {
                        topic_name = name.trim().to_string();
                    } else if let Some(replicas) = part.strip_prefix("Replicas:") {
                        replicas_count = replicas.trim().split(',').count() as i32;
                    } else if let Some(isr) = part.strip_prefix("Isr:") {
                        isr_count = isr.trim().split(',').count() as i32;
                    }
                }

                if !topic_name.is_empty() {
                    if let Some(topic) = topics.get_mut(&topic_name) {
                        topic.isr_count += isr_count;
                        if isr_count < replicas_count {
                            topic.under_replicated += 1;
                        }
                    }
                }
            }
        }

        topics.into_values().collect()
    }

    /// Collect JMX metrics via kafka-run-class.sh
    fn collect_jmx_metrics(&self, container_id: &str) -> Option<HashMap<String, f64>> {
        // JMX metrics collection requires JMX port to be exposed
        // This is a simplified version that uses JMX tool if available
        let mut metrics = HashMap::new();

        // Try to get basic broker metrics from kafka.log.Log metrics
        // This is a placeholder - actual JMX collection would require
        // either JMX port access or using kafka-run-class.sh with JMX tools

        // For now, we'll try to get some metrics from broker logs
        let output = Command::new(&self.docker_path)
            .args(&[
                "exec", container_id, 
                "cat", "/opt/kafka/logs/controller.log"
            ])
            .output();

        if let Ok(output) = output {
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                // Count leader elections from log
                let leader_elections = stdout
                    .lines()
                    .filter(|l| l.contains("LeaderElection"))
                    .count();
                metrics.insert("leader_elections_observed".to_string(), leader_elections as f64);
            }
        }

        // Check if this broker is the controller
        let output = Command::new(&self.docker_path)
            .args(&[
                "exec", container_id,
                "cat", "/opt/kafka/logs/controller.log"
            ])
            .output();

        if let Ok(output) = output {
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                // Check for "This broker is now the controller" message
                let is_controller = stdout.contains("Registered broker") && 
                                   stdout.contains("controller");
                metrics.insert("is_controller".to_string(), if is_controller { 1.0 } else { 0.0 });
            }
        }

        if metrics.is_empty() {
            None
        } else {
            Some(metrics)
        }
    }

    /// Get disk usage of Kafka data directory
    fn get_disk_usage(&self, container_id: &str) -> Option<f64> {
        // Try common Kafka data directories
        let data_dirs = vec![
            "/var/lib/kafka/data",
            "/bitnami/kafka/data",
            "/opt/kafka/logs",
            "/kafka",
        ];

        for data_dir in data_dirs {
            let output = Command::new(&self.docker_path)
                .args(&["exec", container_id, "du", "-sb", data_dir])
                .output();

            if let Ok(output) = output {
                if output.status.success() {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    if let Some(size_str) = stdout.split_whitespace().next() {
                        if let Ok(size) = size_str.parse::<f64>() {
                            return Some(size);
                        }
                    }
                }
            }
        }

        None
    }

    /// Send metrics to ClickHouse
    async fn send_to_clickhouse(&self, metrics: &KafkaMetrics) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = reqwest::Client::new();

        // Send aggregate metrics
        for (metric_name, value) in &metrics.metrics {
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "broker_id": metrics.broker_id,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": metric_name,
                "value": value,
                "consumer_group": "",
                "topic": "",
                "partition": -1
            });

            let response = client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO kafka_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;

            if !response.status().is_success() {
                let body = response.text().await.unwrap_or_default();
                error!("ClickHouse insert failed: {}", body);
            }
        }

        // Send consumer group lag metrics
        for lag in &metrics.consumer_groups {
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "broker_id": metrics.broker_id,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": "consumer_lag",
                "value": lag.lag as f64,
                "consumer_group": lag.group,
                "topic": lag.topic,
                "partition": lag.partition
            });

            client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO kafka_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;
        }

        // Send topic metrics
        for topic in &metrics.topics {
            // Under-replicated partitions
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "broker_id": metrics.broker_id,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": "topic_under_replicated",
                "value": topic.under_replicated as f64,
                "consumer_group": "",
                "topic": topic.topic,
                "partition": -1
            });

            client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO kafka_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;

            // ISR count
            let data = json!({
                "timestamp": metrics.timestamp,
                "hostname": metrics.hostname,
                "broker_id": metrics.broker_id,
                "container_id": metrics.container_id,
                "container_name": metrics.container_name,
                "metric_name": "topic_isr_count",
                "value": topic.isr_count as f64,
                "consumer_group": "",
                "topic": topic.topic,
                "partition": -1
            });

            client
                .post(&self.clickhouse_url)
                .query(&[("query", "INSERT INTO kafka_metrics FORMAT JSONEachRow")])
                .json(&data)
                .send()
                .await?;
        }

        Ok(())
    }
}
