use anyhow::Result;
use sysinfo::{System, Disks};
use tokio::sync::mpsc;
use tokio::time::{interval, Duration};
use tokio::fs;
use tracing::info;
use std::collections::HashMap;
use std::process::Command;

use crate::aggregator::Metric;

/// /proc filesystem-based collector for CPU, memory, and process metrics
///
/// This collector reads from /proc and uses the sysinfo crate to gather
/// system-level metrics that complement eBPF data.
pub struct ProcCollector {
    system: System,
    hostname: String,
    metrics_tx: mpsc::Sender<Metric>,
    last_disk_stats: Option<DiskStats>,
    last_net_stats: Option<NetStats>,
}

impl ProcCollector {
    pub fn new(hostname: String, metrics_tx: mpsc::Sender<Metric>) -> Self {
        info!("Initializing /proc collector...");
        info!("Note: Agent should run with 'pid: host' to see host processes, not container processes");
        
        // Verify we can access host /proc (mounted at /host/proc in container)
        // This helps ensure we're reading from the host, not the container
        let mut system = System::new_all();
        
        // Log a sample of processes to verify we're seeing host processes
        // If we only see container processes (like the agent itself), that's a problem
        system.refresh_processes();
        let process_count = system.processes().len();
        info!("Initial process count: {} (should be > 50 for host, < 10 for container)", process_count);
        
        // Check for a host process that shouldn't be in container (e.g., systemd, kernel threads)
        let has_host_processes = system.processes().iter().any(|(_, proc)| {
            let name = proc.name().to_lowercase();
            name.contains("systemd") || name.contains("kthreadd") || name.contains("ksoftirqd")
        });
        
        if has_host_processes {
            info!("✓ Detected host processes (systemd/kthreadd) - reading from host /proc");
        } else {
            tracing::warn!("⚠️  No host processes detected - may be reading from container /proc");
            tracing::warn!("⚠️  Ensure docker-compose.yml has 'pid: host' for agent service");
        }
        
        Self {
            system,
            hostname,
            metrics_tx,
            last_disk_stats: None,
            last_net_stats: None,
        }
    }

    pub async fn start(mut self) -> Result<()> {
        info!("/proc collector started (1 minute interval)");
        let mut ticker = interval(Duration::from_secs(60)); // Collect every minute

        loop {
            ticker.tick().await;
            if let Err(e) = self.collect_metrics().await {
                tracing::error!("Failed to collect metrics: {}", e);
            }
        }
    }

