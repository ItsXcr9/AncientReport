// HTTP Monitor for AncientReport V3
// HTTP/HTTPS endpoint health checks with status, body, and latency validation

use anyhow::Result;
use reqwest::{Client, Method, Response};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use tracing::{debug, warn};

use super::types::{HttpMonitorConfig, MonitorResult, MonitorStatus};

/// HTTP monitor that checks endpoint availability and validates responses
pub struct HttpMonitor {
    config: HttpMonitorConfig,
    client: Client,
    hostname: String,
}

impl HttpMonitor {
    pub fn new(config: HttpMonitorConfig, hostname: String) -> Result<Self> {
        let client = Client::builder()
            .timeout(Duration::from_millis(config.timeout_ms))
            .danger_accept_invalid_certs(false)
            .build()?;

        Ok(Self {
            config,
            client,
            hostname,
        })
    }

    /// Perform an HTTP check and return the result
    pub async fn check(&self) -> MonitorResult {
        let start = Instant::now();

        match self.execute_request().await {
            Ok((response, body)) => {
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                let status_code = response.status().as_u16();

                // Check expected status
                if let Some(expected_status) = self.config.expected_status {
                    if status_code != expected_status {
                        return MonitorResult {
                            monitor_id: self.config.name.clone(),
                            monitor_name: self.config.name.clone(),
                            status: MonitorStatus::Critical,
                            latency_ms,
                            response: Some(format!("Status: {}", status_code)),
                            error: Some(format!(
                                "Expected status {}, got {}",
                                expected_status, status_code
                            )),
                            timestamp: chrono::Utc::now().timestamp(),
                        };
                    }
                }

                // Check expected body content
                if let Some(expected_body) = &self.config.expected_body_contains {
                    if !body.contains(expected_body) {
                        return MonitorResult {
                            monitor_id: self.config.name.clone(),
                            monitor_name: self.config.name.clone(),
                            status: MonitorStatus::Critical,
                            latency_ms,
                            response: Some(body.chars().take(200).collect()),
                            error: Some(format!(
                                "Expected body to contain '{}'",
                                expected_body
                            )),
                            timestamp: chrono::Utc::now().timestamp(),
                        };
                    }
                }

                debug!(
                    "HTTP check {} succeeded: {} {}ms",
                    self.config.url, status_code, latency_ms
                );

                MonitorResult {
                    monitor_id: self.config.name.clone(),
                    monitor_name: self.config.name.clone(),
                    status: if response.status().is_success() {
                        MonitorStatus::Ok
                    } else if response.status().is_client_error() {
                        MonitorStatus::Warning
                    } else {
                        MonitorStatus::Critical
                    },
                    latency_ms,
                    response: Some(format!("Status: {}, Size: {} bytes", status_code, body.len())),
                    error: None,
                    timestamp: chrono::Utc::now().timestamp(),
                }
            }
            Err(e) => {
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                warn!("HTTP check {} failed: {}", self.config.url, e);

                MonitorResult {
                    monitor_id: self.config.name.clone(),
                    monitor_name: self.config.name.clone(),
                    status: MonitorStatus::Critical,
                    latency_ms,
                    response: None,
                    error: Some(e.to_string()),
                    timestamp: chrono::Utc::now().timestamp(),
                }
            }
        }
    }

    async fn execute_request(&self) -> Result<(Response, String)> {
        let method: Method = self.config.method.parse()
            .unwrap_or(Method::GET);

        let mut request = self.client.request(method, &self.config.url);

        // Add headers
        for (key, value) in &self.config.headers {
            request = request.header(key, value);
        }

        // Add body if present
        if let Some(body) = &self.config.body {
            request = request.body(body.clone());
        }

        let response = request.send().await?;
        let body = response.text().await?;

        // Re-create response for status check (since we consumed it for body)
        let response = self.client
            .request(self.config.method.parse().unwrap_or(Method::GET), &self.config.url)
            .send()
            .await?;

        Ok((response, body))
    }

    /// Check SSL certificate expiration
    pub async fn check_certificate(&self) -> Option<CertificateInfo> {
        // Note: Full certificate checking requires native-tls or rustls features
        // This is a simplified version
        if self.config.url.starts_with("https://") {
            // Would need to establish TLS connection and inspect certificate
            // For now, return None - implement with rustls in production
            None
        } else {
            None
        }
    }

    pub fn config(&self) -> &HttpMonitorConfig {
        &self.config
    }

    pub fn name(&self) -> &str {
        &self.config.name
    }
}

#[derive(Debug, Clone)]
pub struct CertificateInfo {
    pub subject: String,
    pub issuer: String,
    pub not_before: chrono::DateTime<chrono::Utc>,
    pub not_after: chrono::DateTime<chrono::Utc>,
    pub days_until_expiry: i64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_http_monitor_google() {
        let config = HttpMonitorConfig {
            name: "test-http".to_string(),
            url: "https://www.google.com".to_string(),
            method: "GET".to_string(),
            headers: HashMap::new(),
            body: None,
            timeout_ms: 5000,
            expected_status: Some(200),
            expected_body_contains: None,
            interval_seconds: 60,
        };

        let monitor = HttpMonitor::new(config, "test-host".to_string()).unwrap();
        let result = monitor.check().await;

        println!("HTTP check result: {:?}", result);
        assert_eq!(result.status, MonitorStatus::Ok);
    }
}
