import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

interface MetricsChartProps {
  title: string;
  endpoint: string;
  dataKey: string;
  color?: string;
  yAxisLabel?: string;
  timeRange?: string;
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
  timeRange = '1h'
}: MetricsChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

      const response = await fetch(
        `${endpoint}?start=${start.toISOString()}&end=${end.toISOString()}`
      );
      
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
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [endpoint, timeRange]);

  const formatXAxis = (timestamp: string) => {
    try {
      // Manually parse the timestamp string to avoid browser timezone conversions
      // Expected format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SS"
      // We want to treat these numbers as LOCAL time, exactly as they appear
      const parts = timestamp.split(/[-T :]/);
      if (parts.length >= 5) {
        const year = parseInt(parts[0]);
        const month = parseInt(parts[1]) - 1; // Months are 0-indexed
        const day = parseInt(parts[2]);
        const hour = parseInt(parts[3]);
        const minute = parseInt(parts[4]);
        
        // Create date using local time constructor
        const date = new Date(year, month, day, hour, minute);
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
      }
      
      // Fallback to standard parsing if format doesn't match
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch (e) {
      console.warn(`[${title}] Error formatting timestamp:`, timestamp, e);
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
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
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
            labelFormatter={(label) => new Date(label).toLocaleString()}
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
