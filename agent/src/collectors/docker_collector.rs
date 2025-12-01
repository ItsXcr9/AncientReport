use serde_json::json;
use std::process::Command;
use tracing::{info, warn, error};

pub struct DockerCollector {
    clickhouse_url: String,
    docker_path: String,
}

impl DockerCollector {
    pub fn new(clickhouse_url: String) -> Self {
        let docker_path = Self::find_docker_binary_static();
        info!("Docker collector initialized with binary at: {}", docker_path);
        Self { 
            clickhouse_url,
            docker_path,
        }
    }

    /// Find the Docker binary in common locations (static method for initialization)
    fn find_docker_binary_static() -> String {
        // Common locations where docker might be installed
        let common_paths = vec![
            "/usr/bin/docker",
            "/usr/local/bin/docker",
            "/bin/docker",
            "docker", // This will use PATH
        ];

        for path in common_paths {
            if let Ok(output) = Command::new(path).arg("--version").output() {
                if output.status.success() {
                    return path.to_string();
                }
            }
        }

        // Fallback to default
        warn!("Docker binary not found in common locations, using default /usr/bin/docker");
        "/usr/bin/docker".to_string()
    }



    pub async fn collect_and_send(&self) -> Result<(), Box<dyn std::error::Error>> {
        let containers = self.get_container_stats()?;
        
        if containers.is_empty() {
            info!("No Docker containers found");
            return Ok(());
        }

        self.send_to_clickhouse(&containers).await?;
        info!("Sent stats for {} containers to ClickHouse", containers.len());
        
        Ok(())
    }

    fn get_container_stats(&self) -> Result<Vec<serde_json::Value>, Box<dyn std::error::Error>> {
        // Get all containers (including stopped ones)
        let ps_output = Command::new(&self.docker_path)
            .args(&["ps", "-a", "--no-trunc", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.CreatedAt}}"])
            .output();

        let ps_output = match ps_output {
            Ok(out) => out,
            Err(e) => {
                error!("Failed to execute docker command '{}': {}", self.docker_path, e);
                if let Ok(path) = std::env::var("PATH") {
                    error!("Current PATH: {}", path);
                }
                return Ok(Vec::new()); 
            }
        };

        if !ps_output.status.success() {
            let stderr = String::from_utf8_lossy(&ps_output.stderr);
            warn!("Docker ps command failed: {}", stderr);
            return Ok(Vec::new());
        }

        let ps_list = String::from_utf8_lossy(&ps_output.stdout);
        let mut containers: Vec<serde_json::Value> = Vec::new();

        for line in ps_list.lines() {
            let parts: Vec<&str> = line.split('|').collect();
            if parts.len() < 5 {
                continue;
            }

            let container_id = parts[0];
            let container_name = parts[1];
            let image = parts[2];
            let status = parts[3];
            let created_at = parts[4];

            // Determine if container is running
            let is_running = status.starts_with("Up");

            // Get stats only for running containers
            let (cpu_percent, memory_usage, memory_limit, memory_percent, 
                 net_rx, net_tx, block_read, block_write) = if is_running {
                self.get_running_container_stats(container_id)?
            } else {
                (0.0, 0, 0, 0.0, 0, 0, 0, 0)
            };

            // Parse uptime from status
            let uptime_seconds = self.parse_uptime(status);

            // Get restart count
            let restart_count = self.get_restart_count(container_id)?;

            // Parse created_at to ClickHouse-compatible format
            // Docker format: "2025-12-01 11:52:41 +0000 UTC"
            // ClickHouse format: "2025-12-01 11:52:41"
            let formatted_created_at = self.parse_docker_timestamp(created_at);

            let container_data = json!({
                "container_id": container_id,
                "container_name": container_name,
                "image": image,
                "status": self.normalize_status(status),
                "cpu_percent": cpu_percent,
                "memory_usage": memory_usage,
                "memory_limit": memory_limit,
                "memory_percent": memory_percent,
                "network_rx_bytes": net_rx,
                "network_tx_bytes": net_tx,
                "block_read_bytes": block_read,
                "block_write_bytes": block_write,
                "uptime_seconds": uptime_seconds,
                "restart_count": restart_count,
                "created_at": formatted_created_at,
            });

            containers.push(container_data);
        }

        Ok(containers)
    }

    fn get_running_container_stats(&self, container_id: &str) 
        -> Result<(f64, u64, u64, f64, u64, u64, u64, u64), Box<dyn std::error::Error>> {
        
        let stats_output = Command::new(&self.docker_path)
            .args(&["stats", container_id, "--no-stream", "--format", 
                   "{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}"])
            .output()?;

        if !stats_output.status.success() {
            return Ok((0.0, 0, 0, 0.0, 0, 0, 0, 0));
        }

        let stats_str = String::from_utf8_lossy(&stats_output.stdout);
        let parts: Vec<&str> = stats_str.trim().split('|').collect();
        
        if parts.len() < 4 {
            return Ok((0.0, 0, 0, 0.0, 0, 0, 0, 0));
        }

        // Parse CPU (e.g., "12.34%")
        let cpu_percent = parts[0].trim_end_matches('%').parse::<f64>().unwrap_or(0.0);

        // Parse Memory (e.g., "123.4MiB / 2GiB")
        let (memory_usage, memory_limit, memory_percent) = self.parse_memory(parts[1]);

        // Parse Network (e.g., "1.23MB / 4.56MB")
        let (net_rx, net_tx) = self.parse_network(parts[2]);

        // Parse Block I/O (e.g., "10.2MB / 5.3MB")
        let (block_read, block_write) = self.parse_block_io(parts[3]);

        Ok((cpu_percent, memory_usage, memory_limit, memory_percent, net_rx, net_tx, block_read, block_write))
    }

