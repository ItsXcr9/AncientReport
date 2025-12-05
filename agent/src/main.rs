use anyhow::Result;
use tracing::{info, error};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};
use tokio::sync::mpsc;

mod config;
mod collectors;
mod aggregator;
mod storage;
mod streaming;
mod custom_monitors;
mod security;

use config::Config;
use aggregator::MetricAggregator;
use collectors::{ProcCollector, DockerCollector, EbpfCollector};
use streaming::StreamingPublisher;
use custom_monitors::CustomMonitorManager;
use security::{PortScanner, ContainerScanner};

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "AncientReport_agent=info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    info!("🚀 AncientReport AI Agent starting...");

    // Load configuration
    let config = Config::load()?;
    info!("✓ Configuration loaded");
    info!("  Hostname: {}", config.agent.hostname);
    info!("  Collection interval: {:?}", config.agent.collection_interval);

    // Create metrics channel
    let (metrics_tx, metrics_rx) = mpsc::channel(10000);
    info!("✓ Metrics channel created");

    // Check if NATS streaming is enabled (V2 mode)
    let use_streaming = config.nats.as_ref().map(|n| n.enabled).unwrap_or(false);
    
    if use_streaming {
        info!("🚀 Running in V2 STREAMING mode");
    } else {
        info!("📊 Running in V1 LEGACY mode (direct ClickHouse)");
    }

    // Start eBPF collectors in V2 mode
    let ebpf_handle = if use_streaming {
        info!("Starting eBPF collectors...");
        let ebpf_collector = EbpfCollector::new(config.agent.hostname.clone(), metrics_tx.clone())?;
        Some(tokio::spawn(async move {
            if let Err(e) = ebpf_collector.start().await {
                error!("eBPF collector error: {}", e);
            }
        }))
    } else {
        info!("ℹ️  eBPF collectors disabled in legacy mode");
        None
    };

    // Start /proc collector
    info!("Starting /proc collector...");
    let proc_collector = ProcCollector::new(config.agent.hostname.clone(), metrics_tx.clone());
    let proc_handle = tokio::spawn(async move {
        if let Err(e) = proc_collector.start().await {
            error!("/proc collector error: {}", e);
        }
    });
    info!("✓ /proc collector started");

    // Start Docker collector
    info!("Starting Docker collector...");
    // Construct ClickHouse URL for Docker collector
    let mut url = reqwest::Url::parse(&config.clickhouse.url).expect("Invalid ClickHouse URL");
    
    // Add query parameters
    {
        let mut pairs = url.query_pairs_mut();
        pairs.append_pair("database", &config.clickhouse.database);
        if let Some(user) = &config.clickhouse.username {
            pairs.append_pair("user", user);
        }
        if let Some(pass) = &config.clickhouse.password {
            pairs.append_pair("password", pass);
        }
    }
    
    let clickhouse_url = url.to_string();
    let docker_collector = DockerCollector::new(clickhouse_url.clone(), config.agent.hostname.clone());
    let docker_handle = tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(60));
        loop {
            interval.tick().await;
            if let Err(e) = docker_collector.collect_and_send().await {
                error!("Docker collector error: {}", e);
            }
        }
    });
    info!("✓ Docker collector started");

    // V3: Start Custom Monitor Manager
    info!("Starting V3 Custom Monitor Manager...");
    let custom_monitor_manager = CustomMonitorManager::new(
        config.agent.hostname.clone(),
        metrics_tx.clone(),
        clickhouse_url.clone(),
        Some("http://localhost:8800".to_string()), // API URL for config
    );
    let custom_monitor_handle = tokio::spawn(async move {
        if let Err(e) = custom_monitor_manager.start().await {
            error!("Custom monitor manager error: {}", e);
        }
    });
    info!("✓ Custom Monitor Manager started");

    // V3: Start Security Scanner (runs hourly)
    info!("Starting V3 Security Scanner...");
    let security_hostname = config.agent.hostname.clone();
    let security_clickhouse_url = clickhouse_url.clone();
    let security_handle = tokio::spawn(async move {
        let scanner = PortScanner::new(security_hostname.clone());
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(3600)); // Hourly
        
        // Initial scan after 60 seconds
        tokio::time::sleep(tokio::time::Duration::from_secs(60)).await;
        
        loop {
            info!("🔍 Running security port scan...");
            let result = scanner.scan_localhost().await;
            info!("✓ Security scan complete: {} open ports, risk score: {}", 
                  result.open_ports.len(), result.risk_score);
            
            // Store results in ClickHouse
            if let Err(e) = store_security_scan(&security_clickhouse_url, &result).await {
                error!("Failed to store security scan: {}", e);
            }
            
            interval.tick().await;
        }
    });
    info!("✓ Security Scanner started");

    // V3: Start Container Vulnerability Scanner (runs at 3 AM daily, different from analysis at 2 AM)
    info!("Starting V3 Container Vulnerability Scanner...");
    let container_nats_url = config.nats.as_ref().map(|n| n.url.clone());
    let container_scan_enabled = use_streaming && container_nats_url.is_some();
    let container_handle = tokio::spawn(async move {
        if !container_scan_enabled {
            info!("Container scanning disabled (NATS not available)");
            return;
        }
        
        let scanner = ContainerScanner::new();
        
        // Connect to NATS for publishing results
        let nats_url = container_nats_url.unwrap();
        let nats_client = match async_nats::connect(&nats_url).await {
            Ok(client) => client,
            Err(e) => {
                error!("Failed to connect to NATS for container scanning: {}", e);
                return;
            }
        };
        
        // Initial scan after 2 minutes
        tokio::time::sleep(tokio::time::Duration::from_secs(120)).await;
        
        // Run container scan and publish results
        loop {
            info!("🔍 Running container vulnerability scan...");
            let results = scanner.scan_all_containers();
            
            for result in &results {
                // Publish each scan result to NATS
                match serde_json::to_vec(result) {
                    Ok(payload) => {
                        if let Err(e) = nats_client.publish("security.container_scan", payload.into()).await {
                            error!("Failed to publish container scan to NATS: {}", e);
                        } else {
                            info!("Published scan for {} to NATS (hostname: {})", result.target, result.hostname);
                        }
                    }
                    Err(e) => {
                        error!("Failed to serialize container scan result: {}", e);
                    }
                }
            }
            
            info!("✓ Container scan complete: {} containers scanned", results.len());
            
            // Wait 6 hours before next scan
            tokio::time::sleep(tokio::time::Duration::from_secs(6 * 3600)).await;
        }
    });
    info!("✓ Container Vulnerability Scanner started");

    // Start aggregator or streaming publisher based on mode
    let backend_handle = if use_streaming {
        let nats_url = config.nats.as_ref().unwrap().url.clone();
        info!("Starting NATS streaming publisher...");
        info!("  NATS URL: {}", nats_url);
        
        match StreamingPublisher::new(&nats_url).await {
            Ok(publisher) => {
                info!("✓ NATS streaming publisher initialized");
                Some(tokio::spawn(async move {
                    publisher.start(metrics_rx).await;
                }))
            }
            Err(e) => {
                error!("Failed to initialize NATS publisher: {}", e);
                error!("Falling back to legacy mode");
                let mut aggregator = MetricAggregator::new(
                    &config.clickhouse.url,
                    &config.clickhouse.database,
                    config.clickhouse.username.clone(),
                    config.clickhouse.password.clone(),
                    config.agent.collection_interval,
                    metrics_rx,
                );
                Some(tokio::spawn(async move {
                    aggregator.start().await;
                }))
            }
        }
    } else {
        info!("Starting metric aggregator...");
        let mut aggregator = MetricAggregator::new(
            &config.clickhouse.url,
            &config.clickhouse.database,
            config.clickhouse.username.clone(),
            config.clickhouse.password.clone(),
            config.agent.collection_interval,
            metrics_rx,
        );
        info!("✓ Metric aggregator initialized");
        Some(tokio::spawn(async move {
            aggregator.start().await;
        }))
    };

    info!("🎉 AncientReport V3 Agent is running!");
    info!("   Monitoring system with <3% overhead");
    info!("   V3 Features: Custom Monitors, Security Scanning");
    info!("   Press Ctrl+C to stop");

    // Wait for Ctrl+C
    tokio::signal::ctrl_c().await?;
    info!("Shutting down...");

    // Wait for all tasks to complete (including V3 tasks)
    if let Some(backend) = backend_handle {
        if let Some(ebpf) = ebpf_handle {
            let _ = tokio::join!(
                proc_handle, 
                backend, 
                docker_handle, 
                ebpf,
                custom_monitor_handle,
                security_handle,
                container_handle
            );
        } else {
            let _ = tokio::join!(
                proc_handle, 
                backend, 
                docker_handle,
                custom_monitor_handle,
                security_handle,
                container_handle
            );
        }
    } else {
        let _ = tokio::join!(
            proc_handle, 
            docker_handle,
            custom_monitor_handle,
            security_handle,
            container_handle
        );
    }

    info!("👋 AncientReport V3 Agent stopped");
    Ok(())
}

/// Store security scan results in ClickHouse
async fn store_security_scan(
    clickhouse_url: &str, 
    result: &security::ScanResult
) -> Result<()> {
    let client = reqwest::Client::new();
    
    let open_ports: Vec<u16> = result.open_ports.iter().map(|p| p.port).collect();
    let risky_ports: Vec<u16> = result.risky_ports.iter().map(|p| p.port).collect();
    let results_json = serde_json::to_string(&result.open_ports)?;
    
    let query = format!(
        r#"INSERT INTO security_scans 
           (timestamp, hostname, scan_type, target, results, risk_score, open_ports, risky_ports) 
           VALUES (now(), '{}', 'port', '{}', '{}', {}, {:?}, {:?})"#,
        result.hostname,
        result.target,
        results_json.replace('\'', "''"),
        result.risk_score,
        open_ports,
        risky_ports,
    );

    client
        .post(clickhouse_url)
        .body(query)
        .send()
        .await?;

    Ok(())
}
