use anyhow::Result;
use tracing::{info, error};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};
use tokio::sync::mpsc;

mod config;
mod collectors;
mod aggregator;
mod storage;
mod streaming;

use config::Config;
use aggregator::MetricAggregator;
use collectors::{ProcCollector, DockerCollector, EbpfCollector};
use streaming::StreamingPublisher;

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
    let docker_collector = DockerCollector::new(clickhouse_url, config.agent.hostname.clone());
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

    info!("🎉 AncientReport AI Agent is running!");
    info!("   Monitoring system with <3% overhead");
    info!("   Press Ctrl+C to stop");

    // Wait for Ctrl+C
    tokio::signal::ctrl_c().await?;
    info!("Shutting down...");

    // Wait for all tasks to complete
    if let Some(backend) = backend_handle {
        if let Some(ebpf) = ebpf_handle {
            let _ = tokio::join!(proc_handle, backend, docker_handle, ebpf);
        } else {
            let _ = tokio::join!(proc_handle, backend, docker_handle);
        }
    } else {
        let _ = tokio::join!(proc_handle, docker_handle);
    }

    info!("👋 AncientReport AI Agent stopped");
    Ok(())
}
