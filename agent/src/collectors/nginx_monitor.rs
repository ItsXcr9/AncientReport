//! NGINX Container Monitor
//! Collects metrics from NGINX containers using stub_status module or access logs

use std::collections::HashMap;
use std::process::Command;
use tracing::{info, warn, error, debug};

pub struct NginxMonitor {
    hostname: String,
    clickhouse_url: String,
    http_client: reqwest::Client,
}

#[derive(Debug, Clone, Default)]
pub struct NginxMetrics {
    pub container_id: String,
    pub container_name: String,
    // Connection metrics (from stub_status)
    pub active_connections: i64,
    pub reading: i64,
    pub writing: i64,
    pub waiting: i64,
    pub accepts: i64,
    pub handled: i64,
    pub total_requests: i64,
    // Request metrics (from access logs)
    pub requests_1m: i64,
    pub status_2xx: i64,
    pub status_3xx: i64,
    pub status_4xx: i64,
    pub status_5xx: i64,
    pub avg_response_time_ms: f64,
    pub bytes_sent: i64,
}

impl NginxMonitor {
    pub fn new(hostname: String, clickhouse_url: String) -> Self {
        Self { 
            hostname, 
            clickhouse_url,
            http_client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .expect("Failed to create HTTP client"),
        }
    }

    /// Detect NGINX containers
    fn detect_nginx_containers(&self) -> Vec<(String, String)> {
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
                            if image.contains("nginx") {
                                return Some((parts[0].to_string(), parts[1].to_string()));
                            }
                        }
                        None
                    })
                    .collect()
            }
            Err(e) => {
                warn!("Failed to detect NGINX containers: {}", e);
                vec![]
            }
        }
    }

    /// Get stub_status from NGINX container
    fn get_stub_status(&self, container_id: &str) -> Option<String> {
        let endpoints = [
            "http://localhost/nginx_status",
            "http://localhost/status",
            "http://127.0.0.1/nginx_status",
            "http://127.0.0.1:80/nginx_status",
            "http://localhost:8080/nginx_status",
        ];

        for endpoint in &endpoints {
            let output = Command::new("docker")
                .args(["exec", container_id, "curl", "-s", "--max-time", "2", endpoint])
                .output();

            if let Ok(out) = output {
                let stdout = String::from_utf8_lossy(&out.stdout);
                if stdout.contains("Active connections") {
                    return Some(stdout.to_string());
                }
            }
        }

        // Try wget if curl not available
        for endpoint in &endpoints {
            let output = Command::new("docker")
                .args(["exec", container_id, "wget", "-q", "-O", "-", "-T", "2", endpoint])
                .output();

            if let Ok(out) = output {
                let stdout = String::from_utf8_lossy(&out.stdout);
                if stdout.contains("Active connections") {
                    return Some(stdout.to_string());
                }
            }
        }

        None
    }

    /// Parse stub_status output
    fn parse_stub_status(&self, status: &str, metrics: &mut NginxMetrics) {
        for line in status.lines() {
            let line = line.trim();
            
            // Parse "Active connections: 123"
            if line.starts_with("Active connections:") {
                if let Some(val) = line.split(':').nth(1) {
                    metrics.active_connections = val.trim().parse().unwrap_or(0);
                }
            }
            
            // Parse numeric line " 123 456 789"
            if line.chars().next().map(|c| c.is_ascii_digit()).unwrap_or(false) {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 3 {
                    metrics.accepts = parts[0].parse().unwrap_or(0);
                    metrics.handled = parts[1].parse().unwrap_or(0);
                    metrics.total_requests = parts[2].parse().unwrap_or(0);
                }
            }
            
            // Parse "Reading: 1 Writing: 2 Waiting: 3"
            if line.starts_with("Reading:") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                for (i, part) in parts.iter().enumerate() {
                    match *part {
                        "Reading:" => metrics.reading = parts.get(i + 1).and_then(|v| v.parse().ok()).unwrap_or(0),
                        "Writing:" => metrics.writing = parts.get(i + 1).and_then(|v| v.parse().ok()).unwrap_or(0),
                        "Waiting:" => metrics.waiting = parts.get(i + 1).and_then(|v| v.parse().ok()).unwrap_or(0),
                        _ => {}
                    }
                }
            }
        }
    }

    /// Get access log metrics from container
    fn get_access_log_metrics(&self, container_id: &str) -> Option<NginxMetrics> {
        // Use docker logs directly - most containerized nginx writes access logs to stdout
        let output = Command::new("docker")
            .args(["logs", "--tail", "500", container_id])
            .output();

        if let Ok(out) = output {
            // Combine stdout and stderr as nginx may write access logs to either
            let stdout = String::from_utf8_lossy(&out.stdout);
            let stderr = String::from_utf8_lossy(&out.stderr);
            let combined = format!("{}\n{}", stdout, stderr);
            
            let line_count = combined.lines().count();
            info!("Docker logs for {}: {} lines retrieved", container_id, line_count);
            
            if let Some(parsed) = self.parse_access_log_text(&combined) {
                return Some(parsed);
            } else {
                info!("No HTTP access log entries found in docker logs for {}", container_id);
            }
        } else {
            warn!("Failed to get docker logs for container {}", container_id);
        }

        None
    }


    /// Parse access log text and extract metrics
    fn parse_access_log_text(&self, logs: &str) -> Option<NginxMetrics> {
        let mut metrics = NginxMetrics::default();
        let mut bytes_total = 0i64;

        for line in logs.lines() {
            // Standard NGINX combined log format:
            // IP - - [timestamp] "METHOD URL HTTP/x.x" STATUS BYTES "referer" "user-agent" ...
            // Example: 127.0.0.1 - - [13/Dec/2025:09:33:23 +0000] "GET /nginx_status HTTP/1.1" 404 153 "-" "Wget" "-"
            
            // Skip if doesn't look like an access log line
            if !line.contains(']') || !line.contains('"') {
                continue;
            }

            // Find the closing bracket which ends the timestamp
            if let Some(bracket_pos) = line.find(']') {
                let after_timestamp = &line[bracket_pos + 1..];
                
                // Split the rest and find the status code and bytes
                // Expected: "METHOD URL HTTP/x.x" STATUS BYTES ...
                let parts: Vec<&str> = after_timestamp.split('"').collect();
                
                // parts[0] = space before request
                // parts[1] = request (e.g., "GET /path HTTP/1.1")
                // parts[2] = after request (e.g., " 404 153 ")
                
                if parts.len() >= 3 {
                    // Check if this is actually an HTTP request
                    if parts[1].contains("HTTP/") {
                        let after_request: Vec<&str> = parts[2].trim().split_whitespace().collect();
                        
                        if !after_request.is_empty() {
                            // First element should be status code
                            if let Ok(status) = after_request[0].parse::<i32>() {
                                metrics.requests_1m += 1;
                                
                                match status {
                                    200..=299 => metrics.status_2xx += 1,
                                    300..=399 => metrics.status_3xx += 1,
                                    400..=499 => metrics.status_4xx += 1,
                                    500..=599 => metrics.status_5xx += 1,
                                    _ => {}
                                }
                                
                                // Second element should be bytes
                                if after_request.len() > 1 {
                                    if let Ok(bytes) = after_request[1].parse::<i64>() {
                                        bytes_total += bytes;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        metrics.bytes_sent = bytes_total;
        
        if metrics.requests_1m > 0 {
            info!("Parsed {} requests from access logs (2xx={}, 4xx={}, 5xx={})", 
                metrics.requests_1m, metrics.status_2xx, metrics.status_4xx, metrics.status_5xx);
            Some(metrics)
        } else {
            None
        }
    }

    /// Collect metrics from a container
    fn collect_container_metrics(&self, container_id: &str, container_name: &str) -> Result<NginxMetrics, Box<dyn std::error::Error + Send + Sync>> {
        let mut metrics = NginxMetrics::default();
        metrics.container_id = container_id.to_string();
        metrics.container_name = container_name.to_string();

        let mut has_data = false;

        // Try stub_status first (preferred)
        if let Some(status) = self.get_stub_status(container_id) {
            self.parse_stub_status(&status, &mut metrics);
            has_data = true;
            debug!("Got stub_status for {}", container_name);
        }

        // Also try access logs (supplement or fallback)
        if let Some(log_metrics) = self.get_access_log_metrics(container_id) {
            metrics.requests_1m = log_metrics.requests_1m;
            metrics.status_2xx = log_metrics.status_2xx;
            metrics.status_3xx = log_metrics.status_3xx;
            metrics.status_4xx = log_metrics.status_4xx;
            metrics.status_5xx = log_metrics.status_5xx;
            metrics.bytes_sent = log_metrics.bytes_sent;
            metrics.avg_response_time_ms = log_metrics.avg_response_time_ms;
            has_data = true;
            debug!("Got access log metrics for {}: {} requests", container_name, log_metrics.requests_1m);
        }

        if has_data {
            Ok(metrics)
        } else {
            Err("No metrics available (no stub_status or access logs)".into())
        }
    }

    /// Send metrics to ClickHouse
    async fn send_to_clickhouse(&self, metrics: &NginxMetrics) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        
        // Send all available metrics
        let mut values = Vec::new();
        
        // Connection metrics (from stub_status)
        if metrics.active_connections > 0 || metrics.total_requests > 0 {
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'active_connections', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.active_connections
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'reading', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.reading
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'writing', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.writing
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'waiting', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.waiting
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'accepts', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.accepts
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'handled', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.handled
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'total_requests', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.total_requests
            ));
        }

        // Request metrics (from access logs)
        if metrics.requests_1m > 0 {
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'requests_1m', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.requests_1m
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'status_2xx', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.status_2xx
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'status_3xx', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.status_3xx
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'status_4xx', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.status_4xx
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'status_5xx', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.status_5xx
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'bytes_sent', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.bytes_sent
            ));
            values.push(format!(
                "(now(), '{}', '{}', '{}', 'avg_response_time_ms', {})",
                self.hostname, metrics.container_id, metrics.container_name, metrics.avg_response_time_ms
            ));
        }

        if values.is_empty() {
            return Ok(());
        }

        let query = format!(
            "INSERT INTO AncientReport.nginx_metrics (timestamp, hostname, container_id, container_name, metric_name, value) VALUES {}",
            values.join(", ")
        );

        let response = self.http_client
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
        let containers = self.detect_nginx_containers();
        
        if containers.is_empty() {
            debug!("No NGINX containers found");
            return Ok(());
        }

        info!("Found {} NGINX container(s)", containers.len());

        for (container_id, container_name) in containers {
            match self.collect_container_metrics(&container_id, &container_name) {
                Ok(metrics) => {
                    if let Err(e) = self.send_to_clickhouse(&metrics).await {
                        error!("Failed to send NGINX metrics: {}", e);
                    } else {
                        info!("Sent NGINX metrics for container: {} (requests_1m={}, 2xx={}, 4xx={}, 5xx={})", 
                            container_name, metrics.requests_1m, metrics.status_2xx, metrics.status_4xx, metrics.status_5xx);
                    }
                }
                Err(e) => {
                    debug!("Could not collect NGINX metrics from {}: {}", container_name, e);
                }
            }
        }

        Ok(())
    }
}
