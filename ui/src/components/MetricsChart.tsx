import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Activity } from 'lucide-react';

interface MetricsChartProps {
  title: string;
  endpoint: string;
  dataKey: string;
  color?: string;
  yAxisLabel?: string;
  timeRange?: string;
  hostname?: string | null;
  realtimeData?: DataPoint[];
  isLive?: boolean;
}

interface DataPoint {
  timestamp: string;
  value: number;
}

export function MetricsChart({ 
  title, 
  endpoint, 
  dataKey,
  color = '#3b82f6',
  yAxisLabel = 'Value',
  timeRange = '1h',
  hostname = null,
  realtimeData = [],
  isLive = false
}: MetricsChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const MAX_REALTIME_POINTS = 100; // Keep last 100 points for real-time view

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Always use current time in UTC (backend will handle Tehran timezone conversion)
      // Subtract a small buffer to account for data collection lag
      const end = new Date(Date.now() - 10000); // 10 seconds ago
      const start = new Date();
      
      // Calculate start time based on range
      switch(timeRange) {
        case '1h':
          start.setTime(end.getTime() - 60 * 60 * 1000); // 1 hour before end
          break;
        case '6h':
          start.setTime(end.getTime() - 6 * 60 * 60 * 1000); // 6 hours before end
          break;
        case '24h':
          start.setTime(end.getTime() - 24 * 60 * 60 * 1000); // 24 hours before end
          break;
        case '7d':
          start.setTime(end.getTime() - 7 * 24 * 60 * 60 * 1000); // 7 days before end
          break;
      }

      let url = `${endpoint}?start=${start.toISOString()}&end=${end.toISOString()}`;
      if (hostname) {
        url += `&hostname=${hostname}`;
      }

      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error('Failed to fetch metrics');
      }
      
      const result = await response.json();
      const rawData = result.data || [];
      
      // Validate and normalize data
      const normalizedData = rawData
        .filter((point: any) => point && point.timestamp && point.value !== undefined && point.value !== null)
        .map((point: any) => ({
          ...point,
          value: typeof point.value === 'number' ? point.value : parseFloat(point.value) || 0
        }))
        .sort((a: DataPoint, b: DataPoint) => {
          const dateA = new Date(a.timestamp).getTime();
          const dateB = new Date(b.timestamp).getTime();
          return dateA - dateB;
        });
      
      console.log(`[${title}] Fetched ${rawData.length} raw points, ${normalizedData.length} valid points`);
      if (normalizedData.length > 0) {
        console.log(`[${title}] First point:`, normalizedData[0]);
        console.log(`[${title}] Last point:`, normalizedData[normalizedData.length - 1]);
      }
      
      setData(normalizedData);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      console.error(`[${title}] Failed to fetch metrics:`, err);
      setData([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // In live mode, reduce polling frequency (WebSocket is primary)
    // In non-live mode, poll every 30 seconds
    const interval = setInterval(fetchData, isLive ? 60000 : 30000);
    return () => clearInterval(interval);
  }, [endpoint, timeRange, hostname, isLive]);

  // Merge real-time data with historical data
  useEffect(() => {
    if (isLive && realtimeData.length > 0) {
      setData(prevData => {
        // Combine historical and real-time data
        const combined = [...prevData, ...realtimeData];
        
        // Remove duplicates based on timestamp
        const unique = combined.filter((point, index, self) =>
          index === self.findIndex(p => p.timestamp === point.timestamp)
        );
        
        // Sort by timestamp
        const sorted = unique.sort((a, b) => {
          const dateA = new Date(a.timestamp).getTime();
          const dateB = new Date(b.timestamp).getTime();
          return dateA - dateB;
        });
        
        // Keep only the most recent points
        return sorted.slice(-MAX_REALTIME_POINTS);
      });
    }
  }, [realtimeData, isLive]);

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
      console.warn(`[${title}] Error formatting timestamp:`, timestamp, e);
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
    return `${value.toFixed(2)}%`;
  };

  if (loading && data.length === 0) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          Loading...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <div className="h-64 flex items-center justify-center text-red-400">
          Error: {error}
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          No data available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        {isLive && (
          <div className="flex items-center gap-2 text-green-400 text-sm">
            <Activity className="w-4 h-4 animate-pulse" />
            <span>LIVE</span>
          </div>
        )}
      </div>
      <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff20" />
            <XAxis 
              dataKey="timestamp" 
              tickFormatter={formatXAxis}
              stroke="#9ca3af"
              style={{ fontSize: '12px' }}
            />
          <YAxis 
            label={{ value: yAxisLabel, angle: -90, position: 'insideLeft' }}
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
          <Line 
            type="monotone" 
            dataKey="value" 
            name={dataKey}
            stroke={color} 
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
