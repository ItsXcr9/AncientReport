// Prometheus Scraper for AncientReport Agent
// Scrapes local/remote Prometheus exporters and forwards metrics via NATS
//
// Configuration via environment variables:
//   PROMETHEUS_TARGETS: Comma-separated list of endpoints to scrape (optional if auto-discovery enabled)
//   PROMETHEUS_SCRAPE_INTERVAL: Scrape interval in seconds (default: 30)
//   PROMETHEUS_ENABLED: Enable/disable scraping (default: false)
//   PROMETHEUS_AUTO_DISCOVER: Enable auto-discovery of exporters (default: true)
//   PROMETHEUS_DISCOVER_INTERVAL: Discovery interval in seconds (default: 300)

use reqwest::Client;
use std::collections::{HashMap, HashSet};
use std::process::Command;
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

use crate::aggregator::Metric;

/// Common Prometheus exporter ports to scan
const COMMON_EXPORTER_PORTS: &[(u16, &str)] = &[
    (9100, "node_exporter"),
    (9090, "prometheus"),
    (9104, "mysqld_exporter"),
    (9187, "postgres_exporter"),
    (9121, "redis_exporter"),
    (9308, "kafka_exporter"),
    (9113, "nginx_exporter"),
    (9216, "mongodb_exporter"),
    (9323, "docker_metrics"),
    (8080, "cadvisor"),
    (9115, "blackbox_exporter"),
    (9101, "haproxy_exporter"),
    (9102, "statsd_exporter"),
    (9256, "process_exporter"),
    (9419, "rabbitmq_exporter"),
    (9091, "pushgateway"),
];

/// Prometheus metric types
#[derive(Debug, Clone, PartialEq)]
pub enum MetricType {
    Counter,
    Gauge,
    Histogram,
    Summary,
    Untyped,
}

/// Parsed Prometheus metric
#[derive(Debug, Clone)]
pub struct PrometheusMetric {
    pub name: String,
    pub metric_type: MetricType,
    pub value: f64,
    pub labels: HashMap<String, String>,
    pub help: Option<String>,
}

/// Discovered target info
#[derive(Debug, Clone)]
struct DiscoveredTarget {
    url: String,
    exporter_type: String,
    source: String, // "port_scan", "docker_label", "manual"
}

/// Prometheus Scraper Collector with Auto-Discovery
pub struct PrometheusScraper {
    hostname: String,
    manual_targets: Vec<String>,
    discovered_targets: tokio::sync::RwLock<Vec<DiscoveredTarget>>,
    scrape_interval: Duration,
    discover_interval: Duration,
    client: Client,
    metrics_tx: mpsc::Sender<Metric>,
    enabled: bool,
    auto_discover: bool,
}

impl PrometheusScraper {
    pub fn new(hostname: String, metrics_tx: mpsc::Sender<Metric>) -> Self {
        // Parse configuration from environment
        let manual_targets = std::env::var("PROMETHEUS_TARGETS")
            .unwrap_or_default()
            .split(',')
            .filter(|s| !s.trim().is_empty())
            .map(|s| s.trim().to_string())
            .collect::<Vec<_>>();

        let scrape_interval = std::env::var("PROMETHEUS_SCRAPE_INTERVAL")
            .unwrap_or_else(|_| "30".to_string())
            .parse::<u64>()
            .unwrap_or(30);

        let discover_interval = std::env::var("PROMETHEUS_DISCOVER_INTERVAL")
            .unwrap_or_else(|_| "300".to_string())
            .parse::<u64>()
            .unwrap_or(300);

        let enabled = std::env::var("PROMETHEUS_ENABLED")
            .unwrap_or_else(|_| "false".to_string())
            .to_lowercase() == "true";

        let auto_discover = std::env::var("PROMETHEUS_AUTO_DISCOVER")
            .unwrap_or_else(|_| "true".to_string())
            .to_lowercase() == "true";

        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("Failed to create HTTP client");

        if enabled {
            info!("Prometheus scraper initialized");
            info!("  Manual targets: {}", manual_targets.len());
            info!("  Auto-discovery: {}", if auto_discover { "enabled" } else { "disabled" });
            info!("  Scrape interval: {}s", scrape_interval);
            info!("  Discovery interval: {}s", discover_interval);
        }

        Self {
            hostname,
            manual_targets,
            discovered_targets: tokio::sync::RwLock::new(Vec::new()),
            scrape_interval: Duration::from_secs(scrape_interval),
            discover_interval: Duration::from_secs(discover_interval),
            client,
            metrics_tx,
            enabled,
            auto_discover,
        }
    }

