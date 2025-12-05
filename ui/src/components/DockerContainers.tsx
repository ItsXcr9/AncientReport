import React, { useEffect, useState } from 'react';
import { Box, Activity, Clock, RefreshCw, AlertCircle, Play, Square, Pause, ChevronDown, ChevronUp, Cpu, HardDrive } from 'lucide-react';
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
  const [showAll, setShowAll] = useState(false);
  const [sortBy, setSortBy] = useState<'cpu' | 'memory'>('cpu');

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
    const interval = setInterval(fetchContainers, 10000);
    return () => clearInterval(interval);
  }, [selectedServer]);

  // Sort containers by CPU or memory usage (high to low)
  const sortedContainers = [...containers].sort((a, b) => {
    if (sortBy === 'cpu') {
      return b.cpu_percent - a.cpu_percent;
    }
    return b.memory_percent - a.memory_percent;
  });

  // Split into top 5 and rest
  const topContainers = sortedContainers.slice(0, 5);
  const otherContainers = sortedContainers.slice(5);

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

  const ContainerCard = ({ container, compact = false }: { container: Container; compact?: boolean }) => (
    <div 
      className={`${styles.containerCard} ${
        container.status === 'running' ? styles.containerCardRunning : styles.containerCardStopped
      } ${compact ? 'p-3' : ''}`}
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
        {!compact && (
          <p 
            className={styles.containerImage} 
            title={container.image}
          >
            {container.image || 'unknown'}
          </p>
        )}
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

        {!compact && (
          <>
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
            
            {/* Container ID */}
            {container.id && (
              <div className={styles.containerIdSection}>
                <p className={styles.containerId} title={container.id}>
                  ID: {container.id.substring(0, 12)}...
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );

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
        <div className="flex items-center gap-4">
          {/* Sort Toggle */}
          <div className="flex items-center gap-2 bg-white/5 rounded-lg p-1">
            <button
              onClick={() => setSortBy('cpu')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                sortBy === 'cpu' ? 'bg-neon-blue/20 text-neon-blue' : 'text-gray-400 hover:bg-white/5'
              }`}
            >
              <Cpu className="w-3 h-3" />
              CPU
            </button>
            <button
              onClick={() => setSortBy('memory')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                sortBy === 'memory' ? 'bg-neon-purple/20 text-neon-purple' : 'text-gray-400 hover:bg-white/5'
              }`}
            >
              <HardDrive className="w-3 h-3" />
              Memory
            </button>
          </div>
          <div className={styles.sectionUpdateTime}>
            <Clock className={styles.updateIcon} />
            Updated: {lastUpdated.toLocaleTimeString()}
          </div>
        </div>
      </div>

      {error && (
        <div className={styles.errorMessage}>
          <AlertCircle className={styles.errorIcon} />
          {error}
        </div>
      )}

      {containers.length === 0 && !loading && (
        <div className="p-4 glass-panel rounded-lg text-center text-gray-400">
          No containers found
        </div>
      )}

      {containers.length > 0 && (
        <>
          {/* Top 5 Containers */}
          <div className={styles.containersGrid}>
            {topContainers.map((container, index) => (
              <div key={container.id} className="relative">
                {/* Rank Badge */}
                <div className={`absolute -top-2 -left-2 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold z-10 ${
                  index === 0 ? 'bg-yellow-500 text-black' :
                  index === 1 ? 'bg-gray-300 text-black' :
                  index === 2 ? 'bg-amber-600 text-white' :
                  'bg-gray-600 text-white'
                }`}>
                  {index + 1}
                </div>
                <ContainerCard container={container} />
              </div>
            ))}
          </div>

          {/* Other Containers - Expandable */}
          {otherContainers.length > 0 && (
            <div className="mt-4">
              <button
                onClick={() => setShowAll(!showAll)}
                className="w-full flex items-center justify-between px-4 py-3 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 transition-colors"
              >
                <span className="text-sm text-gray-400">
                  {showAll ? 'Hide' : 'Show'} {otherContainers.length} more container{otherContainers.length > 1 ? 's' : ''}
                </span>
                {showAll ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </button>
              
              {showAll && (
                <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-white/10">
                  <div className="space-y-2 p-3">
                    {otherContainers.map((container, index) => (
                      <div 
                        key={container.id}
                        className="flex items-center gap-4 p-3 bg-white/5 rounded-lg hover:bg-white/10 transition-colors"
                      >
                        <span className="text-xs text-gray-500 w-6">{index + 6}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm text-white truncate">
                              {container.name ? container.name.replace(/^\//, '') : container.id.substring(0, 12)}
                            </span>
                            <div className={getStatusClass(container.status)}>
                              {getStatusIcon(container.status)}
                            </div>
                          </div>
                          <p className="text-xs text-gray-500 truncate">{container.image}</p>
                        </div>
                        <div className="flex items-center gap-4 text-xs">
                          <div className="text-right">
                            <div className={`font-medium ${container.cpu_percent > 80 ? 'text-red-400' : container.cpu_percent > 50 ? 'text-yellow-400' : 'text-neon-blue'}`}>
                              {container.cpu_percent.toFixed(1)}% CPU
                            </div>
                          </div>
                          <div className="text-right">
                            <div className={`font-medium ${container.memory_percent > 80 ? 'text-red-400' : container.memory_percent > 50 ? 'text-yellow-400' : 'text-neon-purple'}`}>
                              {formatBytes(container.memory_usage)}
                            </div>
                          </div>
                          <div className="text-gray-400">
                            {formatUptime(container.uptime_seconds)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
