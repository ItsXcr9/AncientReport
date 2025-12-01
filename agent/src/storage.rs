use anyhow::{Context, Result};
use reqwest::Client;
use serde::Serialize;
use std::time::Duration;
use tracing::{debug, error, info};

#[derive(Debug, Clone, Serialize)]
pub struct MetricRow {
    pub timestamp: String,
    pub hostname: String,
    pub metric_type: String,
    pub metric_name: String,
    pub value: f64,
    pub tags: String, // JSON encoded
}

pub struct ClickHouseStorage {
    url: String,
    database: String,
    client: Client,
    username: Option<String>,
    password: Option<String>,
}

impl ClickHouseStorage {
    pub fn new(url: &str, database: &str, username: Option<String>, password: Option<String>) -> Self {
        let client_builder = Client::builder()
            .timeout(Duration::from_secs(10));
            
        // Credentials will be added per-request using X-ClickHouse-User and X-ClickHouse-Key headers.
        // We store them here for later use.
        if let Some(u) = &username {
            debug!("ClickHouse credentials provided for user: {}", u);
        }
        
        let client = client_builder
            .build()
            .expect("Failed to create HTTP client");
        
        info!("ClickHouse storage initialized at {} (database: {})", url, database);
        
        Self {
            url: url.to_string(),
            database: database.to_string(),
            client,
            username: username,
            password: password,
        }
    }

    /// Send a batch of metrics to ClickHouse
    pub async fn send_metrics(&self, metrics: &[MetricRow]) -> Result<()> {
        if metrics.is_empty() {
            return Ok(());
        }

        let query = self.build_insert_query(metrics);
        
        debug!("Sending {} metrics to ClickHouse", metrics.len());
        
        // Retry logic: 3 attempts with exponential backoff
        for attempt in 1..=3 {
            match self.execute_query(&query).await {
                Ok(_) => {
                    info!("✓ Successfully inserted {} metrics", metrics.len());
                    return Ok(());
                }
                Err(e) => {
                    if attempt < 3 {
                        let backoff = Duration::from_millis(100 * 2u64.pow(attempt - 1));
                        error!("Failed to insert metrics (attempt {}): {}. Retrying in {:?}", attempt, e, backoff);
                        tokio::time::sleep(backoff).await;
                    } else {
                        error!("Failed to insert metrics after 3 attempts: {}", e);
                        return Err(e);
                    }
                }
            }
        }

        Ok(())
    }

    fn build_insert_query(&self, metrics: &[MetricRow]) -> String {
        let mut query = String::from("INSERT INTO metrics (timestamp, hostname, metric_type, metric_name, value, tags) VALUES ");
        
        for (i, metric) in metrics.iter().enumerate() {
            if i > 0 {
                query.push_str(", ");
            }
            query.push_str(&format!(
                "({}, '{}', '{}', '{}', {}, {})",
                metric.timestamp,
                metric.hostname,
                metric.metric_type,
                metric.metric_name,
                metric.value,
                metric.tags  // No quotes - it's already a Map literal like {'key': 'value'}
            ));
        }
        
        query
    }

    async fn execute_query(&self, query: &str) -> Result<()> {
        // Build URL with database parameter
        let url_with_db = if self.url.contains('?') {
            format!("{}&database={}", self.url, self.database)
        } else {
            format!("{}?database={}", self.url, self.database)
        };
        
        let mut request = self.client.post(&url_with_db);
        
        // Add auth headers if credentials provided
        if let (Some(u), Some(p)) = (&self.username, &self.password) {
            request = request.header("X-ClickHouse-User", u);
            request = request.header("X-ClickHouse-Key", p);
        }

        let response = request
            .body(query.to_string())
            .send()
            .await
            .context("Failed to send request to ClickHouse")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_else(|_| "Unknown error".to_string());
            anyhow::bail!("ClickHouse returned error {}: {}", status, error_text);
        }

        Ok(())
    }
}