    async fn collect_metrics(&mut self) -> Result<()> {
        // Refresh system information
        self.system.refresh_all();

        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let mut tags = HashMap::new();
        tags.insert("source".to_string(), "proc".to_string());

        // Collect CPU metrics
        let cpu_usage = self.system.global_cpu_info().cpu_usage();
        let cpu_count = self.system.cpus().len();
        info!("CPU usage: {:.2}% ({} cores)", cpu_usage, cpu_count);
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "cpu_usage_percent".to_string(),
            cpu_usage as f64,
            tags.clone(),
        )).await?;

        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "cpu_cores".to_string(),
            cpu_count as f64,
            tags.clone(),
        )).await?;

        // Collect memory metrics
        let total_memory = self.system.total_memory();
        let used_memory = self.system.used_memory();
        let memory_percent = (used_memory as f64 / total_memory as f64) * 100.0;
        info!("Memory usage: {:.2}% ({} MB / {} MB)", 
            memory_percent, 
            used_memory / 1024 / 1024,
            total_memory / 1024 / 1024
        );
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "memory_usage_percent".to_string(),
            memory_percent,
            tags.clone(),
        )).await?;
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "memory_used_mb".to_string(),
            (used_memory / 1024 / 1024) as f64,
            tags.clone(),
        )).await?;

        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "memory_total_mb".to_string(),
            (total_memory / 1024 / 1024) as f64,
            tags.clone(),
        )).await?;

        // Collect load average
        let load_avg = System::load_average();
        info!("Load average: {:.2}, {:.2}, {:.2}", 
            load_avg.one, load_avg.five, load_avg.fifteen
        );
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "load_avg_1min".to_string(),
            load_avg.one,
            tags.clone(),
        )).await?;
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "load_avg_5min".to_string(),
            load_avg.five,
            tags.clone(),
        )).await?;
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "load_avg_15min".to_string(),
            load_avg.fifteen,
            tags.clone(),
        )).await?;

        // Collect process count
        let process_count = self.system.processes().len();
        info!("Process count: {}", process_count);
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "process_count".to_string(),
            process_count as f64,
            tags.clone(),
        )).await?;

        // Collect disk space metrics
        let disks = Disks::new_with_refreshed_list();
        
        let mut total_space: u64 = 0;
        let mut available_space: u64 = 0;
        
        let mut unique_devices = std::collections::HashSet::new();
        
        for disk in &disks {
            // Get filesystem type and convert to lowercase for case-insensitive comparison
            let fs_type = disk.file_system().to_string_lossy().to_lowercase();
            let device_name = disk.name().to_string_lossy();
            
            // Skip common pseudo-filesystems and read-only loop devices
            // overlay: Docker overlay filesystems (duplicates host storage)
            // squashfs: Snap packages (read-only compressed)
            // tmpfs/devtmpfs: In-memory filesystems
            // auffs/overlayfs: Union filesystems
            if fs_type.starts_with("tmp") || 
               fs_type.starts_with("dev") || 
               fs_type.contains("overlay") || 
               fs_type.contains("squashfs") ||
               fs_type.contains("aufs") {
                continue;
            }
            
            // Avoid double counting the same device mounted in multiple locations
            // We use the device name as the unique identifier
            if !unique_devices.insert(device_name.to_string()) {
                continue;
            }

            total_space += disk.total_space();
            available_space += disk.available_space();
        }
        
        let used_space = total_space.saturating_sub(available_space);
        let disk_usage_percent = if total_space > 0 {
            (used_space as f64 / total_space as f64) * 100.0
        } else {
            0.0
        };
        
        info!("Disk usage: {:.2}% ({} GB / {} GB)", 
            disk_usage_percent,
            used_space / 1024 / 1024 / 1024,
            total_space / 1024 / 1024 / 1024
        );
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "disk_total_gb".to_string(),
            (total_space / 1024 / 1024 / 1024) as f64,
            tags.clone(),
        )).await?;
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "disk_used_gb".to_string(),
            (used_space / 1024 / 1024 / 1024) as f64,
            tags.clone(),
        )).await?;
        
        self.metrics_tx.send(Metric::new_basic(
            timestamp,
            self.hostname.clone(),
            "system".to_string(),
            "disk_usage_percent".to_string(),
            disk_usage_percent,
            tags.clone(),
        )).await?;

        // Collect disk I/O metrics
        if let Err(e) = self.collect_disk_io(timestamp, &tags).await {
            tracing::warn!("Failed to collect disk I/O metrics: {}", e);
        }

        // Collect network metrics
        if let Err(e) = self.collect_network(timestamp, &tags).await {
            tracing::warn!("Failed to collect network metrics: {}", e);
        }

        // Collect TCP flows for Active Flows feature
        if let Err(e) = self.collect_tcp_flows(timestamp, &tags).await {
            tracing::warn!("Failed to collect TCP flows: {}", e);
        }

        // Collect per-process network bandwidth
        if let Err(e) = self.collect_process_bandwidth(timestamp, &tags).await {
            tracing::warn!("Failed to collect process bandwidth: {}", e);
        }

        // Collect top processes (CPU, Memory, Disk I/O, Network)
        info!("Starting top processes collection...");
        match self.collect_top_processes(timestamp, &tags).await {
            Ok(_) => info!("✓ Top processes collection completed successfully"),
            Err(e) => {
                tracing::error!("Failed to collect top processes: {}", e);
                tracing::error!("Error details: {:?}", e);
            }
        }

        Ok(())
    }

    async fn collect_disk_io(&mut self, timestamp: i64, tags: &HashMap<String, String>) -> Result<()> {
        // Read /proc/diskstats
        let diskstats_content = match fs::read_to_string("/proc/diskstats").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/host/proc/diskstats").await?,
        };
        
        let mut total_reads: u64 = 0;
        let mut total_writes: u64 = 0;
        let mut total_read_sectors: u64 = 0;
        let mut total_write_sectors: u64 = 0;
        let mut total_io_time_ms: u64 = 0;
        let mut disk_count = 0;

        for line in diskstats_content.lines() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 14 {
                // Skip loop devices and partitions
                let device = parts[2];
                if device.starts_with("loop") || device.chars().any(|c| c.is_ascii_digit() && device.len() > 3) {
                    continue;
                }

                // Fields: major minor name reads reads_merged reads_sectors reads_time writes writes_merged writes_sectors writes_time io_in_progress io_time_ms io_time_weighted_ms
                if let (Ok(reads), Ok(writes), Ok(read_sectors), Ok(write_sectors), Ok(io_time_ms)) = (
                    parts[3].parse::<u64>(),
                    parts[7].parse::<u64>(),
                    parts[5].parse::<u64>(),
                    parts[9].parse::<u64>(),
                    parts[12].parse::<u64>(),
                ) {
                    total_reads += reads;
                    total_writes += writes;
                    total_read_sectors += read_sectors;
                    total_write_sectors += write_sectors;
                    total_io_time_ms += io_time_ms;
                    disk_count += 1;
                }
            }
        }

        if disk_count == 0 {
            return Ok(());
        }

        let current_stats = DiskStats {
            reads: total_reads,
            writes: total_writes,
            read_sectors: total_read_sectors,
            write_sectors: total_write_sectors,
            io_time_ms: total_io_time_ms,
        };

        // Calculate per-second rates if we have previous stats
        if let Some(ref last_stats) = self.last_disk_stats {
            let time_diff = 60.0; // 60 seconds (1 minute) between collections
            let reads_per_sec = ((current_stats.reads.saturating_sub(last_stats.reads)) as f64) / time_diff;
            let writes_per_sec = ((current_stats.writes.saturating_sub(last_stats.writes)) as f64) / time_diff;
            
            // Calculate average latency (simplified: io_time_ms / total_operations)
            let total_ops = current_stats.reads + current_stats.writes;
            let last_total_ops = last_stats.reads + last_stats.writes;
            let ops_diff = total_ops.saturating_sub(last_total_ops);
            let io_time_diff = current_stats.io_time_ms.saturating_sub(last_stats.io_time_ms);
            
            let latency_ms = if ops_diff > 0 {
                (io_time_diff as f64) / (ops_diff as f64)
            } else {
                0.0
            };

            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "disk".to_string(),
                "disk_reads_per_sec".to_string(),
                reads_per_sec,
                tags.clone(),
            )).await?;

            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "disk".to_string(),
                "disk_writes_per_sec".to_string(),
                writes_per_sec,
                tags.clone(),
            )).await?;

            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "disk".to_string(),
                "disk_latency_ms".to_string(),
                latency_ms,
                tags.clone(),
            )).await?;
        }

        self.last_disk_stats = Some(current_stats);
        Ok(())
    }

    async fn collect_network(&mut self, timestamp: i64, tags: &HashMap<String, String>) -> Result<()> {
        // 1. Read /proc/net/dev (Bandwidth & Drops)
        let netdev_content = match fs::read_to_string("/proc/net/dev").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/host/proc/net/dev").await?,
        };
        
        let mut total_rx_bytes: u64 = 0;
        let mut total_tx_bytes: u64 = 0;
        let mut total_rx_packets: u64 = 0;
        let mut total_tx_packets: u64 = 0;
        let mut total_rx_drops: u64 = 0;
        let mut total_tx_drops: u64 = 0;

        for line in netdev_content.lines().skip(2) {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 10 {
                if let (Ok(rx_bytes), Ok(rx_packets), Ok(rx_drops), Ok(tx_bytes), Ok(tx_packets), Ok(tx_drops)) = (
                    parts[1].parse::<u64>(),
                    parts[2].parse::<u64>(),
                    parts[4].parse::<u64>(),
                    parts[9].parse::<u64>(),
                    parts[10].parse::<u64>(),
                    parts[12].parse::<u64>(),
                ) {
                    if !parts[0].trim_end_matches(':').starts_with("lo") {
                        total_rx_bytes += rx_bytes;
                        total_rx_packets += rx_packets;
                        total_rx_drops += rx_drops;
                        total_tx_bytes += tx_bytes;
                        total_tx_packets += tx_packets;
                        total_tx_drops += tx_drops;
                    }
                }
            }
        }
        
        let total_drops = total_rx_drops + total_tx_drops;

        // 1.5. Read /proc/stat (SoftIRQ & System CPU)
        let stat_content = match fs::read_to_string("/proc/stat").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/host/proc/stat").await.unwrap_or_default(),
        };

        let mut softirq = 0u64;
        let mut system_cpu = 0u64;
        let mut total_cpu = 0u64;

        if let Some(first_line) = stat_content.lines().next() {
             if first_line.starts_with("cpu ") {
                 let parts: Vec<&str> = first_line.split_whitespace().collect();
                 // cpu user nice system idle iowait irq softirq ...
                 if parts.len() >= 8 {
                     let user: u64 = parts[1].parse().unwrap_or(0);
                     let nice: u64 = parts[2].parse().unwrap_or(0);
                     let system: u64 = parts[3].parse().unwrap_or(0);
                     let idle: u64 = parts[4].parse().unwrap_or(0);
                     let iowait: u64 = parts[5].parse().unwrap_or(0);
                     let irq: u64 = parts[6].parse().unwrap_or(0);
                     let soft: u64 = parts[7].parse().unwrap_or(0);
                     let steal: u64 = parts.get(8).and_then(|s| s.parse().ok()).unwrap_or(0);
                     
                     softirq = soft;
                     system_cpu = system;
                     total_cpu = user + nice + system + idle + iowait + irq + soft + steal;
                 }
             }
        }

        // 1.6 Read /proc/net/sockstat (TimeWait)
        let sockstat_content = match fs::read_to_string("/proc/net/sockstat").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/host/proc/net/sockstat").await.unwrap_or_default(),
        };
        
        let mut time_wait = 0u64;
        for line in sockstat_content.lines() {
            if line.starts_with("TCP: ") {
                // TCP: inuse 8 orphan 0 tw 0 alloc 10 mem 1
                if let Some(tw_idx) = line.find("tw ") {
                    let after_tw = &line[tw_idx + 3..];
                    let tw_val: Vec<&str> = after_tw.split_whitespace().collect();
                    if let Some(val) = tw_val.first() {
                        time_wait = val.parse().unwrap_or(0);
                    }
                }
            }
        }

        // 1.7 Read /proc/net/netstat (Socket Pressure via TCPMemoryPressures)
        let netstat_content = match fs::read_to_string("/proc/net/netstat").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/host/proc/net/netstat").await.unwrap_or_default(),
        };
        
        let mut socket_pressure = 0u64;
        // Format is 2 lines: headers then values
        let mut headers: Vec<&str> = Vec::new();
        for line in netstat_content.lines() {
            if line.starts_with("TcpExt: ") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if headers.is_empty() {
                    headers = parts;
                } else {
                    // This is the value line
                    for (i, header) in headers.iter().enumerate() {
                        if *header == "TCPMemoryPressures" && i < parts.len() {
                            socket_pressure = parts[i].parse().unwrap_or(0);
                            break;
                        }
                    }
                }
            }
        }

        // 2. Read /proc/net/snmp (Retransmits & States)
        let snmp_content = match fs::read_to_string("/proc/net/snmp").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/host/proc/net/snmp").await.unwrap_or_default(),
        };
        
        let mut retransmits = 0u64;
        let mut established = 0u64;
        let mut active_opens = 0u64;
        let mut passive_opens = 0u64;
        
        for line in snmp_content.lines() {
            if line.starts_with("Tcp: ") && !line.contains("RtoAlgorithm") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() > 12 {
                    // Indexes (1-based in RFC 1213, 0-based here after 'Tcp:'): 
                    // 5: ActiveOpens, 6: PassiveOpens, 9: CurrEstab, 12: RetransSegs
                    active_opens = parts[5].parse().unwrap_or(0);
                    passive_opens = parts[6].parse().unwrap_or(0);
                    established = parts[9].parse().unwrap_or(0);
                    retransmits = parts[12].parse().unwrap_or(0);
                }
            }
        }
        
        // 3. Get Latency via ss -ti
        // Collect all RTTs to calculate real percentiles
        let mut rtt_values: Vec<f64> = Vec::new();
        let mut active_connections: u64 = 0;
        
        let mut latency_p50: f64 = 0.0;
        let mut latency_p90: f64 = 0.0;
        let mut latency_p99: f64 = 0.0;
        
        if let Ok(output) = Command::new("ss").args(&["-ti"]).output() {
            if output.status.success() {
                let output_str = String::from_utf8_lossy(&output.stdout);
                
                for line in output_str.lines() {
                    active_connections += 1;
                    if let Some(rtt_idx) = line.find("rtt:") {
                        // format check: rtt:12.34/5.67
                        let after = &line[rtt_idx + 4..];
                        let parts: Vec<&str> = after.split_whitespace().next().unwrap_or("").split('/').collect();
                        if let Some(rtt_val_str) = parts.first() {
                             if let Ok(rtt) = rtt_val_str.parse::<f64>() {
                                 rtt_values.push(rtt);
                             }
                        }
                    }
                }
                
                if !rtt_values.is_empty() {
                    rtt_values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                    let len = rtt_values.len();
                    
                    latency_p50 = rtt_values[len / 2];
                    latency_p90 = rtt_values[(len * 9) / 10];
                    latency_p99 = rtt_values[(len * 99) / 100];
                }
                
                // active_connections includes header
                active_connections = active_connections.saturating_sub(1); 
            }
        }

        // Calculate rates
        let current_stats = NetStats {
            rx_bytes: total_rx_bytes,
            tx_bytes: total_tx_bytes,
            rx_packets: total_rx_packets,
            tx_packets: total_tx_packets,
            rx_drops: total_rx_drops,
            tx_drops: total_tx_drops,
            active_opens,
            passive_opens,
            established,
            retransmits,
            softirq,
            system_cpu,
            socket_pressure,
            total_cpu,
        };

        if let Some(ref last_stats) = self.last_net_stats {
            let time_diff = 60.0;
            let packets_sent_per_sec = ((current_stats.tx_packets.saturating_sub(last_stats.tx_packets)) as f64) / time_diff;
            let packets_received_per_sec = ((current_stats.rx_packets.saturating_sub(last_stats.rx_packets)) as f64) / time_diff;
            let bytes_sent_per_sec = ((current_stats.tx_bytes.saturating_sub(last_stats.tx_bytes)) as f64) / time_diff;
            let bytes_received_per_sec = ((current_stats.rx_bytes.saturating_sub(last_stats.rx_bytes)) as f64) / time_diff;
            
            // Calculate connection rates (ActiveOpens + PassiveOpens)
            let current_opens = current_stats.active_opens + current_stats.passive_opens;
            let last_opens = last_stats.active_opens + last_stats.passive_opens;
            let connection_open_rate = ((current_opens.saturating_sub(last_opens)) as f64) / time_diff;
            
            // Calculate Close Rate: LastEst + Opens - CurrentEst = Closes
            // Closes/sec = (LastEst + OpensDelta - CurrentEst) / time_diff
            let total_opens_delta = current_opens.saturating_sub(last_opens);
            let estimated_closes = (last_stats.established + total_opens_delta).saturating_sub(current_stats.established);
            let connection_close_rate = (estimated_closes as f64) / time_diff;

            // SoftIRQ % and System CPU %
            let softirq_diff = current_stats.softirq.saturating_sub(last_stats.softirq);
            let system_diff = current_stats.system_cpu.saturating_sub(last_stats.system_cpu);
            let total_cpu_diff = current_stats.total_cpu.saturating_sub(last_stats.total_cpu);
            
            let (softirq_percent, system_cpu_percent) = if total_cpu_diff > 0 {
                (
                    (softirq_diff as f64 / total_cpu_diff as f64) * 100.0,
                    (system_diff as f64 / total_cpu_diff as f64) * 100.0
                )
            } else {
                (0.0, 0.0)
            };
            
            // Socket Pressure (Delta)
            let pressure_diff = current_stats.socket_pressure.saturating_sub(last_stats.socket_pressure);
            // Convert to a boolean-like percentage (if > 0 events per minute, show pressure)
            // Or just normalization. For now, sending raw events might be confusing if UI expects %.
            // Let's cap at 100 if > 0.
            let pressure_val = if pressure_diff > 0 { 100.0 } else { 0.0 };

            // Legacy Metrics
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_packets_sent".to_string(), packets_sent_per_sec, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_packets_received".to_string(), packets_received_per_sec, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_bytes_sent".to_string(), bytes_sent_per_sec, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_bytes_received".to_string(), bytes_received_per_sec, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_drops".to_string(), total_drops as f64, tags.clone())).await?;
            
            // New Explicit Metrics for Debian/Non-eBPF support
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_connection_open_rate".to_string(), connection_open_rate, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_connection_close_rate".to_string(), connection_close_rate, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_latency_p50".to_string(), latency_p50, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_latency_p90".to_string(), latency_p90, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_latency_p99".to_string(), latency_p99, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_active_connections".to_string(), active_connections as f64, tags.clone())).await?;
            
            // New Comprehensive Metrics
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_retransmits".to_string(), retransmits as f64, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_time_wait".to_string(), time_wait as f64, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "system".to_string(), "softirq_net_percent".to_string(), softirq_percent, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "system".to_string(), "cpu_system_percent".to_string(), system_cpu_percent, tags.clone())).await?;
            self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "socket_queue_pressure".to_string(), pressure_val, tags.clone())).await?;
            
            // V2 Advanced Metric (Consolidated)
            // This metric contains all fields needed for network_metrics_ts
            let mut v2_metric = Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "network".to_string(),
                "network_snapshot".to_string(),
                0.0,
                tags.clone()
            );
            
            // Populate V2 fields
            v2_metric.latency_p50 = Some(latency_p50);
            v2_metric.latency_p90 = Some(latency_p90);
            v2_metric.latency_p99 = Some(latency_p99);
            v2_metric.retransmits = Some(retransmits);
            v2_metric.packet_drops = Some(total_drops);
            v2_metric.active_connections = Some(active_connections);
            v2_metric.established = Some(established);
            v2_metric.established = Some(established);
            v2_metric.open_rate = Some(connection_open_rate); 
            v2_metric.close_rate = Some(connection_close_rate);
            
            // Send V2 metric
            self.metrics_tx.send(v2_metric).await?;
        }

        self.last_net_stats = Some(current_stats);
        Ok(())
    }

    /// Collect TCP flow data for "Active Flows" feature
    /// Parses /proc/net/tcp to get active connections and sends as tcp_flow metrics
    async fn collect_tcp_flows(&self, timestamp: i64, tags: &HashMap<String, String>) -> Result<()> {
        // Read /proc/net/tcp (try host path first)
        let tcp_content = match fs::read_to_string("/host/proc/net/tcp").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/proc/net/tcp").await.unwrap_or_default(),
        };
        
        // Also read tcp6 for IPv6 connections
        let tcp6_content = match fs::read_to_string("/host/proc/net/tcp6").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/proc/net/tcp6").await.unwrap_or_default(),
        };

        // Read UDP connections
        let udp_content = match fs::read_to_string("/host/proc/net/udp").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/proc/net/udp").await.unwrap_or_default(),
        };
        
        let udp6_content = match fs::read_to_string("/host/proc/net/udp6").await {
            Ok(content) => content,
            Err(_) => fs::read_to_string("/proc/net/udp6").await.unwrap_or_default(),
        };

        // Parse TCP connections and aggregate by remote address
        let mut flow_map: HashMap<String, (u64, String)> = HashMap::new(); // key: remote_ip:port, value: (count, state)
        
        fn parse_net_line(line: &str, flow_map: &mut HashMap<String, (u64, String)>, is_udp: bool) {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() < 4 {
                return;
            }
            
            // Format: sl local_address rem_address st ...
            // Addresses are in hex: IP:PORT (little endian for IP)
            let remote_hex = parts[2];
            let state_hex = parts[3];
            
            // Parse remote address
            if let Some((ip_hex, port_hex)) = remote_hex.split_once(':') {
                // Convert hex port
                let port = u16::from_str_radix(port_hex, 16).unwrap_or(0);
                if port == 0 {
                    return; // Skip listening sockets
                }
                
                // Convert hex IP (little endian for IPv4)
                let ip = if ip_hex.len() == 8 {
                    // IPv4
                    let ip_num = u32::from_str_radix(ip_hex, 16).unwrap_or(0);
                    format!("{}.{}.{}.{}", 
                        ip_num & 0xFF, 
                        (ip_num >> 8) & 0xFF,
                        (ip_num >> 16) & 0xFF,
                        (ip_num >> 24) & 0xFF
                    )
                } else {
                    // IPv6 - simplified, just use hex for now
                    format!("ipv6:{}", &ip_hex[..16.min(ip_hex.len())])
                };
                
                // Skip invalid 0.0.0.0 addresses (usually listening sockets misparsed or similar)
                if ip == "0.0.0.0" {
                    return;
                }
                
                // Parse state
                let state = if is_udp {
                    "UDP".to_string()
                } else {
                    match state_hex {
                        "01" => "ESTABLISHED".to_string(),
                        "02" => "SYN_SENT".to_string(),
                        "03" => "SYN_RECV".to_string(),
                        "04" => "FIN_WAIT1".to_string(),
                        "05" => "FIN_WAIT2".to_string(),
                        "06" => "TIME_WAIT".to_string(),
                        "07" => "CLOSE".to_string(),
                        "08" => "CLOSE_WAIT".to_string(),
                        "09" => "LAST_ACK".to_string(),
                        "0A" => "LISTEN".to_string(),
                        _ => "UNKNOWN".to_string(),
                    }
                };
                
                let key = format!("{}:{}", ip, port);
                flow_map.entry(key)
                    .and_modify(|(count, _)| *count += 1)
                    .or_insert((1, state));
            }
        }
        
        // Parse IPv4 TCP
        for line in tcp_content.lines().skip(1) {
            parse_net_line(line, &mut flow_map, false);
        }
        
        // Parse IPv6 TCP
        for line in tcp6_content.lines().skip(1) {
            parse_net_line(line, &mut flow_map, false);
        }

        // Parse IPv4 UDP
        for line in udp_content.lines().skip(1) {
            parse_net_line(line, &mut flow_map, true);
        }

        // Parse IPv6 UDP
        for line in udp6_content.lines().skip(1) {
            parse_net_line(line, &mut flow_map, true);
        }
        
        // Calculate counts
        let mut close_wait_count = 0u64;
        let mut established_count = 0u64;
        let mut active_count = 0u64;
        
        for (_, (_, state)) in &flow_map {
            active_count += 1;
            if state == "CLOSE_WAIT" {
                close_wait_count += 1;
            } else if state == "ESTABLISHED" {
                established_count += 1;
            }
        }
        
        // Send these specific metrics
        self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_close_wait".to_string(), close_wait_count as f64, tags.clone())).await?;
        self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_established".to_string(), established_count as f64, tags.clone())).await?;
        
        // IMPORTANT: Override the "active_connections" metric (which might be estimated from /proc/net/snmp) with our concrete flow count
        // This resolves the issue where only TCP stats from SNMP were being used.
        self.metrics_tx.send(Metric::new_basic(timestamp, self.hostname.clone(), "network".to_string(), "network_active_connections_detailed".to_string(), active_count as f64, tags.clone())).await?;
        
        // Sort by connection count and take top 50
        let mut flows: Vec<_> = flow_map.into_iter().collect();
        flows.sort_by(|a, b| b.1.0.cmp(&a.1.0));
        
        info!("[NET FLOWS] Found {} unique remote endpoints (TCP+UDP), sending top {}", flows.len(), flows.len().min(50));
        
        // Send top 50 flows as tcp_flow metrics (keeping name strict for compatibility but now includes UDP)
        for (idx, (remote, (count, state))) in flows.iter().take(50).enumerate() {
            let parts: Vec<&str> = remote.split(':').collect();
            let remote_ip = parts.get(0).unwrap_or(&"unknown");
            let remote_port = parts.get(1).unwrap_or(&"0");
            
            let mut flow_tags = tags.clone();
            flow_tags.insert("remote_ip".to_string(), remote_ip.to_string());
            flow_tags.insert("remote_port".to_string(), remote_port.to_string());
            flow_tags.insert("state".to_string(), state.clone());
            flow_tags.insert("rank".to_string(), (idx + 1).to_string());
            
            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "network".to_string(),
                "tcp_flow".to_string(),
                *count as f64,
                flow_tags,
            )).await?;
        }
        
        info!("[TCP FLOWS] ✓ Sent {} tcp_flow metrics", flows.len().min(50));
        Ok(())
    }

    /// Collect per-process network bandwidth for "Bandwidth by Process" feature
    /// Scans processes with network sockets and gets their network I/O stats
    async fn collect_process_bandwidth(&self, timestamp: i64, tags: &HashMap<String, String>) -> Result<()> {
        let proc_path = if std::path::Path::new("/host/proc").exists() {
            "/host/proc"
        } else {
            "/proc"
        };
        
        // Collect processes with network activity
        let mut process_network: HashMap<String, (u32, u64, u64, u32)> = HashMap::new(); // name -> (pid, bytes_sent, bytes_recv, socket_count)
        const MAX_NETWORK_PROCESSES: usize = 50;
        
        // Read process directories
        let proc_dir = match std::fs::read_dir(proc_path) {
            Ok(dir) => dir,
            Err(e) => {
                tracing::warn!("[PROCESS BANDWIDTH] Failed to read {}: {}", proc_path, e);
                return Ok(());
            }
        };
        
        for entry in proc_dir {
            if process_network.len() >= MAX_NETWORK_PROCESSES {
                break;
            }
            
            let entry = match entry {
                Ok(e) => e,
                Err(_) => continue,
            };
            
            let file_name = entry.file_name();
            let pid_str = file_name.to_string_lossy();
            
            // Only process numeric directories (PIDs)
            let pid: u32 = match pid_str.parse() {
                Ok(p) => p,
                Err(_) => continue,
            };
            
            // Check if process has socket file descriptors
            let fd_path = format!("{}/{}/fd", proc_path, pid);
            let socket_count = match std::fs::read_dir(&fd_path) {
                Ok(fd_dir) => {
                    fd_dir.filter_map(|e| e.ok())
                        .filter_map(|e| std::fs::read_link(e.path()).ok())
                        .filter(|link| link.to_string_lossy().contains("socket:"))
                        .count() as u32
                }
                Err(_) => continue, // No permission or doesn't exist
            };
            
            if socket_count == 0 {
                continue; // Skip processes without network sockets
            }
            
            // Get process name
            let comm_path = format!("{}/{}/comm", proc_path, pid);
            let process_name = match std::fs::read_to_string(&comm_path) {
                Ok(name) => name.trim().chars().take(15).collect::<String>(),
                Err(_) => "unknown".to_string(),
            };
            
            // Get network I/O stats from /proc/{pid}/net/dev
            let net_dev_path = format!("{}/{}/net/dev", proc_path, pid);
            let (bytes_sent, bytes_recv) = match std::fs::read_to_string(&net_dev_path) {
                Ok(content) => {
                    let mut total_sent = 0u64;
                    let mut total_recv = 0u64;
                    
                    for line in content.lines().skip(2) { // Skip headers
                        let parts: Vec<&str> = line.split_whitespace().collect();
                        if parts.len() >= 10 {
                            let interface = parts[0].trim_end_matches(':');
                            if interface != "lo" { // Skip loopback
                                total_recv += parts[1].parse::<u64>().unwrap_or(0);
                                total_sent += parts[9].parse::<u64>().unwrap_or(0);
                            }
                        }
                    }
                    (total_sent, total_recv)
                }
                Err(_) => (0, 0),
            };
            
            // Aggregate by process name
            process_network.entry(process_name.clone())
                .and_modify(|(_, sent, recv, sockets)| {
                    *sent += bytes_sent;
                    *recv += bytes_recv;
                    *sockets += socket_count;
                })
                .or_insert((pid, bytes_sent, bytes_recv, socket_count));
        }
        
        info!("[PROCESS BANDWIDTH] Found {} processes with network activity", process_network.len());
        
        // Sort by total bytes and send top 20
        let mut sorted: Vec<_> = process_network.into_iter().collect();
        sorted.sort_by(|a, b| (b.1.1 + b.1.2).cmp(&(a.1.1 + a.1.2)));
        
        for (idx, (name, (pid, bytes_sent, bytes_recv, sockets))) in sorted.iter().take(20).enumerate() {
            let mut bw_tags = tags.clone();
            bw_tags.insert("process_name".to_string(), name.clone());
            bw_tags.insert("pid".to_string(), pid.to_string());
            bw_tags.insert("rank".to_string(), (idx + 1).to_string());
            bw_tags.insert("sockets".to_string(), sockets.to_string());
            bw_tags.insert("bytes_sent".to_string(), bytes_sent.to_string());
            bw_tags.insert("bytes_received".to_string(), bytes_recv.to_string());
            
            let total_bytes = *bytes_sent + *bytes_recv;
            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "network".to_string(),
                "process_network_bandwidth".to_string(),
                total_bytes as f64,
                bw_tags,
            )).await?;
        }
        
        info!("[PROCESS BANDWIDTH] ✓ Sent {} process_network_bandwidth metrics", sorted.len().min(20));
        Ok(())
    }

    async fn collect_top_processes(&mut self, timestamp: i64, tags: &HashMap<String, String>) -> Result<()> {
        info!("[TOP PROCESSES] Starting collection at timestamp {}", timestamp);
        
        // Refresh processes to get current stats
        // Note: sysinfo needs multiple refreshes to calculate CPU usage accurately
        // First refresh to establish baseline
        info!("[TOP PROCESSES] First refresh...");
        self.system.refresh_processes();
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        // Second refresh to calculate CPU usage
        info!("[TOP PROCESSES] Second refresh...");
        self.system.refresh_processes();
        
        let mut cpu_processes: Vec<(f32, String, u32, String)> = Vec::new();
        let mut memory_processes: Vec<(u64, String, u32, String)> = Vec::new();
        
        // Collect CPU and memory usage for all processes
        info!("[TOP PROCESSES] Iterating through processes...");
        let mut process_count = 0;
        let mut host_process_count = 0;
        for (pid, process) in self.system.processes() {
            process_count += 1;
            let cpu_usage = process.cpu_usage();
            let memory_usage = process.memory();
            let name = process.name().to_string();
            
            // Verify we're seeing host processes (not just container processes)
            // Host processes typically include systemd, kernel threads, etc.
            let name_lower = name.to_lowercase();
            if name_lower.contains("systemd") || name_lower.contains("kthreadd") || 
               name_lower.contains("ksoftirqd") || name_lower.contains("dockerd") ||
               pid.as_u32() == 1 {  // PID 1 on host is usually systemd/init
                host_process_count += 1;
            }
            
            // Get full command line
            let cmd_line = process.cmd().join(" ");
            // Limit command line length to avoid huge tags (max 500 chars)
            let cmd_line_short = if cmd_line.len() > 500 {
                format!("{}...", &cmd_line[..497])
            } else {
                cmd_line
            };
            
            // Collect all processes, even with 0 CPU (we'll sort and take top)
            // This ensures we get processes even if CPU is low
            cpu_processes.push((cpu_usage, name.clone(), pid.as_u32(), cmd_line_short.clone()));
            
            if memory_usage > 0 {
                memory_processes.push((memory_usage, name, pid.as_u32(), cmd_line_short));
            }
        }
        
        info!("[TOP PROCESSES] Processed {} total processes ({} host processes detected)", process_count, host_process_count);
        if host_process_count == 0 && process_count < 20 {
            tracing::warn!("[TOP PROCESSES] ⚠️  WARNING: Only {} processes found, may be reading from container instead of host!", process_count);
            tracing::warn!("[TOP PROCESSES] ⚠️  Ensure docker-compose.yml has 'pid: host' for agent service");
        }
        info!("[TOP PROCESSES] Collected {} CPU processes, {} memory processes", cpu_processes.len(), memory_processes.len());
        
        // Sort and get top 3
        cpu_processes.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
        memory_processes.sort_by(|a, b| b.0.cmp(&a.0));
        
        info!("Top CPU process: {} ({}%), Top Memory: {} ({} MB)", 
            cpu_processes.first().map(|p| p.1.as_str()).unwrap_or("none"),
            cpu_processes.first().map(|p| p.0).unwrap_or(0.0),
            memory_processes.first().map(|p| p.1.as_str()).unwrap_or("none"),
            memory_processes.first().map(|p| p.2).unwrap_or(0) / 1024 / 1024
        );
        
        // Store top 3 CPU processes (even if CPU is 0, we still want to track them)
        info!("[TOP PROCESSES] Storing top {} CPU processes", cpu_processes.len().min(3));
        for (idx, (cpu, name, pid, cmd_line)) in cpu_processes.iter().take(3).enumerate() {
            info!("[TOP PROCESSES] Sending CPU process metric #{}: {} (PID: {}) = {:.2}%", idx + 1, name, pid, cpu);
            let mut process_tags = tags.clone();
            process_tags.insert("process_name".to_string(), name.clone());
            process_tags.insert("pid".to_string(), pid.to_string());
            process_tags.insert("rank".to_string(), (idx + 1).to_string());
            process_tags.insert("command_line".to_string(), cmd_line.clone());
            
            match self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "process".to_string(),
                "process_cpu_usage".to_string(),
                *cpu as f64,
                process_tags,
            )).await {
                Ok(_) => info!("[TOP PROCESSES] ✓ Sent CPU metric for {}", name),
                Err(e) => {
                    tracing::error!("[TOP PROCESSES] Failed to send CPU metric for {}: {}", name, e);
                    return Err(anyhow::anyhow!("Failed to send CPU metric: {}", e));
                }
            }
        }
        
        // Store top 3 memory processes
        info!("[TOP PROCESSES] Storing top {} memory processes", memory_processes.len().min(3));
        for (idx, (memory, name, pid, cmd_line)) in memory_processes.iter().take(3).enumerate() {
            info!("[TOP PROCESSES] Sending memory process metric #{}: {} (PID: {}) = {} MB", idx + 1, name, pid, memory / 1024 / 1024);
            let mut process_tags = tags.clone();
            process_tags.insert("process_name".to_string(), name.clone());
            process_tags.insert("pid".to_string(), pid.to_string());
            process_tags.insert("rank".to_string(), (idx + 1).to_string());
            process_tags.insert("command_line".to_string(), cmd_line.clone());
            
            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "process".to_string(),
                "process_memory_mb".to_string(),
                (*memory / 1024 / 1024) as f64,
                process_tags,
            )).await?;
        }
        
        // For disk I/O and network, we'll collect from /proc/<pid>/io
        // This is more complex, so we'll do a simplified version
        // Collect top processes by reading /proc/<pid>/io for disk I/O
        let mut disk_io_processes: Vec<(u64, String, u32, String)> = Vec::new();
        
        for (pid, process) in self.system.processes() {
            let name = process.name().to_string();
            let pid_num = pid.as_u32();
            
            // Get full command line
            let cmd_line = process.cmd().join(" ");
            let cmd_line_short = if cmd_line.len() > 500 {
                format!("{}...", &cmd_line[..497])
            } else {
                cmd_line
            };
            
            // Try to read /proc/<pid>/io for disk I/O stats
            // Note: Agent runs in container with /proc mounted at /host/proc, so we read from host
            let io_path = format!("/host/proc/{}/io", pid_num);
            if let Ok(io_content) = fs::read_to_string(&io_path).await {
                let mut read_bytes = 0u64;
                let mut write_bytes = 0u64;
                
                for line in io_content.lines() {
                    if line.starts_with("read_bytes:") {
                        if let Some(val_str) = line.split_whitespace().nth(1) {
                            if let Ok(val) = val_str.parse::<u64>() {
                                read_bytes = val;
                            }
                        }
                    } else if line.starts_with("write_bytes:") {
                        if let Some(val_str) = line.split_whitespace().nth(1) {
                            if let Ok(val) = val_str.parse::<u64>() {
                                write_bytes = val;
                            }
                        }
                    }
                }
                
                let total_io = read_bytes + write_bytes;
                if total_io > 0 {
                    disk_io_processes.push((total_io, name, pid_num, cmd_line_short));
                }
            }
        }
        
        disk_io_processes.sort_by(|a, b| b.0.cmp(&a.0));
        
        info!("[TOP PROCESSES] Found {} disk I/O processes, storing top 3", disk_io_processes.len());
        // Store top 3 disk I/O processes
        for (idx, (io_bytes, name, pid, cmd_line)) in disk_io_processes.iter().take(3).enumerate() {
            info!("[TOP PROCESSES] Sending disk I/O process metric #{}: {} (PID: {}) = {} MB", idx + 1, name, pid, io_bytes / 1024 / 1024);
            let mut process_tags = tags.clone();
            process_tags.insert("process_name".to_string(), name.clone());
            process_tags.insert("pid".to_string(), pid.to_string());
            process_tags.insert("rank".to_string(), (idx + 1).to_string());
            process_tags.insert("command_line".to_string(), cmd_line.clone());
            
            self.metrics_tx.send(Metric::new_basic(
                timestamp,
                self.hostname.clone(),
                "process".to_string(),
                "process_disk_io_mb".to_string(),
                (*io_bytes / 1024 / 1024) as f64,
                process_tags,
            )).await?;
        }
        
        // For network, we'll use a simplified approach - track processes that might be network-intensive
        // This is harder to get per-process, so we'll skip it for now or use a heuristic
        // (e.g., processes with many open network connections)
        
        info!("[TOP PROCESSES] ✓ Collection complete - CPU: {}, Memory: {}, DiskIO: {}", 
            cpu_processes.len().min(3), 
            memory_processes.len().min(3),
            disk_io_processes.len().min(3)
        );
        Ok(())
    }
}

#[derive(Clone)]
struct DiskStats {
    reads: u64,
    writes: u64,
    read_sectors: u64,
    write_sectors: u64,
    io_time_ms: u64,
}

#[derive(Clone)]
struct NetStats {
    rx_bytes: u64,
    tx_bytes: u64,
    rx_packets: u64,
    tx_packets: u64,
    rx_drops: u64,
    tx_drops: u64,
    active_opens: u64,
    passive_opens: u64,
    established: u64,
    retransmits: u64,
    softirq: u64,
    system_cpu: u64,
    socket_pressure: u64,
    total_cpu: u64,
}


