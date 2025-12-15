import { useState, useEffect } from 'react';

interface HealthCheck {
  status: string;
  latency_ms?: number;
  buffer_percent?: number;
  usage_percent?: number;
  count?: number;
  limit?: number;
  usage_mb?: number;
  percent?: number;
}

interface HealthData {
  status: string;
  timestamp: string;
  uptime_seconds: number;
  checks: {
    clickhouse: HealthCheck;
    ingestion: HealthCheck;
    file_descriptors: HealthCheck;
    memory: HealthCheck;
  };
  component_health: Record<string, string>;
}

interface CardinalityData {
  total_series: number;
  dropped_total: number;
  limit_breaches: number;
  limits: Record<string, number>;
  top_hosts: Record<string, number>;
  top_metrics: Record<string, number>;
}

interface InternalMetrics {
  timestamp: string;
  uptime_seconds: number;
  counters: {
    ingested_total: number;
    dropped_total: number;
    alerts_triggered_total: number;
    errors_total: number;
    flushes_total: number;
  };
  gauges: {
    buffer_size: number;
    cardinality_series: number;
    active_alerts: number;
    open_fds: number;
    memory_mb: number;
    cpu_percent: number;
  };
  resources: {
    open_fds: number;
    fd_limit_soft: number;
    fd_limit_hard: number;
    fd_usage_percent: number;
    memory_mb: number;
    cpu_percent: number;
    threads: number;
  };
}

