use anyhow::{Result, Context};
use async_nats::jetstream;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::time::{interval, Duration};
use tracing::{info, warn, error};

use crate::aggregator::Metric;

/// NATS streaming publisher for metrics
/// Provides reliable metric streaming with local buffering
pub struct StreamingPublisher {
    client: async_nats::Client,
    context: jetstream::Context,
    buffer: Vec<Metric>,
    max_buffer_size: usize,
    flush_interval: Duration,
}

impl StreamingPublisher {
    /// Create a new streaming publisher connected to NATS
    pub async fn new(nats_url: &str) -> Result<Self> {
        info!("Connecting to NATS at {}...", nats_url);
        
        let client = async_nats::connect(nats_url)
            .await
            .context("Failed to connect to NATS")?;
        
        let context = jetstream::new(client.clone());
        
        // Create or get the METRICS stream
        Self::ensure_stream(&context).await?;
        
        info!("Connected to NATS JetStream");
        
        Ok(Self {
            client,
            context,
            buffer: Vec::with_capacity(1000),
            max_buffer_size: 1000,
            flush_interval: Duration::from_secs(10),
        })
    }
    
    /// Ensure the METRICS stream exists
    async fn ensure_stream(context: &jetstream::Context) -> Result<()> {
        use async_nats::jetstream::stream::Config;
        use async_nats::jetstream::stream::RetentionPolicy;
        use async_nats::jetstream::stream::StorageType;
        
        let stream_config = Config {
            name: "METRICS".to_string(),
            subjects: vec![
                "metrics.system.*".to_string(),
                "metrics.network.*".to_string(),
                "metrics.disk.*".to_string(),
                "metrics.process.*".to_string(),
            ],
            retention: RetentionPolicy::Limits,
            max_bytes: 1_000_000_000, // 1GB
            max_age: std::time::Duration::from_secs(86400), // 24 hours
            storage: StorageType::File,
            num_replicas: 1,
            ..Default::default()
        };
        
        match context.get_or_create_stream(stream_config).await {
            Ok(_) => {
                info!("METRICS stream ready");
                Ok(())
            }
            Err(e) => {
                warn!("Could not create METRICS stream: {}", e);
                warn!("Streaming may not work correctly");
                Ok(()) // Don't fail, try to continue
            }
        }
    }
    
    /// Publish a metric to NATS
    pub async fn publish(&mut self, metric: Metric) -> Result<()> {
        self.buffer.push(metric);
        
        if self.buffer.len() >= self.max_buffer_size {
            self.flush().await?;
        }
        
        Ok(())
    }
    
    /// Flush buffered metrics to NATS
    pub async fn flush(&mut self) -> Result<()> {
        if self.buffer.is_empty() {
            return Ok(());
        }
        
        let count = self.buffer.len();
        
        // Serialize to MessagePack for efficiency
        let payload = rmp_serde::to_vec(&self.buffer)
            .context("Failed to serialize metrics")?;
        
        // Determine subject based on metric type
        let subject = "metrics.system.batch";
        
        // Publish to JetStream
        self.context
            .publish(subject.to_string(), payload.into())
            .await
            .context("Failed to publish to NATS")?;
        
        info!("Flushed {} metrics to NATS", count);
        self.buffer.clear();
        
        Ok(())
    }
    
    /// Start the streaming publisher with automatic flushing
    pub async fn start(mut self, mut metrics_rx: mpsc::Receiver<Metric>) {
        let mut flush_ticker = interval(self.flush_interval);
        
        loop {
            tokio::select! {
                // Receive metrics from collectors
                Some(metric) = metrics_rx.recv() => {
                    if let Err(e) = self.publish(metric).await {
                        error!("Failed to publish metric: {}", e);
                    }
                }
                
                // Periodic flush
                _ = flush_ticker.tick() => {
                    if let Err(e) = self.flush().await {
                        error!("Failed to flush metrics: {}", e);
                    }
                }
            }
        }
    }
}
