use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::time::Duration;

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct Config {
    pub agent: AgentConfig,
    pub clickhouse: ClickHouseConfig,
    pub nats: Option<NatsConfig>,
    pub ai: AiConfig,
    pub alerts: AlertsConfig,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct AgentConfig {
    pub hostname: String,
    #[serde(with = "humantime_serde")]
    pub collection_interval: Duration,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct ClickHouseConfig {
    pub url: String,
    pub database: String,
    pub username: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct NatsConfig {
    pub url: String,
    pub enabled: bool,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct AiConfig {
    pub provider: String,
    pub api_key: String,
    pub model: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct AlertsConfig {
    pub telegram_token: Option<String>,
    pub telegram_chat_id: Option<String>,
    pub slack_webhook: Option<String>,
}

impl Config {
    pub fn load() -> Result<Self> {
        let config_path = std::env::var("AncientReport_CONFIG")
            .unwrap_or_else(|_| "/etc/AncientReport/config.toml".to_string());

        let config_str = fs::read_to_string(&config_path)
            .with_context(|| format!("Failed to read config file: {}", config_path))?;

        let mut config: Config = toml::from_str(&config_str)
            .with_context(|| "Failed to parse config file")?;

        // Auto-detect hostname if set to "auto-detect"
        if config.agent.hostname == "auto-detect" {
            config.agent.hostname = hostname::get()?
                .to_string_lossy()
                .to_string();
        }

        Ok(config)
    }
}

impl Default for Config {
    fn default() -> Self {
        Self {
            agent: AgentConfig {
                hostname: "auto-detect".to_string(),
                collection_interval: Duration::from_secs(60), // 1 minute
            },
            clickhouse: ClickHouseConfig {
                url: "http://localhost:8123".to_string(),
                database: "AncientReport".to_string(),
                username: None,
                password: None,
            },
            nats: None,
            ai: AiConfig {
                provider: "anthropic".to_string(),
                api_key: String::new(),
                model: "claude-3-5-sonnet-20241022".to_string(),
            },
            alerts: AlertsConfig {
                telegram_token: None,
                telegram_chat_id: None,
                slack_webhook: None,
            },
        }
    }
}
