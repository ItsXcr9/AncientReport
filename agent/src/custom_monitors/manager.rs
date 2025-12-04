// Custom Monitor Manager for AncientReport V3
// Orchestrates all custom monitors, fetches configs, and publishes results

use anyhow::Result;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{mpsc, RwLock};
use tokio::time::interval;
use tracing::{info, warn, error, debug};

use super::types::{CustomMonitorConfig, MonitorResult, MonitorType};
use super::port_monitor::PortMonitor;
use super::http_monitor::HttpMonitor;
use crate::aggregator::Metric;

/// Manages all custom monitors and their lifecycle
pub struct CustomMonitorManager {
    hostname: String,
    metrics_tx: mpsc::Sender<Metric>,
    monitors: Arc<RwLock<HashMap<String, MonitorInstance>>>,
    api_url: Option<String>,
    clickhouse_url: String,
}

enum MonitorInstance {
    Port(PortMonitor),
    Http(HttpMonitor),
}

impl CustomMonitorManager {
    pub fn new(
        hostname: String,
        metrics_tx: mpsc::Sender<Metric>,
        clickhouse_url: String,
        api_url: Option<String>,
    ) -> Self {
        Self {
            hostname,
            metrics_tx,
            monitors: Arc::new(RwLock::new(HashMap::new())),
            api_url,
            clickhouse_url,
        }
    }

    /// Start the monitor manager
    pub async fn start(self) -> Result<()> {
        info!("🔍 Starting Custom Monitor Manager");

        // Spawn config refresh task
        let monitors_clone = self.monitors.clone();
        let hostname_clone = self.hostname.clone();
        let api_url_clone = self.api_url.clone();
        
        tokio::spawn(async move {
            let mut refresh_interval = interval(Duration::from_secs(60));
            loop {
                refresh_interval.tick().await;
                if let Err(e) = Self::refresh_configs(
                    &monitors_clone,
                    &hostname_clone,
                    api_url_clone.as_deref(),
                ).await {
                    warn!("Failed to refresh monitor configs: {}", e);
                }
            }
        });

        // Main monitoring loop
        let mut check_interval = interval(Duration::from_secs(10));
        loop {
            check_interval.tick().await;
            
            let monitors = self.monitors.read().await;
            for (name, monitor) in monitors.iter() {
                let result = match monitor {
                    MonitorInstance::Port(m) => m.check().await,
                    MonitorInstance::Http(m) => m.check().await,
                };

                // Convert to metric and send
                if let Err(e) = self.send_result(&result).await {
                    error!("Failed to send monitor result for {}: {}", name, e);
                }

                // Also store in ClickHouse directly for custom_monitor_results table
                if let Err(e) = self.store_result(&result).await {
                    debug!("Failed to store monitor result: {}", e);
                }
            }
        }
    }

    /// Refresh monitor configurations from API or ClickHouse
    async fn refresh_configs(
        monitors: &Arc<RwLock<HashMap<String, MonitorInstance>>>,
        hostname: &str,
        api_url: Option<&str>,
    ) -> Result<()> {
        // Try to fetch from API first
        if let Some(url) = api_url {
            match Self::fetch_configs_from_api(url).await {
                Ok(configs) => {
                    let mut monitors_write = monitors.write().await;
                    for config in configs {
                        if !config.enabled {
                            monitors_write.remove(&config.name);
                            continue;
                        }
                        
                        match Self::create_monitor_instance(&config, hostname) {
                            Ok(instance) => {
                                monitors_write.insert(config.name.clone(), instance);
                            }
                            Err(e) => {
                                warn!("Failed to create monitor {}: {}", config.name, e);
                            }
                        }
                    }
                    return Ok(());
                }
                Err(e) => {
                    debug!("Failed to fetch from API, will try ClickHouse: {}", e);
                }
            }
        }

        Ok(())
    }

