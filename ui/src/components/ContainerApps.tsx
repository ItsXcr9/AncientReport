import React, { useEffect, useState } from 'react';
import { Database, MessageSquare, AlertTriangle, CheckCircle, XCircle, RefreshCw, Clock, Server, Activity, HardDrive, Users, Zap } from 'lucide-react';

interface ContainerAppsProps {
  selectedServer: string | null;
}

interface KafkaHealth {
  status: string;
  issues: string[];
  brokers: Record<string, Record<string, number>>;
}

interface RedisHealth {
  status: string;
  issues: string[];
  instances: Record<string, { hostname: string; metrics: Record<string, number> }>;
}

interface PostgresHealth {
  status: string;
  issues: string[];
  instances: Record<string, { hostname: string; global: Record<string, number>; databases: Record<string, Record<string, number>> }>;
}

interface DetectedContainers {
  kafka: Array<{ hostname: string; container_name: string; container_id: string }>;
  redis: Array<{ hostname: string; container_name: string; container_id: string }>;
  postgres: Array<{ hostname: string; container_name: string; container_id: string }>;
  total: number;
}

export const ContainerApps: React.FC<ContainerAppsProps> = ({ selectedServer }) => {
  const [kafkaHealth, setKafkaHealth] = useState<KafkaHealth | null>(null);
  const [redisHealth, setRedisHealth] = useState<RedisHealth | null>(null);
  const [postgresHealth, setPostgresHealth] = useState<PostgresHealth | null>(null);
  const [detected, setDetected] = useState<DetectedContainers | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      const hostnameParam = selectedServer ? `?hostname=${encodeURIComponent(selectedServer)}` : '';
      
      const [detectedRes, kafkaRes, redisRes, postgresRes] = await Promise.all([
        fetch(`/api/container-apps/detected${hostnameParam}`),
        fetch(`/api/container-apps/kafka/health${hostnameParam}`),
        fetch(`/api/container-apps/redis/health${hostnameParam}`),
        fetch(`/api/container-apps/postgres/health${hostnameParam}`)
      ]);

      if (detectedRes.ok) setDetected(await detectedRes.json());
      if (kafkaRes.ok) setKafkaHealth(await kafkaRes.json());
      if (redisRes.ok) setRedisHealth(await redisRes.json());
      if (postgresRes.ok) setPostgresHealth(await postgresRes.json());
      
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Error fetching container apps data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [selectedServer]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy': return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'warning': return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      case 'critical': return <XCircle className="w-5 h-5 text-red-400" />;
      default: return <Activity className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'healthy': return 'border-green-500/30 bg-green-500/5';
      case 'warning': return 'border-yellow-500/30 bg-yellow-500/5';
      case 'critical': return 'border-red-500/30 bg-red-500/5';
      default: return 'border-gray-500/30 bg-gray-500/5';
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  // Check if any apps are detected
  const hasKafka = detected?.kafka && detected.kafka.length > 0;
  const hasRedis = detected?.redis && detected.redis.length > 0;
  const hasPostgres = detected?.postgres && detected.postgres.length > 0;
  const hasAnyApps = hasKafka || hasRedis || hasPostgres;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-4 bg-white/10 rounded w-48 animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-48 bg-white/5 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!hasAnyApps) {
    return (
      <div className="glass-card rounded-xl p-6 text-center">
        <Database className="w-12 h-12 text-gray-500 mx-auto mb-3" />
        <h3 className="text-lg font-medium text-gray-300 mb-2">No Application Containers Detected</h3>
        <p className="text-sm text-gray-500">
          Kafka, Redis, and PostgreSQL containers will appear here once detected.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Database className="w-6 h-6 text-neon-blue" />
          <h2 className="text-xl font-bold text-white">Application Containers</h2>
          <span className="text-sm text-gray-400">
            ({detected?.total || 0} detected)
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Clock className="w-4 h-4" />
          Updated: {lastUpdated.toLocaleTimeString()}
          <button 
            onClick={fetchData}
            className="p-1 hover:bg-white/10 rounded transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* App Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Kafka Card */}
        <div className={`rounded-xl border p-5 transition-all ${
          hasKafka ? getStatusBg(kafkaHealth?.status || 'unknown') : 'border-gray-700/50 bg-gray-800/20 opacity-50'
        }`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-orange-500/20 rounded-lg">
                <MessageSquare className="w-5 h-5 text-orange-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white">Kafka</h3>
                <p className="text-xs text-gray-400">
                  {detected?.kafka?.length || 0} broker{(detected?.kafka?.length || 0) !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            {hasKafka && getStatusIcon(kafkaHealth?.status || 'unknown')}
          </div>

          {hasKafka && kafkaHealth && (
            <div className="space-y-3">
              {/* Key Metrics */}
              {Object.entries(kafkaHealth.brokers || {}).slice(0, 2).map(([broker, metrics]) => (
                <div key={broker} className="text-sm">
                  <div className="text-gray-400 truncate mb-1">{broker}</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">Lag:</span>
                      <span className={`ml-1 ${(metrics.total_consumer_lag || 0) > 10000 ? 'text-yellow-400' : 'text-green-400'}`}>
                        {(metrics.total_consumer_lag || 0).toLocaleString()}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">URPs:</span>
                      <span className={`ml-1 ${(metrics.under_replicated_partitions || 0) > 0 ? 'text-red-400' : 'text-green-400'}`}>
                        {metrics.under_replicated_partitions || 0}
                      </span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Issues */}
              {kafkaHealth.issues && kafkaHealth.issues.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  {kafkaHealth.issues.slice(0, 2).map((issue, i) => (
                    <div key={i} className="text-xs text-yellow-400 flex items-start gap-1 mb-1">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="truncate">{issue}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!hasKafka && (
            <p className="text-sm text-gray-500 italic">No Kafka containers</p>
          )}
        </div>

        {/* Redis Card */}
        <div className={`rounded-xl border p-5 transition-all ${
          hasRedis ? getStatusBg(redisHealth?.status || 'unknown') : 'border-gray-700/50 bg-gray-800/20 opacity-50'
        }`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-red-500/20 rounded-lg">
                <Zap className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white">Redis</h3>
                <p className="text-xs text-gray-400">
                  {detected?.redis?.length || 0} instance{(detected?.redis?.length || 0) !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            {hasRedis && getStatusIcon(redisHealth?.status || 'unknown')}
          </div>

          {hasRedis && redisHealth && (
            <div className="space-y-3">
              {Object.entries(redisHealth.instances || {}).slice(0, 2).map(([instance, data]) => (
                <div key={instance} className="text-sm">
                  <div className="text-gray-400 truncate mb-1">{instance}</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">Memory:</span>
                      <span className={`ml-1 ${(data.metrics?.memory_usage_percent || 0) > 80 ? 'text-red-400' : 'text-green-400'}`}>
                        {(data.metrics?.memory_usage_percent || 0).toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Hit Rate:</span>
                      <span className={`ml-1 ${(data.metrics?.hit_rate_percent || 100) < 80 ? 'text-yellow-400' : 'text-green-400'}`}>
                        {(data.metrics?.hit_rate_percent || 0).toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Clients:</span>
                      <span className="ml-1 text-blue-400">
                        {data.metrics?.connected_clients || 0}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Evicted:</span>
                      <span className={`ml-1 ${(data.metrics?.evicted_keys || 0) > 100 ? 'text-yellow-400' : 'text-gray-300'}`}>
                        {(data.metrics?.evicted_keys || 0).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              ))}

              {redisHealth.issues && redisHealth.issues.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  {redisHealth.issues.slice(0, 2).map((issue, i) => (
                    <div key={i} className="text-xs text-yellow-400 flex items-start gap-1 mb-1">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="truncate">{issue}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!hasRedis && (
            <p className="text-sm text-gray-500 italic">No Redis containers</p>
          )}
        </div>

        {/* PostgreSQL Card */}
        <div className={`rounded-xl border p-5 transition-all ${
          hasPostgres ? getStatusBg(postgresHealth?.status || 'unknown') : 'border-gray-700/50 bg-gray-800/20 opacity-50'
        }`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/20 rounded-lg">
                <Database className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white">PostgreSQL</h3>
                <p className="text-xs text-gray-400">
                  {detected?.postgres?.length || 0} instance{(detected?.postgres?.length || 0) !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            {hasPostgres && getStatusIcon(postgresHealth?.status || 'unknown')}
          </div>

          {hasPostgres && postgresHealth && (
            <div className="space-y-3">
              {Object.entries(postgresHealth.instances || {}).slice(0, 2).map(([instance, data]) => {
                const conns = data.global?.connections_total || 0;
                const maxConns = data.global?.max_connections || 100;
                const utilPct = maxConns > 0 ? (conns / maxConns) * 100 : 0;
                
                return (
                  <div key={instance} className="text-sm">
                    <div className="text-gray-400 truncate mb-1">{instance}</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-gray-500">Conns:</span>
                        <span className={`ml-1 ${utilPct > 80 ? 'text-red-400' : 'text-green-400'}`}>
                          {conns}/{maxConns}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Replica:</span>
                        <span className="ml-1 text-gray-300">
                          {data.global?.is_replica ? 'Yes' : 'No'}
                        </span>
                      </div>
                      {data.global?.replica_lag_seconds !== undefined && (
                        <div className="col-span-2">
                          <span className="text-gray-500">Lag:</span>
                          <span className={`ml-1 ${(data.global.replica_lag_seconds || 0) > 60 ? 'text-yellow-400' : 'text-green-400'}`}>
                            {data.global.replica_lag_seconds?.toFixed(1)}s
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {postgresHealth.issues && postgresHealth.issues.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  {postgresHealth.issues.slice(0, 2).map((issue, i) => (
                    <div key={i} className="text-xs text-yellow-400 flex items-start gap-1 mb-1">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="truncate">{issue}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!hasPostgres && (
            <p className="text-sm text-gray-500 italic">No PostgreSQL containers</p>
          )}
        </div>
      </div>
    </div>
  );
};
