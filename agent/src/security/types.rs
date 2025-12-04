// Security Types for AncientReport V3

use serde::{Deserialize, Serialize};

/// Scan type enum
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ScanType {
    Port,
    Network,
    Container,
    File,
}

/// Security severity
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SecuritySeverity {
    Info,
    Warning,
    Critical,
}

/// Open port information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpenPort {
    pub port: u16,
    pub protocol: String,
    pub service: Option<String>,
    pub state: String,
    pub is_risky: bool,
    pub risk_reason: Option<String>,
}

/// Known risky ports configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskyPortConfig {
    pub port: u16,
    pub name: String,
    pub alert_if: RiskyPortCondition,
    pub severity: SecuritySeverity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskyPortCondition {
    Open,
    ExposedToInternet,
    NoAuth,
}

/// Port scan result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanResult {
    pub hostname: String,
    pub target: String,
    pub scan_type: ScanType,
    pub timestamp: i64,
    pub open_ports: Vec<OpenPort>,
    pub risky_ports: Vec<OpenPort>,
    pub risk_score: u8,
}

/// Security event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityEvent {
    pub timestamp: i64,
    pub hostname: String,
    pub event_type: SecurityEventType,
    pub severity: SecuritySeverity,
    pub source: String,
    pub description: String,
    pub details: serde_json::Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SecurityEventType {
    PortOpened,
    SuspiciousConnection,
    FileChanged,
    ProcessSuspicious,
    ContainerPrivileged,
    ThreatDetected,
}

/// Default risky ports
pub fn default_risky_ports() -> Vec<RiskyPortConfig> {
    vec![
        RiskyPortConfig {
            port: 21,
            name: "FTP".to_string(),
            alert_if: RiskyPortCondition::Open,
            severity: SecuritySeverity::Warning,
        },
        RiskyPortConfig {
            port: 23,
            name: "Telnet".to_string(),
            alert_if: RiskyPortCondition::Open,
            severity: SecuritySeverity::Critical,
        },
        RiskyPortConfig {
            port: 3389,
            name: "RDP".to_string(),
            alert_if: RiskyPortCondition::ExposedToInternet,
            severity: SecuritySeverity::Critical,
        },
        RiskyPortConfig {
            port: 5900,
            name: "VNC".to_string(),
            alert_if: RiskyPortCondition::Open,
            severity: SecuritySeverity::Warning,
        },
        RiskyPortConfig {
            port: 27017,
            name: "MongoDB".to_string(),
            alert_if: RiskyPortCondition::NoAuth,
            severity: SecuritySeverity::Critical,
        },
        RiskyPortConfig {
            port: 6379,
            name: "Redis".to_string(),
            alert_if: RiskyPortCondition::NoAuth,
            severity: SecuritySeverity::Critical,
        },
        RiskyPortConfig {
            port: 9200,
            name: "Elasticsearch".to_string(),
            alert_if: RiskyPortCondition::ExposedToInternet,
            severity: SecuritySeverity::Critical,
        },
        RiskyPortConfig {
            port: 5432,
            name: "PostgreSQL".to_string(),
            alert_if: RiskyPortCondition::ExposedToInternet,
            severity: SecuritySeverity::Warning,
        },
        RiskyPortConfig {
            port: 3306,
            name: "MySQL".to_string(),
            alert_if: RiskyPortCondition::ExposedToInternet,
            severity: SecuritySeverity::Warning,
        },
    ]
}
