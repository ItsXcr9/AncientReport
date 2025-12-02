import { MetricsChart } from './MetricsChart';

export function MemoryChart({ timeRange = '1h', hostname = null }: { timeRange?: string; hostname?: string | null }) {
  return (
    <MetricsChart
      title="Memory Usage"
      endpoint="/api/metrics/memory"
      dataKey="Memory %"
      color="#8b5cf6"
      yAxisLabel="Memory Usage (%)"
      timeRange={timeRange}
      hostname={hostname}
    />
  );
}
