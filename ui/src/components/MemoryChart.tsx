import { MetricsChart } from './MetricsChart';

export function MemoryChart({ timeRange = '1h' }: { timeRange?: string }) {
  return (
    <MetricsChart
      title="Memory Usage"
      endpoint="/api/metrics/memory"
      dataKey="Memory %"
      color="#8b5cf6"
      yAxisLabel="Memory Usage (%)"
      timeRange={timeRange}
    />
  );
}
