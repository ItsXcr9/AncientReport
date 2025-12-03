import { LiveChart } from './LiveChart';

export function MemoryChart({ timeRange = '1h', hostname = null }: { timeRange?: string; hostname?: string | null }) {
  return (
    <LiveChart
      title="Memory Usage"
      endpoint="/api/metrics/memory"
      metricName="memory_usage_percent"
      dataKey="Memory %"
      color="#EC4899"
      yAxisLabel="Memory Usage (%)"
      timeRange={timeRange}
      hostname={hostname}
      showLiveIndicator={true}
    />
  );
}
