// Port Scanner for AncientReport V3
// Scans for open ports and identifies security risks

use anyhow::Result;
use std::collections::HashSet;
use std::net::SocketAddr;
use std::time::{Duration, Instant};
use tokio::net::TcpStream;
use tokio::time::timeout;
use tracing::{info, debug, warn};

use super::types::{OpenPort, ScanResult, ScanType, RiskyPortConfig, default_risky_ports, SecuritySeverity};

/// Port scanner for security auditing
pub struct PortScanner {
    hostname: String,
    risky_ports: Vec<RiskyPortConfig>,
    common_ports: Vec<u16>,
    scan_timeout_ms: u64,
}

impl PortScanner {
    pub fn new(hostname: String) -> Self {
        Self {
            hostname,
            risky_ports: default_risky_ports(),
            common_ports: Self::get_common_ports(),
            scan_timeout_ms: 1000,
        }
    }

    fn get_common_ports() -> Vec<u16> {
        vec![
            20, 21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 993, 995,
            1433, 1521, 1723, 3306, 3389, 5432, 5900, 5901, 6379, 8080, 8443, 9200,
            27017, 27018, 27019, 11211, 6380, 6381, 9000, 9090, 9092, 15672, 5672,
        ]
    }

    /// Scan common ports on localhost
    pub async fn scan_localhost(&self) -> ScanResult {
        self.scan_host("127.0.0.1").await
    }

    /// Scan a specific host
    pub async fn scan_host(&self, target: &str) -> ScanResult {
        let start = Instant::now();
        info!("🔍 Starting port scan on {}", target);

        let mut open_ports = Vec::new();
        let mut risky_ports = Vec::new();

        // Scan common ports
        for port in &self.common_ports {
            if let Ok(open_port) = self.check_port(target, *port).await {
                // Check if this is a risky port
                let is_risky = self.check_risky(&open_port);
                let mut port_info = open_port;
                port_info.is_risky = is_risky;

                if is_risky {
                    port_info.risk_reason = self.get_risk_reason(port_info.port);
                    risky_ports.push(port_info.clone());
                }
                open_ports.push(port_info);
            }
        }

        let elapsed = start.elapsed();
        info!("✓ Port scan complete in {:.2}s: {} open, {} risky", 
              elapsed.as_secs_f32(), open_ports.len(), risky_ports.len());

        // Calculate risk score (0-100)
        let risk_score = self.calculate_risk_score(&open_ports, &risky_ports);

        ScanResult {
            hostname: self.hostname.clone(),
            target: target.to_string(),
            scan_type: ScanType::Port,
            timestamp: chrono::Utc::now().timestamp(),
            open_ports,
            risky_ports,
            risk_score,
        }
    }

    /// Scan a range of ports
    pub async fn scan_port_range(&self, target: &str, start_port: u16, end_port: u16) -> ScanResult {
        let start = Instant::now();
        info!("🔍 Scanning ports {}-{} on {}", start_port, end_port, target);

        let mut open_ports = Vec::new();
        let mut risky_ports = Vec::new();

        // Use concurrent scanning for speed
        let mut handles = Vec::new();
        let concurrency = 100; // Max concurrent connections
        
        for port_chunk in (start_port..=end_port).collect::<Vec<_>>().chunks(concurrency) {
            for port in port_chunk {
                let target = target.to_string();
                let port = *port;
                let timeout_ms = self.scan_timeout_ms;
                
                handles.push(tokio::spawn(async move {
                    Self::tcp_probe(&target, port, timeout_ms).await
                }));
            }
            
            // Wait for this batch
            let results = futures::future::join_all(handles.drain(..)).await;
            for result in results {
                if let Ok(Some(port_info)) = result {
                    let is_risky = self.check_risky(&port_info);
                    let mut port_info = port_info;
                    port_info.is_risky = is_risky;
                    
                    if is_risky {
                        port_info.risk_reason = self.get_risk_reason(port_info.port);
                        risky_ports.push(port_info.clone());
                    }
                    open_ports.push(port_info);
                }
            }
        }

        let elapsed = start.elapsed();
        info!("✓ Range scan complete in {:.2}s: {} open", elapsed.as_secs_f32(), open_ports.len());

        let risk_score = self.calculate_risk_score(&open_ports, &risky_ports);

        ScanResult {
            hostname: self.hostname.clone(),
            target: target.to_string(),
            scan_type: ScanType::Port,
            timestamp: chrono::Utc::now().timestamp(),
            open_ports,
            risky_ports,
            risk_score,
        }
    }

