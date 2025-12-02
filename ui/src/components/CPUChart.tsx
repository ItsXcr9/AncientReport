import { MetricsChart } from './MetricsChart';

export function CPUChart({ timeRange = '1h', hostname = null }: { timeRange?: string; hostname?: string | null }) {
  return (
    <MetricsChart
      title="CPU Usage"
      endpoint="/api/metrics/cpu"
      dataKey="CPU %"
      color="#3b82f6"
      yAxisLabel="CPU Usage (%)"
      timeRange={timeRange}
      hostname={hostname}
    />
  );
}
