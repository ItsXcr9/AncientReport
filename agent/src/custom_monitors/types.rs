// Custom Monitor Types for AncientReport V3

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Monitor status enum
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MonitorStatus {
    Ok,
    Warning,
    Critical,
    Unknown,
}

impl std::fmt::Display for MonitorStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MonitorStatus::Ok => write!(f, "ok"),
            MonitorStatus::Warning => write!(f, "warning"),
            MonitorStatus::Critical => write!(f, "critical"),
            MonitorStatus::Unknown => write!(f, "unknown"),
        }
    }
}

/// Monitor type enum
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MonitorType {
    Port,
    Http,
    Process,
    Script,
    Metric,
}

/// Result from a monitor check
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitorResult {
    pub monitor_id: String,
    pub monitor_name: String,
    pub status: MonitorStatus,
    pub latency_ms: f32,
    pub response: Option<String>,
    pub error: Option<String>,
    pub timestamp: i64,
}

/// Port monitor configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortMonitorConfig {
    pub name: String,
    pub host: String,
    pub port: u16,
    pub timeout_ms: u64,
    #[serde(default)]
    pub expected_response: Option<String>,
    #[serde(default)]
    pub send_data: Option<String>,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
}

/// HTTP monitor configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HttpMonitorConfig {
    pub name: String,
    pub url: String,
    #[serde(default = "default_method")]
    pub method: String,
    #[serde(default)]
    pub headers: HashMap<String, String>,
    #[serde(default)]
    pub body: Option<String>,
    #[serde(default = "default_timeout")]
    pub timeout_ms: u64,
    #[serde(default)]
    pub expected_status: Option<u16>,
    #[serde(default)]
    pub expected_body_contains: Option<String>,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
}

/// Process monitor configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessMonitorConfig {
    pub name: String,
    pub process_match: String,  // Regex pattern
    #[serde(default = "default_expected_count")]
    pub expected_count: u32,
    #[serde(default)]
    pub cpu_threshold_percent: Option<f32>,
    #[serde(default)]
    pub memory_threshold_mb: Option<u64>,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
}

/// Script monitor configuration  
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScriptMonitorConfig {
    pub name: String,
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default = "default_timeout")]
    pub timeout_ms: u64,
    #[serde(default)]
    pub expected_exit_code: Option<i32>,
    #[serde(default)]
    pub expected_output_contains: Option<String>,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
}

/// Generic custom monitor configuration (from API)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CustomMonitorConfig {
    pub id: Option<String>,
    pub name: String,
    pub monitor_type: MonitorType,
    pub config: serde_json::Value,
    #[serde(default = "default_interval")]
    pub interval_seconds: u64,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_interval() -> u64 { 60 }
fn default_timeout() -> u64 { 5000 }
fn default_method() -> String { "GET".to_string() }
fn default_expected_count() -> u32 { 1 }
fn default_enabled() -> bool { true }