    async fn fetch_configs_from_api(api_url: &str) -> Result<Vec<CustomMonitorConfig>> {
        let client = reqwest::Client::new();
        let url = format!("{}/api/v3/monitors", api_url);
        
        let response = client
            .get(&url)
            .timeout(Duration::from_secs(5))
            .send()
            .await?;

        let configs: Vec<CustomMonitorConfig> = response.json().await?;
        Ok(configs)
    }

    fn create_monitor_instance(config: &CustomMonitorConfig, hostname: &str) -> Result<MonitorInstance> {
        match config.monitor_type {
            MonitorType::Port => {
                let port_config = serde_json::from_value(config.config.clone())?;
                Ok(MonitorInstance::Port(PortMonitor::new(port_config, hostname.to_string())))
            }
            MonitorType::Http => {
                let http_config = serde_json::from_value(config.config.clone())?;
                Ok(MonitorInstance::Http(HttpMonitor::new(http_config, hostname.to_string())?))
            }
            _ => Err(anyhow::anyhow!("Monitor type {:?} not yet implemented", config.monitor_type)),
        }
    }

    async fn send_result(&self, result: &MonitorResult) -> Result<()> {
        let metric = Metric {
            timestamp: result.timestamp,
            hostname: self.hostname.clone(),
            metric_type: "custom_monitor".to_string(),
            metric_name: format!("monitor_{}", result.monitor_name),
            value: match result.status {
                super::types::MonitorStatus::Ok => 1.0,
                super::types::MonitorStatus::Warning => 0.5,
                super::types::MonitorStatus::Critical => 0.0,
                super::types::MonitorStatus::Unknown => -1.0,
            },
            tags: {
                let mut tags = std::collections::HashMap::new();
                tags.insert("monitor_id".to_string(), result.monitor_id.clone());
                tags.insert("status".to_string(), result.status.to_string());
                tags.insert("latency_ms".to_string(), result.latency_ms.to_string());
                if let Some(ref error) = result.error {
                    tags.insert("error".to_string(), error.clone());
                }
                tags
            },
        };

        self.metrics_tx.send(metric).await?;
        Ok(())
    }

    async fn store_result(&self, result: &MonitorResult) -> Result<()> {
        let client = reqwest::Client::new();
        
        let query = format!(
            r#"INSERT INTO custom_monitor_results 
               (timestamp, monitor_id, monitor_name, hostname, status, latency_ms, response, error) 
               VALUES (now(), '{}', '{}', '{}', '{}', {}, '{}', '{}')"#,
            result.monitor_id,
            result.monitor_name,
            self.hostname,
            result.status.to_string(),
            result.latency_ms,
            result.response.as_deref().unwrap_or("").replace('\'', "''"),
            result.error.as_deref().unwrap_or("").replace('\'', "''"),
        );

        client
            .post(&self.clickhouse_url)
            .body(query)
            .send()
            .await?;

        Ok(())
    }

    /// Add a monitor programmatically (for local config)
    pub async fn add_port_monitor(&self, config: super::types::PortMonitorConfig) {
        let mut monitors = self.monitors.write().await;
        let instance = PortMonitor::new(config.clone(), self.hostname.clone());
        monitors.insert(config.name.clone(), MonitorInstance::Port(instance));
        info!("Added port monitor: {}", config.name);
    }

    /// Add an HTTP monitor programmatically
    pub async fn add_http_monitor(&self, config: super::types::HttpMonitorConfig) -> Result<()> {
        let mut monitors = self.monitors.write().await;
        let instance = HttpMonitor::new(config.clone(), self.hostname.clone())?;
        monitors.insert(config.name.clone(), MonitorInstance::Http(instance));
        info!("Added HTTP monitor: {}", config.name);
        Ok(())
    }

    /// Remove a monitor
    pub async fn remove_monitor(&self, name: &str) {
        let mut monitors = self.monitors.write().await;
        if monitors.remove(name).is_some() {
            info!("Removed monitor: {}", name);
        }
    }

    /// Get count of active monitors
    pub async fn monitor_count(&self) -> usize {
        self.monitors.read().await.len()
    }
}