    /// Start the scraping loop
    pub async fn run(&self) {
        if !self.enabled {
            debug!("Prometheus scraper disabled");
            return;
        }

        info!("🔍 Starting Prometheus scraper with auto-discovery");

        // Initial discovery
        if self.auto_discover {
            self.run_discovery().await;
        }

        let mut scrape_interval = tokio::time::interval(self.scrape_interval);
        let mut discover_interval = tokio::time::interval(self.discover_interval);

        loop {
            tokio::select! {
                _ = scrape_interval.tick() => {
                    self.scrape_all_targets().await;
                }
                _ = discover_interval.tick() => {
                    if self.auto_discover {
                        self.run_discovery().await;
                    }
                }
            }
        }
    }

    /// Run auto-discovery for Prometheus exporters
    async fn run_discovery(&self) {
        info!("🔎 Running Prometheus exporter discovery...");
        
        let mut new_targets = Vec::new();

        // 1. Scan common exporter ports on localhost
        let port_targets = self.discover_by_port_scan().await;
        new_targets.extend(port_targets);

        // 2. Check Docker containers for prometheus.io labels
        let docker_targets = self.discover_from_docker_labels().await;
        new_targets.extend(docker_targets);

        // Update discovered targets
        {
            let mut targets = self.discovered_targets.write().await;
            *targets = new_targets;
            info!("✓ Discovery complete: {} exporters found", targets.len());
            for target in targets.iter() {
                info!("  📊 {} ({}) - {}", target.exporter_type, target.source, target.url);
            }
        }
    }

    /// Discover exporters by scanning common ports
    async fn discover_by_port_scan(&self) -> Vec<DiscoveredTarget> {
        let mut targets = Vec::new();

        for (port, exporter_name) in COMMON_EXPORTER_PORTS {
            let url = format!("http://127.0.0.1:{}/metrics", port);
            
            // Quick check if port responds with Prometheus metrics
            match self.client.get(&url).send().await {
                Ok(response) if response.status().is_success() => {
                    // Verify it's actually Prometheus format
                    if let Ok(body) = response.text().await {
                        if body.contains("# HELP") || body.contains("# TYPE") || body.contains("_total") {
                            info!("✓ Found {} on port {} (valid Prometheus format)", exporter_name, port);
                            targets.push(DiscoveredTarget {
                                url,
                                exporter_type: exporter_name.to_string(),
                                source: "port_scan".to_string(),
                            });
                        }
                    }
                }
                Ok(response) => {
                    debug!("Port {} responded with status {}", port, response.status());
                }
                Err(e) => {
                    debug!("Port {} error: {}", port, e);
                }
            }
        }

        targets
    }

    /// Discover exporters from Docker container labels
    async fn discover_from_docker_labels(&self) -> Vec<DiscoveredTarget> {
        let mut targets = Vec::new();

        // Use docker inspect to find containers with prometheus.io labels
        let output = Command::new("docker")
            .args(&[
                "ps", "-q", "--filter", "label=prometheus.io/scrape=true",
            ])
            .output();

        let container_ids = match output {
            Ok(output) if output.status.success() => {
                String::from_utf8_lossy(&output.stdout)
                    .lines()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>()
            }
            _ => return targets,
        };

        for container_id in container_ids {
            // Get container info including labels and network
            let inspect = Command::new("docker")
                .args(&[
                    "inspect",
                    "--format",
                    "{{range $k, $v := .Config.Labels}}{{$k}}={{$v}}\n{{end}}|||{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}|||{{.Name}}",
                    &container_id,
                ])
                .output();

            if let Ok(output) = inspect {
                if output.status.success() {
                    let info = String::from_utf8_lossy(&output.stdout);
                    let parts: Vec<&str> = info.split("|||").collect();
                    
                    if parts.len() >= 3 {
                        let labels_str = parts[0];
                        let ip = parts[1].trim();
                        let name = parts[2].trim().trim_start_matches('/');

                        // Parse labels
                        let mut port = "9090".to_string();
                        let mut path = "/metrics".to_string();

                        for line in labels_str.lines() {
                            if let Some(value) = line.strip_prefix("prometheus.io/port=") {
                                port = value.trim().to_string();
                            }
                            if let Some(value) = line.strip_prefix("prometheus.io/path=") {
                                path = value.trim().to_string();
                            }
                        }

                        // Construct URL - prefer container IP, fallback to localhost with port
                        let url = if !ip.is_empty() {
                            format!("http://{}:{}{}", ip, port, path)
                        } else {
                            format!("http://127.0.0.1:{}{}", port, path)
                        };

                        targets.push(DiscoveredTarget {
                            url,
                            exporter_type: format!("docker:{}", name),
                            source: "docker_label".to_string(),
                        });
                    }
                }
            }
        }

        targets
    }