export default function SystemHealth() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [cardinality, setCardinality] = useState<CardinalityData | null>(null);
  const [metrics, setMetrics] = useState<InternalMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      const [healthRes, cardinalityRes, metricsRes] = await Promise.all([
        fetch('/api/internal/health').then(r => r.json()),
        fetch('/api/internal/cardinality').then(r => r.json()),
        fetch('/api/internal/metrics').then(r => r.json())
      ]);
      
      setHealth(healthRes);
      setCardinality(cardinalityRes);
      setMetrics(metricsRes);
      setError(null);
      setLastUpdate(new Date());
    } catch (err) {
      setError('Failed to fetch system health data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${mins}m`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  };

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy': return 'text-neon-green';
      case 'degraded': return 'text-yellow-400';
      case 'critical':
      case 'unhealthy': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusBg = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy': return 'bg-neon-green/20 border-neon-green/50';
      case 'degraded': return 'bg-yellow-400/20 border-yellow-400/50';
      case 'critical':
      case 'unhealthy': return 'bg-red-400/20 border-red-400/50';
      default: return 'bg-gray-400/20 border-gray-400/50';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-primary p-6 flex items-center justify-center">
        <div className="text-gray-400">Loading system health...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-primary p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">System Health</h1>
          <p className="text-gray-400">Internal monitoring and self-observability</p>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </span>
          <button 
            onClick={fetchData}
            className="px-4 py-2 bg-neon-blue/20 text-neon-blue border border-neon-blue/50 rounded-lg hover:bg-neon-blue/30 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/20 border border-red-500/50 text-red-400 p-4 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Overall Status */}
      <div className={`glass rounded-xl p-6 mb-6 border ${getStatusBg(health?.status || '')}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`text-4xl ${getStatusColor(health?.status || '')}`}>
              {health?.status === 'healthy' ? '✓' : health?.status === 'degraded' ? '⚠' : '✗'}
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${getStatusColor(health?.status || '')}`}>
                System {health?.status?.toUpperCase()}
              </h2>
              <p className="text-gray-400">Uptime: {formatUptime(health?.uptime_seconds || 0)}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-gray-400 text-sm">Timestamp</p>
            <p className="text-white">{health?.timestamp}</p>
          </div>
        </div>
      </div>

      {/* Health Checks Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {/* ClickHouse */}
        <div className="glass rounded-xl p-5 border border-glass-border">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400">ClickHouse</span>
            <span className={`${getStatusColor(health?.checks?.clickhouse?.status || '')} font-semibold`}>
              {health?.checks?.clickhouse?.status?.toUpperCase()}
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {health?.checks?.clickhouse?.latency_ms?.toFixed(1)}ms
          </div>
          <div className="text-sm text-gray-500">Query latency</div>
        </div>

        {/* Ingestion */}
        <div className="glass rounded-xl p-5 border border-glass-border">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400">Ingestion Buffer</span>
            <span className={`${getStatusColor(health?.checks?.ingestion?.status || '')} font-semibold`}>
              {health?.checks?.ingestion?.status?.toUpperCase()}
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {health?.checks?.ingestion?.buffer_percent?.toFixed(1)}%
          </div>
          <div className="text-sm text-gray-500">Buffer utilization</div>
        </div>

        {/* File Descriptors */}
        <div className="glass rounded-xl p-5 border border-glass-border">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400">File Descriptors</span>
            <span className={`${getStatusColor(health?.checks?.file_descriptors?.status || '')} font-semibold`}>
              {health?.checks?.file_descriptors?.status?.toUpperCase()}
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {health?.checks?.file_descriptors?.count} / {health?.checks?.file_descriptors?.limit}
          </div>
          <div className="text-sm text-gray-500">
            {health?.checks?.file_descriptors?.usage_percent?.toFixed(2)}% used
          </div>
        </div>

        {/* Memory */}
        <div className="glass rounded-xl p-5 border border-glass-border">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400">Memory</span>
            <span className={`${getStatusColor(health?.checks?.memory?.status || '')} font-semibold`}>
              {health?.checks?.memory?.status?.toUpperCase()}
            </span>
          </div>
          <div className="text-2xl font-bold text-white">
            {health?.checks?.memory?.usage_mb?.toFixed(0)} MB
          </div>
          <div className="text-sm text-gray-500">
            {health?.checks?.memory?.percent?.toFixed(1)}% of system
          </div>
        </div>
      </div>

      {/* Cardinality Section */}
      <div className="glass rounded-xl p-6 border border-glass-border mb-8">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <span>📊</span> Cardinality Control
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Total Series</div>
            <div className="text-3xl font-bold text-neon-blue">
              {cardinality?.total_series?.toLocaleString()}
            </div>
            <div className="text-sm text-gray-500">
              Limit: {cardinality?.limits?.global?.toLocaleString()}
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Dropped (High Cardinality)</div>
            <div className="text-3xl font-bold text-yellow-400">
              {cardinality?.dropped_total?.toLocaleString()}
            </div>
            <div className="text-sm text-gray-500">
              Protected from explosion
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Limit Breaches</div>
            <div className={`text-3xl font-bold ${cardinality?.limit_breaches === 0 ? 'text-neon-green' : 'text-red-400'}`}>
              {cardinality?.limit_breaches}
            </div>
            <div className="text-sm text-gray-500">
              {cardinality?.limit_breaches === 0 ? 'All within limits' : 'Action required'}
            </div>
          </div>
        </div>

        {/* Top Metrics Table */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className="text-gray-400 mb-3">Top Metrics by Series Count</h4>
            <div className="bg-bg-secondary rounded-lg overflow-hidden">
              {Object.entries(cardinality?.top_metrics || {}).slice(0, 5).map(([metric, count], i) => (
                <div key={metric} className={`flex justify-between items-center px-4 py-2 ${i % 2 === 0 ? 'bg-bg-secondary' : 'bg-bg-primary/50'}`}>
                  <span className="text-gray-300 text-sm truncate max-w-[200px]">{metric}</span>
                  <span className="text-neon-purple font-mono">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <h4 className="text-gray-400 mb-3">Series by Host</h4>
            <div className="bg-bg-secondary rounded-lg overflow-hidden">
              {Object.entries(cardinality?.top_hosts || {}).map(([host, count], i) => (
                <div key={host} className={`flex justify-between items-center px-4 py-2 ${i % 2 === 0 ? 'bg-bg-secondary' : 'bg-bg-primary/50'}`}>
                  <span className="text-gray-300 text-sm">{host}</span>
                  <span className="text-neon-blue font-mono">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Ingestion Metrics */}
      <div className="glass rounded-xl p-6 border border-glass-border mb-8">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <span>📥</span> Ingestion Pipeline
        </h3>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Ingested Total</div>
            <div className="text-2xl font-bold text-neon-green">
              {metrics?.counters?.ingested_total?.toLocaleString() || 0}
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Dropped Total</div>
            <div className="text-2xl font-bold text-yellow-400">
              {metrics?.counters?.dropped_total?.toLocaleString() || 0}
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Buffer Size</div>
            <div className="text-2xl font-bold text-white">
              {metrics?.gauges?.buffer_size?.toLocaleString() || 0}
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Flushes</div>
            <div className="text-2xl font-bold text-neon-blue">
              {metrics?.counters?.flushes_total?.toLocaleString() || 0}
            </div>
          </div>
        </div>
      </div>

      {/* Resource Usage */}
      <div className="glass rounded-xl p-6 border border-glass-border">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <span>⚙️</span> Resource Usage
        </h3>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">CPU Usage</div>
            <div className="text-2xl font-bold text-white">
              {metrics?.resources?.cpu_percent?.toFixed(1) || 0}%
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Memory</div>
            <div className="text-2xl font-bold text-white">
              {metrics?.resources?.memory_mb?.toFixed(0) || 0} MB
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">Threads</div>
            <div className="text-2xl font-bold text-white">
              {metrics?.resources?.threads || 0}
            </div>
          </div>
          
          <div className="bg-bg-secondary rounded-lg p-4">
            <div className="text-gray-400 text-sm mb-1">FD Usage</div>
            <div className="text-2xl font-bold text-white">
              {metrics?.resources?.fd_usage_percent?.toFixed(2) || 0}%
            </div>
            <div className="text-xs text-gray-500">
              {metrics?.resources?.open_fds} / {metrics?.resources?.fd_limit_soft}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
