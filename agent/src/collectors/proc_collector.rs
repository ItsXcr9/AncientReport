use anyhow::Result;
use sysinfo::{System, Disks};
use tokio::sync::mpsc;
use tokio::time::{interval, Duration};
use tokio::fs;
use tracing::info;
use std::collections::HashMap;

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
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "cpu_usage_percent".to_string(),
            value: cpu_usage as f64,
            tags: tags.clone(),
        }).await?;

        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "cpu_cores".to_string(),
            value: cpu_count as f64,
            tags: tags.clone(),
        }).await?;

        // Collect memory metrics
        let total_memory = self.system.total_memory();
        let used_memory = self.system.used_memory();
        let memory_percent = (used_memory as f64 / total_memory as f64) * 100.0;
        info!("Memory usage: {:.2}% ({} MB / {} MB)", 
            memory_percent, 
            used_memory / 1024 / 1024,
            total_memory / 1024 / 1024
        );
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "memory_usage_percent".to_string(),
            value: memory_percent,
            tags: tags.clone(),
        }).await?;
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "memory_used_mb".to_string(),
            value: (used_memory / 1024 / 1024) as f64,
            tags: tags.clone(),
        }).await?;

        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "memory_total_mb".to_string(),
            value: (total_memory / 1024 / 1024) as f64,
            tags: tags.clone(),
        }).await?;

        // Collect load average
        let load_avg = System::load_average();
        info!("Load average: {:.2}, {:.2}, {:.2}", 
            load_avg.one, load_avg.five, load_avg.fifteen
        );
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "load_avg_1min".to_string(),
            value: load_avg.one,
            tags: tags.clone(),
        }).await?;
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "load_avg_5min".to_string(),
            value: load_avg.five,
            tags: tags.clone(),
        }).await?;
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "load_avg_15min".to_string(),
            value: load_avg.fifteen,
            tags: tags.clone(),
        }).await?;

        // Collect process count
        let process_count = self.system.processes().len();
        info!("Process count: {}", process_count);
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "process_count".to_string(),
            value: process_count as f64,
            tags: tags.clone(),
        }).await?;

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
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "disk_total_gb".to_string(),
            value: (total_space / 1024 / 1024 / 1024) as f64,
            tags: tags.clone(),
        }).await?;
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "disk_used_gb".to_string(),
            value: (used_space / 1024 / 1024 / 1024) as f64,
            tags: tags.clone(),
        }).await?;
        
        self.metrics_tx.send(Metric {
            timestamp,
            hostname: self.hostname.clone(),
            metric_type: "system".to_string(),
            metric_name: "disk_usage_percent".to_string(),
            value: disk_usage_percent,
            tags: tags.clone(),
        }).await?;

        // Collect disk I/O metrics
        if let Err(e) = self.collect_disk_io(timestamp, &tags).await {
            tracing::warn!("Failed to collect disk I/O metrics: {}", e);
        }

        // Collect network metrics
        if let Err(e) = self.collect_network(timestamp, &tags).await {
            tracing::warn!("Failed to collect network metrics: {}", e);
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

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "disk".to_string(),
                metric_name: "disk_reads_per_sec".to_string(),
                value: reads_per_sec,
                tags: tags.clone(),
            }).await?;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "disk".to_string(),
                metric_name: "disk_writes_per_sec".to_string(),
                value: writes_per_sec,
                tags: tags.clone(),
            }).await?;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "disk".to_string(),
                metric_name: "disk_latency_ms".to_string(),
                value: latency_ms,
                tags: tags.clone(),
            }).await?;
        }

        self.last_disk_stats = Some(current_stats);
        Ok(())
    }

    async fn collect_network(&mut self, timestamp: i64, tags: &HashMap<String, String>) -> Result<()> {
        // Read /proc/net/dev
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
            // Skip header lines
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 10 {
                // Format: interface rx_bytes rx_packets rx_errs rx_drop rx_fifo rx_frame rx_compressed rx_multicast tx_bytes tx_packets ...
                if let (Ok(rx_bytes), Ok(rx_packets), Ok(rx_drops), Ok(tx_bytes), Ok(tx_packets), Ok(tx_drops)) = (
                    parts[1].parse::<u64>(),
                    parts[2].parse::<u64>(),
                    parts[4].parse::<u64>(),
                    parts[9].parse::<u64>(),
                    parts[10].parse::<u64>(),
                    parts[12].parse::<u64>(),
                ) {
                    // Skip loopback
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

        let current_stats = NetStats {
            rx_bytes: total_rx_bytes,
            tx_bytes: total_tx_bytes,
            rx_packets: total_rx_packets,
            tx_packets: total_tx_packets,
            rx_drops: total_rx_drops,
            tx_drops: total_tx_drops,
        };

        // Calculate per-second rates if we have previous stats
        if let Some(ref last_stats) = self.last_net_stats {
            let time_diff = 60.0; // 60 seconds (1 minute) between collections
            let packets_sent_per_sec = ((current_stats.tx_packets.saturating_sub(last_stats.tx_packets)) as f64) / time_diff;
            let packets_received_per_sec = ((current_stats.rx_packets.saturating_sub(last_stats.rx_packets)) as f64) / time_diff;
            let bytes_sent_per_sec = ((current_stats.tx_bytes.saturating_sub(last_stats.tx_bytes)) as f64) / time_diff;
            let bytes_received_per_sec = ((current_stats.rx_bytes.saturating_sub(last_stats.rx_bytes)) as f64) / time_diff;
            let drops = current_stats.rx_drops + current_stats.tx_drops;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "network".to_string(),
                metric_name: "network_packets_sent".to_string(),
                value: packets_sent_per_sec,
                tags: tags.clone(),
            }).await?;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "network".to_string(),
                metric_name: "network_packets_received".to_string(),
                value: packets_received_per_sec,
                tags: tags.clone(),
            }).await?;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "network".to_string(),
                metric_name: "network_bytes_sent".to_string(),
                value: bytes_sent_per_sec,
                tags: tags.clone(),
            }).await?;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "network".to_string(),
                metric_name: "network_bytes_received".to_string(),
                value: bytes_received_per_sec,
                tags: tags.clone(),
            }).await?;

            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "network".to_string(),
                metric_name: "network_drops".to_string(),
                value: drops as f64,
                tags: tags.clone(),
            }).await?;
        }

        self.last_net_stats = Some(current_stats);
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
            
            match self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "process".to_string(),
                metric_name: "process_cpu_usage".to_string(),
                value: *cpu as f64,
                tags: process_tags,
            }).await {
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
            
            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "process".to_string(),
                metric_name: "process_memory_mb".to_string(),
                value: (*memory / 1024 / 1024) as f64,
                tags: process_tags,
            }).await?;
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
            
            self.metrics_tx.send(Metric {
                timestamp,
                hostname: self.hostname.clone(),
                metric_type: "process".to_string(),
                metric_name: "process_disk_io_mb".to_string(),
                value: (*io_bytes / 1024 / 1024) as f64,
                tags: process_tags,
            }).await?;
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
}


