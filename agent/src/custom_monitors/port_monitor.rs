// Port Monitor for AncientReport V3
// TCP/UDP port health checks with latency measurement

use anyhow::Result;
use std::net::SocketAddr;
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::time::timeout;
use tracing::{debug, warn};

use super::types::{MonitorResult, MonitorStatus, PortMonitorConfig};

/// Port monitor that checks TCP connectivity and optionally validates responses
pub struct PortMonitor {
    config: PortMonitorConfig,
    hostname: String,
}

impl PortMonitor {
    pub fn new(config: PortMonitorConfig, hostname: String) -> Self {
        Self { config, hostname }
    }

    /// Perform a port check and return the result
    pub async fn check(&self) -> MonitorResult {
        let start = Instant::now();
        let timeout_duration = Duration::from_millis(self.config.timeout_ms);
        
        let addr = format!("{}:{}", self.config.host, self.config.port);
        
        match self.tcp_connect_with_timeout(&addr, timeout_duration).await {
            Ok(mut stream) => {
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                
                // If we need to send data and check response
                if let (Some(send_data), Some(expected)) = 
                    (&self.config.send_data, &self.config.expected_response) 
                {
                    match self.check_response(&mut stream, send_data, expected, timeout_duration).await {
                        Ok(response) => MonitorResult {
                            monitor_id: self.config.name.clone(),
                            monitor_name: self.config.name.clone(),
                            status: MonitorStatus::Ok,
                            latency_ms,
                            response: Some(response),
                            error: None,
                            timestamp: chrono::Utc::now().timestamp(),
                        },
                        Err(e) => MonitorResult {
                            monitor_id: self.config.name.clone(),
                            monitor_name: self.config.name.clone(),
                            status: MonitorStatus::Critical,
                            latency_ms,
                            response: None,
                            error: Some(format!("Response check failed: {}", e)),
                            timestamp: chrono::Utc::now().timestamp(),
                        },
                    }
                } else {
                    // Just TCP connect check
                    debug!("Port {}:{} is open ({}ms)", self.config.host, self.config.port, latency_ms);
                    MonitorResult {
                        monitor_id: self.config.name.clone(),
                        monitor_name: self.config.name.clone(),
                        status: MonitorStatus::Ok,
                        latency_ms,
                        response: Some(format!("Port {} open", self.config.port)),
                        error: None,
                        timestamp: chrono::Utc::now().timestamp(),
                    }
                }
            }
            Err(e) => {
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                warn!("Port {}:{} check failed: {}", self.config.host, self.config.port, e);
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

    async fn tcp_connect_with_timeout(&self, addr: &str, timeout_duration: Duration) -> Result<TcpStream> {
        let addr: SocketAddr = addr.parse()
            .map_err(|e| anyhow::anyhow!("Invalid address {}: {}", addr, e))?;
        
        let stream = timeout(timeout_duration, TcpStream::connect(addr))
            .await
            .map_err(|_| anyhow::anyhow!("Connection timeout after {}ms", self.config.timeout_ms))?
            .map_err(|e| anyhow::anyhow!("Connection failed: {}", e))?;
        
        Ok(stream)
    }

    async fn check_response(
        &self,
        stream: &mut TcpStream,
        send_data: &str,
        expected: &str,
        timeout_duration: Duration,
    ) -> Result<String> {
        // Send data
        timeout(timeout_duration, stream.write_all(send_data.as_bytes()))
            .await
            .map_err(|_| anyhow::anyhow!("Write timeout"))?
            .map_err(|e| anyhow::anyhow!("Write failed: {}", e))?;

        // Read response
        let mut buffer = vec![0u8; 4096];
        let n = timeout(timeout_duration, stream.read(&mut buffer))
            .await
            .map_err(|_| anyhow::anyhow!("Read timeout"))?
            .map_err(|e| anyhow::anyhow!("Read failed: {}", e))?;

        let response = String::from_utf8_lossy(&buffer[..n]).to_string();
        
        if response.contains(expected) {
            Ok(response)
        } else {
            Err(anyhow::anyhow!("Expected '{}' in response, got: {}", expected, response))
        }
    }

    pub fn config(&self) -> &PortMonitorConfig {
        &self.config
    }

    pub fn name(&self) -> &str {
        &self.config.name
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_port_monitor_localhost() {
        // This test requires a local server running on port 8080
        let config = PortMonitorConfig {
            name: "test-port".to_string(),
            host: "127.0.0.1".to_string(),
            port: 22,  // SSH port, usually available
            timeout_ms: 1000,
            expected_response: None,
            send_data: None,
            interval_seconds: 60,
        };

        let monitor = PortMonitor::new(config, "test-host".to_string());
        let result = monitor.check().await;
        
        // Result depends on whether SSH is running
        println!("Port check result: {:?}", result);
    }
}