    fn parse_memory(&self, mem_str: &str) -> (u64, u64, f64) {
        let parts: Vec<&str> = mem_str.split('/').map(|s| s.trim()).collect();
        if parts.len() != 2 {
            return (0, 0, 0.0);
        }

        let usage = self.parse_bytes(parts[0]);
        let limit = self.parse_bytes(parts[1]);
        let percent = if limit > 0 {
            (usage as f64 / limit as f64) * 100.0
        } else {
            0.0
        };

        (usage, limit, percent)
    }

    fn parse_network(&self, net_str: &str) -> (u64, u64) {
        let parts: Vec<&str> = net_str.split('/').map(|s| s.trim()).collect();
        if parts.len() != 2 {
            return (0, 0);
        }

        (self.parse_bytes(parts[0]), self.parse_bytes(parts[1]))
    }

    fn parse_block_io(&self, block_str: &str) -> (u64, u64) {
        let parts: Vec<&str> = block_str.split('/').map(|s| s.trim()).collect();
        if parts.len() != 2 {
            return (0, 0);
        }

        (self.parse_bytes(parts[0]), self.parse_bytes(parts[1]))
    }

    fn parse_bytes(&self, size_str: &str) -> u64 {
        let size_str = size_str.trim();
        
        let (num_str, multiplier) = if size_str.ends_with("GiB") || size_str.ends_with("GB") {
            (size_str.trim_end_matches("GiB").trim_end_matches("GB"), 1_073_741_824u64)
        } else if size_str.ends_with("MiB") || size_str.ends_with("MB") {
            (size_str.trim_end_matches("MiB").trim_end_matches("MB"), 1_048_576u64)
        } else if size_str.ends_with("KiB") || size_str.ends_with("KB") || size_str.ends_with("kB") {
            (size_str.trim_end_matches("KiB").trim_end_matches("KB").trim_end_matches("kB"), 1_024u64)
        } else if size_str.ends_with("B") {
            (size_str.trim_end_matches("B"), 1u64)
        } else {
            (size_str, 1u64)
        };

        num_str.parse::<f64>().unwrap_or(0.0) as u64 * multiplier
    }

    fn parse_uptime(&self, status: &str) -> u64 {
        // Status examples: "Up 2 hours", "Up 5 minutes", "Exited (0) 3 days ago"
        if !status.starts_with("Up") {
            return 0;
        }

        let parts: Vec<&str> = status.split_whitespace().collect();
        if parts.len() < 3 {
            return 0;
        }

        let value = parts[1].parse::<u64>().unwrap_or(0);
        let unit = parts[2];

        match unit {
            "second" | "seconds" => value,
            "minute" | "minutes" => value * 60,
            "hour" | "hours" => value * 3600,
            "day" | "days" => value * 86400,
            "week" | "weeks" => value * 604800,
            _ => 0,
        }
    }

    fn parse_docker_timestamp(&self, timestamp: &str) -> String {
        // Docker format: "2025-12-01 11:52:41 +0000 UTC" or "2025-12-01 11:52:41.123456 +0000 UTC"
        // ClickHouse format: "2025-12-01 11:52:41"
        
        // Split by space and take first two parts (date and time)
        let parts: Vec<&str> = timestamp.split_whitespace().collect();
        if parts.len() >= 2 {
            // Take date and time, ignore timezone
            let date = parts[0];
            let time = parts[1].split('.').next().unwrap_or(parts[1]); // Remove microseconds if present
            format!("{} {}", date, time)
        } else {
            // Fallback: use current time if parsing fails
            chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
        }
    }

    fn get_restart_count(&self, container_id: &str) -> Result<u32, Box<dyn std::error::Error>> {
        let inspect_output = Command::new(&self.docker_path)
            .args(&["inspect", container_id, "--format", "{{.RestartCount}}"])
            .output()?;

        if !inspect_output.status.success() {
            return Ok(0);
        }

        let count_str = String::from_utf8_lossy(&inspect_output.stdout);
        Ok(count_str.trim().parse::<u32>().unwrap_or(0))
    }

    fn normalize_status(&self, status: &str) -> String {
        if status.starts_with("Up") {
            "running".to_string()
        } else if status.contains("Exited") {
            "exited".to_string()
        } else if status.contains("Restarting") {
            "restarting".to_string()
        } else if status.contains("Paused") {
            "paused".to_string()
        } else if status.contains("Dead") {
            "dead".to_string()
        } else {
            "unknown".to_string()
        }
    }

    async fn send_to_clickhouse(&self, containers: &[serde_json::Value]) 
        -> Result<(), Box<dyn std::error::Error>> {
        
        let client = reqwest::Client::new();
        let timestamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string();

        for container in containers {
            let query = format!(
                "INSERT INTO docker_containers FORMAT JSONEachRow",
            );

            let mut data = container.clone();
            if let Some(obj) = data.as_object_mut() {
                obj.insert("timestamp".to_string(), json!(timestamp));
            }

            let response = client
                .post(&self.clickhouse_url)
                .query(&[("query", query)])
                .json(&data)
                .send()
                .await?;

            if !response.status().is_success() {
                let status = response.status();
                let body = response.text().await.unwrap_or_else(|_| "Unable to read response".to_string());
                error!(
                    "Failed to send container stats to ClickHouse: {} - Response: {}", 
                    status, 
                    body
                );
            }
        }

        Ok(())
    }
}
