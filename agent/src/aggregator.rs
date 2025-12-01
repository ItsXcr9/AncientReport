use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;
use tokio::time::interval;
use tracing::{error, info};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Metric {
    pub timestamp: i64,
    pub hostname: String,
    pub metric_type: String,
    pub metric_name: String,
    pub value: f64,
    pub tags: HashMap<String, String>,
}

pub struct MetricAggregator {
    clickhouse_url: String,
    clickhouse_database: String,
    clickhouse_user: Option<String>,
    clickhouse_pass: Option<String>,
    buffer: Vec<Metric>,
    flush_interval: Duration,
    metrics_rx: tokio::sync::mpsc::Receiver<Metric>,
}

impl MetricAggregator {
    pub fn new(
        clickhouse_url: &str,
        clickhouse_database: &str,
        clickhouse_user: Option<String>,
        clickhouse_pass: Option<String>,
        flush_interval: Duration,
        metrics_rx: tokio::sync::mpsc::Receiver<Metric>,
    ) -> Self {
        Self {
            clickhouse_url: clickhouse_url.to_string(),
            clickhouse_database: clickhouse_database.to_string(),
            clickhouse_user,
            clickhouse_pass,
            buffer: Vec::with_capacity(10000),
            flush_interval,
            metrics_rx,
        }
    }

    pub async fn start(&mut self) {
        let mut ticker = interval(self.flush_interval);

        loop {
            tokio::select! {
                _ = ticker.tick() => {
                    if let Err(e) = self.flush_metrics().await {
                        error!("Failed to flush metrics: {}", e);
                    }
                }
                Some(metric) = self.metrics_rx.recv() => {
                    self.buffer.push(metric);
                    
                    // Auto-flush if buffer is getting too large
                    if self.buffer.len() >= 1000 {
                        if let Err(e) = self.flush_metrics().await {
                            error!("Failed to auto-flush metrics: {}", e);
                        }
                    }
                }
            }
        }
    }

    async fn flush_metrics(&mut self) -> Result<()> {
        if self.buffer.is_empty() {
            return Ok(());
        }

        let metrics_count = self.buffer.len();
        info!("Flushing {} metrics to ClickHouse...", metrics_count);

        // Convert metrics to storage format
        use crate::storage::{ClickHouseStorage, MetricRow};
        
        let storage = ClickHouseStorage::new(
            &self.clickhouse_url,
            &self.clickhouse_database,
            self.clickhouse_user.clone(),
            self.clickhouse_pass.clone()
        );
        let rows: Vec<MetricRow> = self.buffer.iter().map(|m| {
        let rows: Vec<MetricRow> = self.buffer.iter().map(|m| {
            MetricRow {
                timestamp: m.timestamp,
                hostname: m.hostname.clone(),
                metric_type: m.metric_type.clone(),
                metric_name: m.metric_name.clone(),
                value: m.value,
                tags: format_tags_for_clickhouse(&m.tags),
            }
        }).collect();

        // Send to ClickHouse
        storage.send_metrics(&rows).await?;
        
        // Clear buffer after successful send
        self.buffer.clear();

        info!("✓ Flushed {} metrics", metrics_count);
        Ok(())
    }
}

/// Format HashMap as ClickHouse Map literal: {'key': 'value'}
fn format_tags_for_clickhouse(tags: &HashMap<String, String>) -> String {
    if tags.is_empty() {
        return "{}".to_string();
    }
    let pairs: Vec<String> = tags.iter()
        .map(|(k, v)| format!("'{}': '{}'", k.replace('\'', "''"), v.replace('\'', "''")))
        .collect();
    format!("{{{}}}", pairs.join(", "))
}
