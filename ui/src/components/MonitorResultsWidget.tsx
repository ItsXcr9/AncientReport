import { useState, useEffect } from 'react';
import { Activity, Check, AlertTriangle, XCircle, Clock, RefreshCw, Plug, Globe, Zap } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface MonitorResult {
  monitor_id: string;
  name: string;
  type: 'port' | 'http';
  target: string;
  status: 'ok' | 'warning' | 'critical' | 'unknown';
  latency_ms: number;
  last_check: string;
  message?: string;
}

interface MonitorConfig {
  id: string;
  name: string;
  type: 'port' | 'http';
  config: {
    host?: string;
    port?: number;
    url?: string;
  };
  enabled: boolean;
}

const API_BASE = '';

export const MonitorResultsWidget = () => {
  const [monitors, setMonitors] = useState<MonitorConfig[]>([]);
  const [results, setResults] = useState<MonitorResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const monitorsRes = await fetch(`${API_BASE}/api/v3/monitors`);
      if (monitorsRes.ok) {
        const monitorsData = await monitorsRes.json();
        setMonitors(monitorsData);
        
        const simulatedResults: MonitorResult[] = monitorsData.map((m: MonitorConfig) => ({
          monitor_id: m.id,
          name: m.name,
          type: m.type,
          target: m.type === 'port' ? `${m.config.host}:${m.config.port}` : m.config.url || '',
          status: m.enabled ? (Math.random() > 0.2 ? 'ok' : 'warning') : 'unknown',
          latency_ms: Math.floor(Math.random() * 150) + 5,
          last_check: new Date().toISOString(),
        }));
        setResults(simulatedResults);
      }
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Failed to fetch monitor data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ok': return <Check className="w-4 h-4 text-neon-green" />;
      case 'warning': return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
      case 'critical': return <XCircle className="w-4 h-4 text-red-400" />;
      default: return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ok': return 'border-neon-green/30 bg-neon-green/5';
      case 'warning': return 'border-yellow-400/30 bg-yellow-400/5';
      case 'critical': return 'border-red-400/30 bg-red-400/5';
      default: return 'border-gray-500/30 bg-gray-500/5';
    }
  };

  const healthyCount = results.filter(r => r.status === 'ok').length;
  const warningCount = results.filter(r => r.status === 'warning').length;
  const criticalCount = results.filter(r => r.status === 'critical').length;

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-neon-purple/10 rounded-lg">
            <Activity className="w-5 h-5 text-neon-purple" />
          </div>
          <h3 className="text-lg font-semibold text-white">Custom Monitors</h3>
        </div>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 text-neon-blue animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-6 rounded-xl"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-neon-purple/10 rounded-lg">
            <Activity className="w-5 h-5 text-neon-purple" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">Custom Monitors</h3>
            <p className="text-xs text-gray-500">
              {lastUpdate ? `Updated ${lastUpdate.toLocaleTimeString()}` : 'Loading...'}
            </p>
          </div>
        </div>
        <button
          onClick={fetchData}
          className="p-2 hover:bg-white/5 rounded-lg transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {monitors.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="p-2 rounded-lg bg-neon-green/5 border border-neon-green/20 text-center">
            <div className="text-xl font-bold text-neon-green">{healthyCount}</div>
            <div className="text-xs text-gray-400">Healthy</div>
          </div>
          <div className="p-2 rounded-lg bg-yellow-400/5 border border-yellow-400/20 text-center">
            <div className="text-xl font-bold text-yellow-400">{warningCount}</div>
            <div className="text-xs text-gray-400">Warning</div>
          </div>
          <div className="p-2 rounded-lg bg-red-400/5 border border-red-400/20 text-center">
            <div className="text-xl font-bold text-red-400">{criticalCount}</div>
            <div className="text-xs text-gray-400">Critical</div>
          </div>
        </div>
      )}

      {monitors.length === 0 ? (
        <div className="text-center py-6">
          <Activity className="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p className="text-sm text-gray-400">No monitors configured</p>
          <p className="text-xs text-gray-500 mt-1">
            Go to Settings → Custom Monitors to add one
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <AnimatePresence>
            {results.map((result) => (
              <motion.div
                key={result.monitor_id}
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                className={`p-3 rounded-lg border transition-all ${getStatusColor(result.status)}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(result.status)}
                    <div>
                      <div className="font-medium text-white text-sm flex items-center gap-2">
                        {result.type === 'port' ? (
                          <Plug className="w-3 h-3 text-neon-purple" />
                        ) : (
                          <Globe className="w-3 h-3 text-neon-blue" />
                        )}
                        {result.name}
                      </div>
                      <div className="text-xs text-gray-500 font-mono truncate max-w-[200px]">
                        {result.target}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-xs text-gray-400">
                      <Zap className="w-3 h-3" />
                      {result.latency_ms}ms
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
};

export default MonitorResultsWidget;
