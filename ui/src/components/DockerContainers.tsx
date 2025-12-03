import React, { useEffect, useState } from 'react';
import { Box, Server, Activity, Clock, RefreshCw, AlertCircle, Play, Square, Pause } from 'lucide-react';
import styles from './DockerContainers.module.css';

interface Container {
  id: string;
  name: string;
  image: string;
  status: string;
  cpu_percent: number;
  memory_usage: number;
  memory_limit: number;
  memory_percent: number;
  network_rx_bytes: number;
  network_tx_bytes: number;
  block_read_bytes: number;
  block_write_bytes: number;
  uptime_seconds: number;
  restart_count: number;
  created_at: string;
  last_seen: string;
  hostname: string;
}

interface DockerContainersProps {
  selectedServer: string | null;
}

export const DockerContainers: React.FC<DockerContainersProps> = ({ selectedServer }) => {
  const [containers, setContainers] = useState<Container[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const fetchContainers = async () => {
    try {
      const url = selectedServer 
        ? `/api/containers/current?hostname=${encodeURIComponent(selectedServer)}`
        : '/api/containers/current';
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Failed to fetch container stats');
      }
      const data = await response.json();
      setContainers(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error('Error fetching containers:', err);
      setError('Failed to load container data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContainers();
    const interval = setInterval(fetchContainers, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, [selectedServer]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  };

  const getStatusClass = (status: string) => {
    const baseClass = styles.statusBadge;
    switch (status.toLowerCase()) {
      case 'running': return `${baseClass} ${styles.statusBadgeRunning}`;
      case 'exited': return `${baseClass} ${styles.statusBadgeExited}`;
      case 'restarting': return `${baseClass} ${styles.statusBadgeRestarting}`;
      case 'dead': return `${baseClass} ${styles.statusBadgeDead}`;
      case 'paused': return `${baseClass} ${styles.statusBadgePaused}`;
      default: return `${baseClass} ${styles.statusBadgeExited}`;
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running': return <Play className="w-3 h-3 fill-current" />;
      case 'exited': return <Square className="w-3 h-3 fill-current" />;
      case 'paused': return <Pause className="w-3 h-3 fill-current" />;
      case 'restarting': return <RefreshCw className="w-3 h-3" />;
      default: return <AlertCircle className="w-3 h-3" />;
    }
  };

  if (loading && containers.length === 0) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.sectionSpacing}>
          <div className={styles.loadingTitle}></div>
          <div className={styles.loadingGrid}>
            {[1, 2, 3].map(i => (
              <div key={i} className={styles.loadingCard}></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.sectionSpacing}>
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>
          <Box className={styles.sectionTitleIcon} />
          Docker Containers
          <span className={styles.sectionCount}>
            ({containers.length} total, {containers.filter(c => c.status === 'running').length} running)
          </span>
        </h2>
        <div className={styles.sectionUpdateTime}>
          <Clock className={styles.updateIcon} />
          Updated: {lastUpdated.toLocaleTimeString()}
        </div>
      </div>

      {error && (
        <div className={styles.errorMessage}>
          <AlertCircle className={styles.errorIcon} />
          {error}
        </div>
      )}

      {containers.length === 0 && !loading && (
        <div className="p-4 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400">
          No containers found
        </div>
      )}

      {containers.length > 0 && (
        <div className={styles.containersGrid}>
          {containers.map(container => (
            <div 
              key={container.id}
              className={`${styles.containerCard} ${
                container.status === 'running' ? styles.containerCardRunning : styles.containerCardStopped
              }`}
            >
            {/* Header */}
            <div className={styles.containerHeader}>
              <div className={styles.containerHeaderTop}>
                <h3 
                  className={styles.containerName} 
                  title={container.name || container.id}
                >
                  {container.name ? container.name.replace(/^\//, '') : container.id.substring(0, 12)}
                </h3>
                <div className={getStatusClass(container.status)}>
                  {getStatusIcon(container.status)}
                  <span className={`${styles.statusText} ${styles.statusTextHidden}`}>{container.status}</span>
                </div>
              </div>
              <p 
                className={styles.containerImage} 
                title={container.image}
              >
                {container.image || 'unknown'}
              </p>
            </div>

            {/* Stats Grid */}
            <div className={styles.statsSection}>
              {/* CPU & Memory */}
              <div className={styles.statsMetrics}>
                <div>
                  <div className={styles.metricRow}>
                    <span className={styles.metricLabel}>CPU Usage</span>
                    <span className={`${styles.metricValue} ${container.cpu_percent > 80 ? styles.metricValueWarning : ''}`}>
                      {container.cpu_percent.toFixed(1)}%
                    </span>
                  </div>
                  <div className={styles.progressBarContainer}>
                    <div 
                      className={`${styles.progressBar} ${
                        container.cpu_percent > 80 ? styles.progressBarDanger : 
                        container.cpu_percent > 50 ? styles.progressBarWarning : styles.progressBarSafe
                      }`}
                      style={{ width: `${Math.min(container.cpu_percent, 100)}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className={styles.metricRow}>
                    <span className={styles.metricLabel}>Memory</span>
                    <span className={`${styles.metricValue} ${container.memory_percent > 80 ? styles.metricValueWarning : ''}`}>
                      {formatBytes(container.memory_usage)} / {formatBytes(container.memory_limit)}
                    </span>
                  </div>
                  <div className={styles.progressBarContainer}>
                    <div 
                      className={`${styles.progressBar} ${
                        container.memory_percent > 80 ? styles.progressBarDanger : 
                        container.memory_percent > 50 ? styles.progressBarWarning : styles.progressBarMemory
                      }`}
                      style={{ width: `${Math.min(container.memory_percent, 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Network & I/O */}
              <div className={styles.networkIOSection}>
                <div className={styles.ioColumn}>
                  <p className={styles.ioLabel}>Network I/O</p>
                  <p className={styles.ioValue}>
                    ↓{formatBytes(container.network_rx_bytes)}
                  </p>
                  <p className={styles.ioValue}>
                    ↑{formatBytes(container.network_tx_bytes)}
                  </p>
                </div>
                <div className={styles.ioColumn}>
                  <p className={styles.ioLabel}>Block I/O</p>
                  <p className={styles.ioValue}>
                    R: {formatBytes(container.block_read_bytes)}
                  </p>
                  <p className={styles.ioValue}>
                    W: {formatBytes(container.block_write_bytes)}
                  </p>
                </div>
              </div>

              {/* Footer Info */}
              <div className={styles.footerSection}>
                <div className={styles.footerItem} title={`Uptime: ${formatUptime(container.uptime_seconds)}`}>
                  <Activity className="w-3 h-3" />
                  <span className={styles.footerLabel}>Uptime:</span>
                  <span className={styles.footerValue}>{formatUptime(container.uptime_seconds)}</span>
                </div>
                <div className={styles.footerItem} title={`Restart Count: ${container.restart_count}`}>
                  <RefreshCw className="w-3 h-3" />
                  <span className={styles.footerValue}>{container.restart_count}</span>
                </div>
              </div>
              
              {/* Container ID (small, for reference) */}
              {container.id && (
                <div className={styles.containerIdSection}>
                  <p className={styles.containerId} title={container.id}>
                    ID: {container.id.substring(0, 12)}...
                  </p>
                </div>
              )}
            </div>
          </div>
          ))}
        </div>
      )}
    </div>
  );
};

