# CPU and System Resource Metrics

## CPU Usage Explained

The `cpu_usage_percent` metric represents **overall CPU usage across all cores** as a percentage (0-100%).

- **50% on a 4-core system** = Overall 50% utilization across all cores
- This is equivalent to **2 out of 4 cores** being fully utilized, or all 4 cores at 50% each

## New Metrics Added

### System Resources (Now Collected):
1. **`cpu_cores`**: Number of CPU cores on the system
2. **`cpu_usage_percent`**: Overall CPU usage percentage (0-100%)
3. **`load_avg_1min`**, **`load_avg_5min`**, **`load_avg_15min`**: System load averages
4. **`memory_total_mb`**: Total system memory in MB
5. **`memory_used_mb`**: Used memory in MB  
6. **`memory_usage_percent`**: Memory usage percentage
7. **`disk_total_gb`**: Total disk space in GB (physical disks only)
8. **`disk_used_gb`**: Used disk space in GB
9. **`disk_usage_percent`**: Disk usage percentage
10. **`process_count`**: Number of running processes

### Process Metrics:
- **`process_cpu_usage`**: Per-process CPU usage
- **`process_memory_mb`**: Per-process memory usage
- **`process_disk_io_mb`**: Per-process disk I/O

## Where to Display

In the UI, you should display a "System Information" card showing:
- **CPU**: 8 cores @ 45% usage
- **Memory**: 16 GB / 32 GB (50%)
- **Disk**: 250 GB / 500 GB (50%)  
- **Load**: 2.5, 1.8, 1.2 (1m, 5m, 15m)
- **Processes**: 245 running

This gives a complete overview of system resources at a glance.
