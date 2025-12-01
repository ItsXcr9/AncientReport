import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

interface NetworkChartProps {
  timeRange?: string;
}

interface DataPoint {
  timestamp: string;
  sent: number;
  received: number;
}

export function NetworkChart({ timeRange = '1h' }: NetworkChartProps) {
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
        `/api/metrics/network?start=${start.toISOString()}&end=${end.toISOString()}`
      );
      
      if (!response.ok) {
        throw new Error('Failed to fetch network metrics');
      }
      
      const result = await response.json();
      const rawData = result.data || [];
      
      // Validate and normalize data
      const normalizedData = rawData
        .filter((point: any) => point && point.timestamp && 
                (point.sent !== undefined || point.received !== undefined))
        .map((point: any) => ({
          timestamp: point.timestamp,
          sent: typeof point.sent === 'number' ? point.sent : parseFloat(point.sent) || 0,
          received: typeof point.received === 'number' ? point.received : parseFloat(point.received) || 0
        }))
        .sort((a: DataPoint, b: DataPoint) => {
          const dateA = new Date(a.timestamp).getTime();
          const dateB = new Date(b.timestamp).getTime();
          return dateA - dateB;
        });
      
      console.log(`[Network] Fetched ${rawData.length} raw points, ${normalizedData.length} valid points`);
      setData(normalizedData);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      console.error('[Network] Failed to fetch metrics:', err);
      setData([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [timeRange]);

  const formatXAxis = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  const formatTooltip = (value: number, name: string) => {
    if (name === 'sent' || name === 'received') {
      return [`${value.toFixed(2)} packets/sec`, name === 'sent' ? 'Sent' : 'Received'];
    }
    return [value, name];
  };

  if (loading && data.length === 0) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4">Network Traffic</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          Loading...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4">Network Traffic</h3>
        <div className="h-64 flex items-center justify-center text-red-400">
          Error: {error}
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4">Network Traffic</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          No data available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
      <h3 className="text-lg font-semibold mb-4">Network Traffic</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff20" />
          <XAxis 
            dataKey="timestamp" 
            tickFormatter={formatXAxis}
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
          />
          <YAxis 
            label={{ value: 'Packets/sec', angle: -90, position: 'insideLeft' }}
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
            dataKey="sent" 
            name="Packets Sent"
            stroke="#3b82f6" 
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 6 }}
          />
          <Line 
            type="monotone" 
            dataKey="received" 
            name="Packets Received"
            stroke="#8b5cf6" 
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