    /// Scrape all targets (manual + discovered)
    async fn scrape_all_targets(&self) {
        // Collect all unique target URLs
        let mut all_urls: HashSet<String> = HashSet::new();

        // Add manual targets
        for target in &self.manual_targets {
            all_urls.insert(target.clone());
        }

        // Add discovered targets
        {
            let discovered = self.discovered_targets.read().await;
            for target in discovered.iter() {
                all_urls.insert(target.url.clone());
            }
        }

        if all_urls.is_empty() {
            info!("📊 No Prometheus targets to scrape (manual: {}, discovered: 0)", self.manual_targets.len());
            return;
        }

        info!("📊 Scraping {} Prometheus target(s)...", all_urls.len());

        // Scrape all targets concurrently
        let futures: Vec<_> = all_urls.iter()
            .map(|url| self.scrape_target(url))
            .collect();

        let results = futures::future::join_all(futures).await;
        
        let success_count = results.iter().filter(|r| r.is_ok()).count();
        let fail_count = results.iter().filter(|r| r.is_err()).count();
        
        info!("✓ Scrape complete: {} succeeded, {} failed", success_count, fail_count);
    }

    /// Scrape a single Prometheus target
    async fn scrape_target(&self, target: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        info!("  → Scraping: {}", target);

        let response = self.client.get(target).send().await?;
        
        if !response.status().is_success() {
            return Err(format!("HTTP {} from {}", response.status(), target).into());
        }

        let body = response.text().await?;
        let metrics = self.parse_prometheus_text(&body)?;

        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;

        let mut sent_count = 0;
        for metric in metrics {
            // Build tags from labels
            let mut tags = metric.labels.clone();
            tags.insert("source".to_string(), "prometheus".to_string());
            tags.insert("scrape_target".to_string(), target.to_string());
            tags.insert("metric_type".to_string(), format!("{:?}", metric.metric_type).to_lowercase());

            // Determine category based on metric name prefix
            let category = self.categorize_metric(&metric.name);

            let m = Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                category,
                metric.name.clone(),
                metric.value,
                tags,
            );

            if let Err(e) = self.metrics_tx.send(m).await {
                error!("Failed to send metric {}: {}", metric.name, e);
            } else {
                sent_count += 1;
            }
        }

