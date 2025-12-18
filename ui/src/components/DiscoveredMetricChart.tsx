/**
 * DiscoveredMetricChart - Chart for agent-discovered Prometheus metrics
 */

import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { 
  XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, Area, AreaChart 
} from 'recharts';
import { RefreshCw, TrendingUp, Clock, Code } from 'lucide-react';

interface DiscoveredMetricChartProps {
  scrapeTarget: string;  // The scrape_target URL (e.g., "http://127.0.0.1:9187/metrics")
  metricName: string;
  title?: string;
  color?: string;
  timeRange?: '1h' | '6h' | '24h' | '7d';
  height?: number;
}

interface DataPoint {
  timestamp: string;
  value: number;
  min?: number;
  max?: number;
}

export function DiscoveredMetricChart({
  scrapeTarget,
  metricName,
  title,
  color = '#10B981',  // Default green for discovered metrics
  timeRange = '1h',
  height = 180
}: DiscoveredMetricChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [showJson, setShowJson] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Convert time range to hours
      const hours = timeRange === '1h' ? 1 : 
                    timeRange === '6h' ? 6 : 
                    timeRange === '24h' ? 24 : 168;  // 7d = 168h

      const params = new URLSearchParams({
        scrape_target: scrapeTarget,
        metric_name: metricName,
        hours: hours.toString()
      });

      const response = await fetch(`/api/prometheus/discovered/series?${params}`);
      
      if (!response.ok) {
        throw new Error('Failed to fetch metrics');
      }

      const result = await response.json();
      setData(result.data || []);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [scrapeTarget, metricName, timeRange]);

  const stats = useMemo(() => {
    if (data.length === 0) return null;
    const values = data.map(d => d.value);
    return {
      current: values[values.length - 1],
      avg: values.reduce((a, b) => a + b, 0) / values.length,
      min: Math.min(...values),
      max: Math.max(...values)
    };
  }, [data]);

  const formatXAxis = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      timeZone: 'Asia/Tehran',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const formatTooltip = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(2)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(2)}K`;
    return value.toFixed(2);
  };

  const formatValue = (value: number) => {
    if (value >= 1000000000) return `${(value / 1000000000).toFixed(1)}B`;
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
    return value.toFixed(1);
  };

  if (loading && data.length === 0) {
    return (
      <motion.div 
        className="bg-white/5 rounded-xl p-4 border border-green-500/20"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-green-400" />
          <h3 className="text-sm font-medium text-gray-300 truncate">{title || metricName}</h3>
        </div>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-5 h-5 animate-spin text-green-400" />
        </div>
      </motion.div>
    );
  }

  if (error) {
    return (
      <motion.div 
        className="bg-white/5 rounded-xl p-4 border border-green-500/20"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-green-400" />
          <h3 className="text-sm font-medium text-gray-300 truncate">{title || metricName}</h3>
        </div>
        <div className="text-center py-8 text-red-400 text-sm">
          {error}
        </div>
      </motion.div>
    );
  }

  if (data.length === 0) {
    return (
      <motion.div 
        className="bg-white/5 rounded-xl p-4 border border-green-500/20"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-green-400" />
          <h3 className="text-sm font-medium text-gray-300 truncate">{title || metricName}</h3>
        </div>
        <div className="text-center py-8 text-gray-500 text-sm">
          No data available
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div 
      className="bg-white/5 rounded-xl p-4 border border-green-500/20"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <TrendingUp className="w-4 h-4 flex-shrink-0" style={{ color }} />
          <h3 className="text-sm font-medium text-gray-300 truncate">{title || metricName}</h3>
        </div>
        
        {stats && (
          <div className="flex items-center gap-4 text-xs flex-shrink-0">
            <div className="text-gray-400">
              Current: <span className="text-white font-medium">{formatValue(stats.current)}</span>
            </div>
            <div className="text-gray-500 hidden md:block">
              Avg: {formatValue(stats.avg)}
            </div>
          </div>
        )}
        
        {/* JSON Toggle Button */}
        <button
          onClick={() => setShowJson(!showJson)}
          className={`p-1.5 rounded transition-colors ml-2 ${showJson ? 'bg-green-500/20 text-green-400' : 'text-gray-500 hover:text-gray-300'}`}
          title="Toggle JSON view"
        >
          <Code className="w-4 h-4" />
        </button>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <defs>
            <linearGradient id={`gradient-discovered-${metricName}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
          <XAxis 
            dataKey="timestamp" 
            tickFormatter={formatXAxis}
            stroke="#6b7280"
            fontSize={10}
            tickLine={false}
          />
          <YAxis 
            stroke="#6b7280"
            fontSize={10}
            tickLine={false}
            tickFormatter={formatValue}
            width={50}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: '#1f2937', 
              border: '1px solid #10B981',
              borderRadius: '8px',
              fontSize: '12px'
            }}
            formatter={(value: number) => [formatTooltip(value), metricName]}
            labelFormatter={(label) => new Date(label).toLocaleString()}
          />
          <Area 
            type="monotone" 
            dataKey="value" 
            stroke={color} 
            strokeWidth={2}
            fill={`url(#gradient-discovered-${metricName})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {lastUpdate && (
        <div className="flex items-center justify-end gap-1 mt-2 text-xs text-gray-500">
          <Clock className="w-3 h-3" />
          Updated {lastUpdate.toLocaleTimeString()}
        </div>
      )}
      
      {/* JSON View */}
      {showJson && (
        <div className="mt-4 border-t border-green-500/20 pt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">Raw Data ({data.length} points)</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(JSON.stringify(data, null, 2));
              }}
              className="text-xs text-gray-500 hover:text-green-400"
            >
              Copy
            </button>
          </div>
          <pre className="text-xs bg-gray-900/50 rounded-lg p-3 overflow-auto max-h-48 text-gray-300 font-mono">
            {JSON.stringify(data.slice(-10), null, 2)}
          </pre>
          {data.length > 10 && (
            <p className="text-xs text-gray-500 mt-2 text-center">Showing last 10 of {data.length} points</p>
          )}
        </div>
      )}
    </motion.div>
  );
}

export default DiscoveredMetricChart;
