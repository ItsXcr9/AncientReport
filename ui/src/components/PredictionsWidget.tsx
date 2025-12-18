import { useState, useEffect } from 'react';
import { Brain, TrendingUp, AlertTriangle, Activity, Loader2 } from 'lucide-react';

interface AnomalyPrediction {
  metric: string;
  current_value: number;
  anomaly_probability: number;
  is_anomaly: boolean;
  severity: string;
  z_score: number;
  recommendation: string;
  method: string;
}

interface Props {
  hostname: string;
}

export function PredictionsWidget({ hostname }: Props) {
  const [anomalies, setAnomalies] = useState<Record<string, AnomalyPrediction>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPredictions = async () => {
      if (!hostname) return;
      try {
        setLoading(true);
        const res = await fetch(`/api/v3/ai/intelligence/ml/predict/${hostname}`);
        const data = await res.json();
        if (data.anomaly_predictions) {
          setAnomalies(data.anomaly_predictions);
        }
      } catch (err) {
        console.error('Failed to fetch predictions:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchPredictions();
    const interval = setInterval(fetchPredictions, 60000);
    return () => clearInterval(interval);
  }, [hostname]);

  const hasAnomalies = Object.values(anomalies).some(a => a.is_anomaly);
  const anomalyCount = Object.values(anomalies).filter(a => a.is_anomaly).length;

  if (loading) {
    return (
      <div className="p-4 bg-gray-800/50 rounded-lg border border-gray-700/50">
        <div className="flex items-center gap-2 text-gray-400 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading AI predictions...
        </div>
      </div>
    );
  }

  return (
    <div className={`p-4 rounded-lg border ${
      hasAnomalies 
        ? 'bg-red-500/10 border-red-500/30' 
        : 'bg-purple-500/10 border-purple-500/30'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-medium flex items-center gap-2 text-white">
          <Brain className="w-4 h-4 text-purple-400" />
          AI Predictions
        </h4>
        {hasAnomalies ? (
          <span className="text-xs bg-red-500/20 text-red-400 px-2 py-1 rounded animate-pulse">
            {anomalyCount} Anomal{anomalyCount === 1 ? 'y' : 'ies'}
          </span>
        ) : (
          <span className="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded">
            Normal
          </span>
        )}
      </div>

      <div className="space-y-2">
        {Object.entries(anomalies).map(([metric, data]) => (
          <div key={metric} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              {data.is_anomaly ? (
                <AlertTriangle className="w-3 h-3 text-red-400" />
              ) : data.z_score > 1.5 ? (
                <TrendingUp className="w-3 h-3 text-yellow-400" />
              ) : (
                <Activity className="w-3 h-3 text-green-400" />
              )}
              <span className="text-gray-300 capitalize">
                {metric.replace(/_/g, ' ').replace(' percent', '')}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-white font-mono text-xs">
                {data.current_value}%
              </span>
              <span className={`text-xs ${
                data.is_anomaly ? 'text-red-400' : 
                data.z_score > 1.5 ? 'text-yellow-400' : 'text-gray-500'
              }`}>
                {data.z_score > 0 ? '+' : ''}{data.z_score}σ
              </span>
            </div>
          </div>
        ))}
      </div>

      {Object.keys(anomalies).length === 0 && (
        <div className="text-xs text-gray-500 text-center py-2">
          No prediction data available
        </div>
      )}

      <div className="mt-3 pt-2 border-t border-gray-700/50">
        <a 
          href="/ai-intelligence" 
          className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
        >
          View full AI Intelligence →
        </a>
      </div>
    </div>
  );
}
