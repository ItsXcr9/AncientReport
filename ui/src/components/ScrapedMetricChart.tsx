/**
 * ScrapedMetricChart - Chart for scraped Prometheus metrics
 */

import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, Area, AreaChart, ReferenceLine 
} from 'recharts';
import { RefreshCw, TrendingUp, Clock, Filter, Settings2, Code, ChevronDown, ChevronUp } from 'lucide-react';

interface ScrapedMetricChartProps {
  targetId: string;
  metricName: string;
  title?: string;
  color?: string;
  timeRange?: '1h' | '6h' | '24h' | '7d';
  chartType?: 'line' | 'area';
  height?: number;
  labelFilters?: Record<string, string>;  // Label key-value filters
  aggregation?: 'avg' | 'sum' | 'max' | 'min' | 'none';  // Aggregation function
  threshold?: { value: number; color?: string; label?: string };  // Threshold line
  showControls?: boolean;  // Show filter/aggregation controls
}

interface DataPoint {
  timestamp: string;
  value: number;
  min?: number;
  max?: number;
}


export function ScrapedMetricChart({
  targetId,
  metricName,
  title,
  color = '#00F3FF',
  timeRange = '1h',
  chartType = 'area',
  height = 200,
  labelFilters,
  aggregation = 'avg',
  threshold,
  showControls = false
}: ScrapedMetricChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [showJson, setShowJson] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const end = new Date();
      const start = new Date();

      switch (timeRange) {
        case '1h':
          start.setHours(start.getHours() - 1);
          break;
        case '6h':
          start.setHours(start.getHours() - 6);
          break;
        case '24h':
          start.setDate(start.getDate() - 1);
          break;
        case '7d':
          start.setDate(start.getDate() - 7);
          break;
      }

      // Determine step based on time range
      const step = timeRange === '1h' ? '1m' : 
                   timeRange === '6h' ? '5m' : 
                   timeRange === '24h' ? '15m' : '1h';

      const params = new URLSearchParams({
        target_id: targetId,
        metric_name: metricName,
        start: start.toISOString(),
        end: end.toISOString(),
        step,
        aggregation
      });

      // Add label filters if provided
      if (labelFilters && Object.keys(labelFilters).length > 0) {
        params.set('labels', JSON.stringify(labelFilters));
      }

      const response = await fetch(`/api/prometheus/scraped/series?${params}`);
      
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
  }, [targetId, metricName, timeRange]);

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
        className="glass-card rounded-xl p-4"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-300">{title || metricName}</h3>
        </div>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </motion.div>
    );
  }

  if (error) {
    return (
      <motion.div 
        className="glass-card rounded-xl p-4"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-300">{title || metricName}</h3>
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
        className="glass-card rounded-xl p-4"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-300">{title || metricName}</h3>
        </div>
        <div className="text-center py-8 text-gray-500 text-sm">
          No data available
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div 
      className="glass-card rounded-xl p-4"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4" style={{ color }} />
          <h3 className="text-sm font-medium text-gray-300">{title || metricName}</h3>
        </div>
        
        {stats && (
          <div className="flex items-center gap-4 text-xs">
            <div className="text-gray-400">
              Current: <span className="text-white font-medium">{formatValue(stats.current)}</span>
            </div>
            <div className="text-gray-500">
              Avg: {formatValue(stats.avg)}
            </div>
          </div>
        )}
        
        {/* JSON Toggle Button */}
        <button
          onClick={() => setShowJson(!showJson)}
          className={`p-1.5 rounded transition-colors ${showJson ? 'bg-cyan-500/20 text-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
          title="Toggle JSON view"
        >
          <Code className="w-4 h-4" />
        </button>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        {chartType === 'area' ? (
          <AreaChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <defs>
              <linearGradient id={`gradient-${metricName}`} x1="0" y1="0" x2="0" y2="1">
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
                border: '1px solid #374151',
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
              fill={`url(#gradient-${metricName})`}
              isAnimationActive={false}
            />
            {threshold && (
              <ReferenceLine 
                y={threshold.value} 
                stroke={threshold.color || '#EF4444'} 
                strokeDasharray="5 5"
                strokeWidth={2}
                label={{ value: threshold.label || `Threshold: ${threshold.value}`, fill: threshold.color || '#EF4444', fontSize: 10 }}
              />
            )}
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
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
                border: '1px solid #374151',
                borderRadius: '8px',
                fontSize: '12px'
              }}
              formatter={(value: number) => [formatTooltip(value), metricName]}
              labelFormatter={(label) => new Date(label).toLocaleString()}
            />
            <Line 
              type="monotone" 
              dataKey="value" 
              stroke={color} 
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            {threshold && (
              <ReferenceLine 
                y={threshold.value} 
                stroke={threshold.color || '#EF4444'} 
                strokeDasharray="5 5"
                strokeWidth={2}
                label={{ value: threshold.label || `Threshold: ${threshold.value}`, fill: threshold.color || '#EF4444', fontSize: 10 }}
              />
            )}
          </LineChart>
        )}
      </ResponsiveContainer>

      {lastUpdate && (
        <div className="flex items-center justify-end gap-1 mt-2 text-xs text-gray-500">
          <Clock className="w-3 h-3" />
          Updated {lastUpdate.toLocaleTimeString()}
        </div>
      )}
      
      {/* JSON View */}
      {showJson && (
        <div className="mt-4 border-t border-gray-700/50 pt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">Raw Data ({data.length} points)</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(JSON.stringify(data, null, 2));
              }}
              className="text-xs text-gray-500 hover:text-cyan-400"
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

export default ScrapedMetricChart;