        info!("  ✓ Scraped {} metrics from {}", sent_count, target);
        Ok(())
    }

    /// Parse Prometheus text format
    fn parse_prometheus_text(&self, text: &str) -> Result<Vec<PrometheusMetric>, Box<dyn std::error::Error + Send + Sync>> {
        let mut metrics = Vec::new();
        let mut current_type = MetricType::Untyped;
        let mut current_help: Option<String> = None;
        let mut current_name = String::new();

        for line in text.lines() {
            let line = line.trim();
            
            if line.is_empty() {
                continue;
            }

            if line.starts_with("# HELP ") {
                let parts: Vec<&str> = line[7..].splitn(2, ' ').collect();
                if parts.len() >= 2 {
                    current_name = parts[0].to_string();
                    current_help = Some(parts[1].to_string());
                }
                continue;
            }

            if line.starts_with("# TYPE ") {
                let parts: Vec<&str> = line[7..].splitn(2, ' ').collect();
                if parts.len() >= 2 {
                    current_name = parts[0].to_string();
                    current_type = match parts[1].to_lowercase().as_str() {
                        "counter" => MetricType::Counter,
                        "gauge" => MetricType::Gauge,
                        "histogram" => MetricType::Histogram,
                        "summary" => MetricType::Summary,
                        _ => MetricType::Untyped,
                    };
                }
                continue;
            }

            if line.starts_with('#') {
                continue;
            }

            if let Some(metric) = self.parse_metric_line(line, &current_type, &current_help, &current_name) {
                metrics.push(metric);
            }
        }

        Ok(metrics)
    }

    /// Parse a single metric line
    fn parse_metric_line(
        &self,
        line: &str,
        default_type: &MetricType,
        help: &Option<String>,
        type_name: &str,
    ) -> Option<PrometheusMetric> {
        let (name_labels, value_str) = if let Some(brace_start) = line.find('{') {
            if let Some(brace_end) = line.find('}') {
                let name = line[..brace_start].trim();
                let labels_str = &line[brace_start + 1..brace_end];
                let rest = line[brace_end + 1..].trim();
                let value_part = rest.split_whitespace().next()?;
                
                let labels = self.parse_labels(labels_str);
                (Some((name.to_string(), labels)), value_part.to_string())
            } else {
                return None;
            }
        } else {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 2 {
                let name = parts[0].to_string();
                let value = parts[1].to_string();
                (Some((name, HashMap::new())), value)
            } else {
                return None;
            }
        };

        let (name, labels) = name_labels?;
        let value: f64 = match value_str.parse() {
            Ok(v) => v,
            Err(_) => {
                if value_str == "+Inf" {
                    return None; // Skip infinity
                } else if value_str == "-Inf" {
                    return None;
                } else if value_str == "NaN" {
                    return None;
                } else {
                    return None;
                }
            }
        };

        if value.is_infinite() || value.is_nan() {
            return None;
        }

        let metric_type = if name == type_name || name.starts_with(&format!("{}_", type_name)) {
            default_type.clone()
        } else {
            MetricType::Untyped
        };

        Some(PrometheusMetric {
            name,
            metric_type,
            value,
            labels,
            help: help.clone(),
        })
    }

    /// Parse labels from {key="value",...} format
    fn parse_labels(&self, labels_str: &str) -> HashMap<String, String> {
        let mut labels = HashMap::new();
        let mut in_value = false;
        let mut current_key = String::new();
        let mut current_value = String::new();
        let mut escape_next = false;

        for c in labels_str.chars() {
            if escape_next {
                current_value.push(c);
                escape_next = false;
                continue;
            }

            match c {
                '\\' if in_value => {
                    escape_next = true;
                }
                '"' => {
                    if in_value {
                        labels.insert(current_key.clone(), current_value.clone());
                        current_key.clear();
                        current_value.clear();
                    }
                    in_value = !in_value;
                }
                '=' if !in_value => {}
                ',' if !in_value => {}
                _ => {
                    if in_value {
                        current_value.push(c);
                    } else if c != ' ' && c != ',' && c != '=' {
                        current_key.push(c);
                    }
                }
            }
        }

        labels
    }

    /// Categorize metric based on name prefix
    fn categorize_metric(&self, name: &str) -> String {
        if name.starts_with("node_") {
            "node_exporter".to_string()
        } else if name.starts_with("process_") {
            "process".to_string()
        } else if name.starts_with("go_") {
            "go_runtime".to_string()
        } else if name.starts_with("http_") || name.starts_with("promhttp_") {
            "http".to_string()
        } else if name.starts_with("mysql_") {
            "mysql".to_string()
        } else if name.starts_with("postgres_") || name.starts_with("pg_") {
            "postgresql".to_string()
        } else if name.starts_with("redis_") {
            "redis".to_string()
        } else if name.starts_with("nginx_") {
            "nginx".to_string()
        } else if name.starts_with("kafka_") {
            "kafka".to_string()
        } else if name.starts_with("container_") || name.starts_with("docker_") {
            "docker".to_string()
        } else if name.starts_with("kube_") || name.starts_with("kubernetes_") {
            "kubernetes".to_string()
        } else if name.starts_with("mongodb_") || name.starts_with("mongo_") {
            "mongodb".to_string()
        } else if name.starts_with("rabbitmq_") {
            "rabbitmq".to_string()
        } else if name.starts_with("haproxy_") {
            "haproxy".to_string()
        } else {
            "prometheus".to_string()
        }
    }
}