    async fn check_port(&self, target: &str, port: u16) -> Result<OpenPort> {
        match Self::tcp_probe(target, port, self.scan_timeout_ms).await {
            Some(port_info) => Ok(port_info),
            None => Err(anyhow::anyhow!("Port closed or filtered")),
        }
    }

    async fn tcp_probe(target: &str, port: u16, timeout_ms: u64) -> Option<OpenPort> {
        let addr = format!("{}:{}", target, port);
        let addr: SocketAddr = match addr.parse() {
            Ok(a) => a,
            Err(_) => return None,
        };

        let timeout_duration = Duration::from_millis(timeout_ms);
        
        match timeout(timeout_duration, TcpStream::connect(addr)).await {
            Ok(Ok(_)) => {
                debug!("Port {} is open", port);
                Some(OpenPort {
                    port,
                    protocol: "tcp".to_string(),
                    service: Self::guess_service(port),
                    state: "open".to_string(),
                    is_risky: false,
                    risk_reason: None,
                })
            }
            _ => None,
        }
    }

    fn check_risky(&self, port: &OpenPort) -> bool {
        self.risky_ports.iter().any(|rp| rp.port == port.port)
    }

    fn get_risk_reason(&self, port: u16) -> Option<String> {
        self.risky_ports
            .iter()
            .find(|rp| rp.port == port)
            .map(|rp| format!("{} - {:?}", rp.name, rp.alert_if))
    }

    fn calculate_risk_score(&self, open_ports: &[OpenPort], risky_ports: &[OpenPort]) -> u8 {
        let mut score: u8 = 0;
        
        // Base score from risky ports
        for port in risky_ports {
            let severity_score = match self.risky_ports.iter().find(|rp| rp.port == port.port) {
                Some(rp) => match rp.severity {
                    SecuritySeverity::Critical => 30,
                    SecuritySeverity::Warning => 15,
                    SecuritySeverity::Info => 5,
                },
                None => 10,
            };
            score = score.saturating_add(severity_score);
        }

        // Cap at 100
        score.min(100)
    }

    fn guess_service(port: u16) -> Option<String> {
        match port {
            20 | 21 => Some("FTP".to_string()),
            22 => Some("SSH".to_string()),
            23 => Some("Telnet".to_string()),
            25 => Some("SMTP".to_string()),
            53 => Some("DNS".to_string()),
            80 => Some("HTTP".to_string()),
            110 => Some("POP3".to_string()),
            143 => Some("IMAP".to_string()),
            443 => Some("HTTPS".to_string()),
            445 => Some("SMB".to_string()),
            1433 => Some("MSSQL".to_string()),
            3306 => Some("MySQL".to_string()),
            3389 => Some("RDP".to_string()),
            5432 => Some("PostgreSQL".to_string()),
            5672 => Some("RabbitMQ".to_string()),
            5900 => Some("VNC".to_string()),
            6379 => Some("Redis".to_string()),
            8080 => Some("HTTP-Proxy".to_string()),
            9200 => Some("Elasticsearch".to_string()),
            27017 => Some("MongoDB".to_string()),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_port_scanner_localhost() {
        let scanner = PortScanner::new("test-host".to_string());
        let result = scanner.scan_localhost().await;
        
        println!("Scan result: {} open ports, {} risky", 
                 result.open_ports.len(), result.risky_ports.len());
        println!("Risk score: {}", result.risk_score);
        
        for port in &result.open_ports {
            println!("  Port {}: {:?} (risky: {})", 
                     port.port, port.service, port.is_risky);
        }
    }
}
