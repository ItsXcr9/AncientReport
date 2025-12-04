/**
 * LiveChart Component - Real-time metrics visualization
 * 
 * Combines historical data from API with real-time WebSocket updates
 */

import { useEffect, useState, useMemo, memo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts';
import { Activity, RefreshCw } from 'lucide-react';
import { motion } from 'framer-motion';
import { useMetricsStore } from '../stores/metricsStore';

interface LiveChartProps {
  title: string;
  endpoint: string;
  metricName: string;
  dataKey: string;
  color?: string;
  yAxisLabel?: string;
  timeRange?: string;
  hostname?: string | null;
  showLiveIndicator?: boolean;
  maxPoints?: number;
}

interface DataPoint {
  timestamp: string;
  value: number;
}

export function LiveChart({ 
  title, 
  endpoint, 
  metricName,
  dataKey,
  color = '#3b82f6',
  yAxisLabel = 'Value',
  timeRange = '1h',
  hostname = null,
  showLiveIndicator = true,
  maxPoints = 150
}: LiveChartProps) {
  const [historicalData, setHistoricalData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  
  // Get real-time metrics from store
  const isConnected = useMetricsStore(state => state.isConnected);
  const getMetrics = useMetricsStore(state => state.getMetrics);
  const realtimeData = hostname ? getMetrics(hostname, metricName, 50) : [];
  
  // Fetch historical data
  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const end = new Date(Date.now() - 10000);
      const start = new Date();
      
      switch(timeRange) {
        case '1h':
          start.setTime(end.getTime() - 60 * 60 * 1000);
          break;
        case '6h':
          start.setTime(end.getTime() - 6 * 60 * 60 * 1000);
          break;
        case '24h':
          start.setTime(end.getTime() - 24 * 60 * 60 * 1000);
          break;
        case '7d':
          start.setTime(end.getTime() - 7 * 24 * 60 * 60 * 1000);
          break;
      }

      let url = `${endpoint}?start=${start.toISOString()}&end=${end.toISOString()}`;
      if (hostname) {
        url += `&hostname=${hostname}`;
      }

      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch metrics');
      
      const result = await response.json();
      const rawData = result.data || [];
      
      const normalizedData = rawData
        .filter((point: any) => point && point.timestamp && point.value !== undefined)
        .map((point: any) => ({
          timestamp: point.timestamp,
          value: typeof point.value === 'number' ? point.value : parseFloat(point.value) || 0
        }))
        .sort((a: DataPoint, b: DataPoint) => 
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
        );
      
      setHistoricalData(normalizedData);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      console.error(`[${title}] Fetch error:`, err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Refresh less frequently in live mode (WebSocket handles updates)
    const interval = setInterval(fetchData, isConnected ? 120000 : 30000);
    return () => clearInterval(interval);
  }, [endpoint, timeRange, hostname, isConnected]);

  // Merge historical and real-time data
  const mergedData = useMemo(() => {
    if (!isConnected || realtimeData.length === 0) {
      return historicalData;
    }
    
    // Combine and deduplicate
    const combined = [...historicalData, ...realtimeData];
    const uniqueMap = new Map<string, DataPoint>();
    
    combined.forEach(point => {
      uniqueMap.set(point.timestamp, point);
    });
    
    const sorted = Array.from(uniqueMap.values())
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    
    // Keep only maxPoints
    return sorted.slice(-maxPoints);
  }, [historicalData, realtimeData, isConnected, maxPoints]);

  const formatXAxis = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      if (!isNaN(date.getTime())) {
        return date.toLocaleTimeString('en-US', { 
          timeZone: 'Asia/Tehran',
          hour: '2-digit', 
          minute: '2-digit',
          hour12: false 
        });
      }
      return timestamp;
    } catch (e) {
      return timestamp;
    }
  };

  const formatTooltipLabel = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      if (!isNaN(date.getTime())) {
        return date.toLocaleString('en-US', { 
          timeZone: 'Asia/Tehran',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false 
        }) + ' (Tehran)';
      }
      return timestamp;
    } catch (e) {
      return timestamp;
    }
  };

  const formatTooltip = (value: number) => {
    return `${value.toFixed(2)}`;
  };

  // Calculate stats
  const stats = useMemo(() => {
    return mergedData.length > 0 ? {
      current: mergedData[mergedData.length - 1]?.value || 0,
      avg: mergedData.reduce((sum, d) => sum + d.value, 0) / mergedData.length,
      max: Math.max(...mergedData.map(d => d.value)),
      min: Math.min(...mergedData.map(d => d.value))
    } : null;
  }, [mergedData]);

  if (loading && mergedData.length === 0) {
    return (
      <div className="glass-card rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          <RefreshCw className="w-6 h-6 animate-spin" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <div className="h-64 flex items-center justify-center text-red-400 text-sm">
          Error: {error}
        </div>
      </div>
    );
  }

  return (
    <motion.div 
      className="glass-card rounded-xl p-6"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold">{title}</h3>
          {showLiveIndicator && isConnected && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center gap-2 text-green-400 text-xs px-2 py-1 bg-green-500/10 rounded-full border border-green-500/20"
            >
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ repeat: Infinity, duration: 2 }}
              >
                <Activity className="w-3 h-3" />
              </motion.div>
              <span className="font-medium">LIVE</span>
            </motion.div>
          )}
        </div>
        
        {stats && (
          <div className="flex items-center gap-4 text-xs text-gray-400">
            <div>
              <span className="text-gray-500">Current:</span>{' '}
              <span className="text-white font-semibold">{stats.current.toFixed(1)}</span>
            </div>
            <div>
              <span className="text-gray-500">Avg:</span>{' '}
              <span className="text-gray-300">{stats.avg.toFixed(1)}</span>
            </div>
            <div>
              <span className="text-gray-500">Max:</span>{' '}
              <span className="text-gray-300">{stats.max.toFixed(1)}</span>
            </div>
          </div>
        )}
      </div>
      
      {mergedData.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
          No data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={mergedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff20" />
            <XAxis 
              dataKey="timestamp" 
              tickFormatter={formatXAxis}
              stroke="#9ca3af"
              style={{ fontSize: '12px' }}
            />
            <YAxis 
              label={{ value: yAxisLabel, angle: -90, position: 'insideLeft', style: { fill: '#9ca3af' } }}
              stroke="#9ca3af"
              style={{ fontSize: '12px' }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1f2937', 
                border: '1px solid #374151',
                borderRadius: '8px'
              }}
              formatter={formatTooltip}
              labelFormatter={formatTooltipLabel}
            />
            <Legend />
            
            {/* Show average line */}
            {stats && (
              <ReferenceLine 
                y={stats.avg} 
                stroke="#6b7280" 
                strokeDasharray="3 3"
                label={{ value: 'Avg', position: 'right', fill: '#6b7280', fontSize: 10 }}
              />
            )}
            
            <Line 
              type="monotone" 
              dataKey="value" 
              name={dataKey}
              stroke={color} 
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 6 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
      
      {lastUpdate && (
        <div className="mt-2 text-xs text-gray-500 text-right">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}
    </motion.div>
  );
}

export default memo(LiveChart);
