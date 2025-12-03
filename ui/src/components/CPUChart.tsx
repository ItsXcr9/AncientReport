import { LiveChart } from './LiveChart';

export function CPUChart({ timeRange = '1h', hostname = null }: { timeRange?: string; hostname?: string | null }) {
  return (
    <LiveChart
      title="CPU Usage"
      endpoint="/api/metrics/cpu"
      metricName="cpu_usage_percent"
      dataKey="CPU %"
      color="#8B5CF6"
      yAxisLabel="CPU Usage (%)"
      timeRange={timeRange}
      hostname={hostname}
      showLiveIndicator={true}
    />
  );
}
