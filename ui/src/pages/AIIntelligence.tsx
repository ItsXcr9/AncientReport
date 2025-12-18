import { useState, useEffect } from 'react';
import { 
  Brain, TrendingUp, AlertTriangle, Activity, 
  Calendar, Target, Loader2, RefreshCw, Clock,
  ChevronDown, ChevronUp, Lightbulb, Zap
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOutletContext } from 'react-router-dom';

interface Prediction {
  metric: string;
  hostname: string;
  current_value: number;
  predicted_value: number;
  predicted_date: string;
  days_until_critical: number;
  trend: string;
  confidence: number;
  recommendation: string;
  method: string;
}

interface AnomalyPrediction {
  metric: string;
  hostname: string;
  current_value: number;
  anomaly_probability: number;
  is_anomaly: boolean;
  severity: string;
  direction: string;
  z_score: number;
  recommendation: string;
  method: string;
}

interface Incident {
  id: string;
  alert_count: number;
  severity: string;
  affected_hosts: string[];
  root_cause_candidates: { cause: string; confidence: number }[];
  start_time: string;
  end_time: string;
}

interface MLStatus {
  status: string;
  capabilities: {
    prophet_forecasting: boolean;
    isolation_forest_anomaly: boolean;
    pandas_dataframes: boolean;
  };
}

export default function AIIntelligence() {
  const { selectedServer } = useOutletContext<{ selectedServer: string | null }>();
  const [predictions, setPredictions] = useState<Record<string, Prediction>>({});
  const [anomalies, setAnomalies] = useState<Record<string, AnomalyPrediction>>({});
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [mlStatus, setMlStatus] = useState<MLStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [expandedSection, setExpandedSection] = useState<string>('predictions');

  const hostname = selectedServer || 'xcr9';

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch ML predictions
      const predRes = await fetch(`/api/v3/ai/intelligence/ml/predict/${hostname}`);
      const predData = await predRes.json();
      
      if (predData.resource_predictions) {
        setPredictions(predData.resource_predictions);
      }
      if (predData.anomaly_predictions) {
        setAnomalies(predData.anomaly_predictions);
      }

      // Fetch alert correlations
      const corrRes = await fetch('/api/v3/ai/intelligence/correlate/recent?hours=24');
      const corrData = await corrRes.json();
      setIncidents(corrData.incidents || []);

      // Fetch ML status
      const statusRes = await fetch('/api/v3/ai/intelligence/ml/status');
      const statusData = await statusRes.json();
      setMlStatus(statusData);

      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      setError('Failed to fetch AI intelligence data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [hostname]);

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'text-red-400 bg-red-500/20 border-red-500/40';
      case 'high': return 'text-orange-400 bg-orange-500/20 border-orange-500/40';
      case 'medium': return 'text-yellow-400 bg-yellow-500/20 border-yellow-500/40';
      default: return 'text-green-400 bg-green-500/20 border-green-500/40';
    }
  };

  const getTrendIcon = (trend: string) => {
    if (trend === 'increasing') return <TrendingUp className="w-4 h-4 text-red-400" />;
    if (trend === 'decreasing') return <TrendingUp className="w-4 h-4 text-green-400 transform rotate-180" />;
    return <Activity className="w-4 h-4 text-gray-400" />;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-display tracking-tight flex items-center gap-3">
            <Brain className="w-7 h-7 text-purple-400" />
            AI Intelligence
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            ML-powered predictions, anomaly detection, and alert correlation for <span className="text-blue-400">{hostname}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Updated: {lastUpdated}</span>
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-3 py-2 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/40 rounded-lg text-purple-400 text-sm flex items-center gap-2 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ML Status Banner */}
      {mlStatus && (
        <div className="p-4 bg-gradient-to-r from-purple-500/10 to-blue-500/10 rounded-lg border border-purple-500/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Zap className="w-5 h-5 text-purple-400" />
              <span className="text-sm text-gray-300">ML Engine Status:</span>
              <span className={`text-sm font-medium ${mlStatus.status === 'operational' ? 'text-green-400' : 'text-yellow-400'}`}>
                {mlStatus.status}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-gray-400">
              <span className={mlStatus.capabilities.prophet_forecasting ? 'text-green-400' : 'text-red-400'}>
                Prophet: {mlStatus.capabilities.prophet_forecasting ? '✓' : '✗'}
              </span>
              <span className={mlStatus.capabilities.isolation_forest_anomaly ? 'text-green-400' : 'text-red-400'}>
                IsolationForest: {mlStatus.capabilities.isolation_forest_anomaly ? '✓' : '✗'}
              </span>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-500/10 rounded-lg border border-red-500/30 text-red-400">
          {error}
        </div>
      )}

      {/* Resource Predictions */}
      <section className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => setExpandedSection(expandedSection === 'predictions' ? '' : 'predictions')}
          className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Calendar className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold text-white">Resource Predictions</h2>
            <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded">
              {Object.keys(predictions).length} metrics
            </span>
          </div>
          {expandedSection === 'predictions' ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>
        
        <AnimatePresence>
          {expandedSection === 'predictions' && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="border-t border-gray-700/50"
            >
              <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(predictions).length > 0 ? (
                  Object.entries(predictions).map(([metric, pred]) => (
                    <div key={metric} className="p-4 bg-gray-900/50 rounded-lg border border-gray-700/50">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="font-medium text-white capitalize">
                          {metric.replace(/_/g, ' ')}
                        </h3>
                        {getTrendIcon(pred.trend)}
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Current</span>
                          <span className="text-white font-mono">{pred.current_value}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Predicted</span>
                          <span className={`font-mono ${pred.predicted_value > 80 ? 'text-red-400' : 'text-green-400'}`}>
                            {pred.predicted_value}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Days Until Critical</span>
                          <span className={`font-mono ${pred.days_until_critical < 7 ? 'text-red-400' : pred.days_until_critical < 14 ? 'text-yellow-400' : 'text-green-400'}`}>
                            {pred.days_until_critical}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Confidence</span>
                          <span className="text-blue-400 font-mono">{(pred.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Method</span>
                          <span className="text-purple-400 text-xs">{pred.method}</span>
                        </div>
                      </div>
                      <div className="mt-3 pt-3 border-t border-gray-700/50">
                        <p className="text-xs text-gray-400">{pred.recommendation}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="col-span-3 p-8 text-center text-gray-500">
                    {loading ? (
                      <Loader2 className="w-6 h-6 animate-spin mx-auto" />
                    ) : (
                      'No predictions available - need more historical data'
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {/* Anomaly Detection */}
      <section className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => setExpandedSection(expandedSection === 'anomalies' ? '' : 'anomalies')}
          className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Target className="w-5 h-5 text-orange-400" />
            <h2 className="text-lg font-semibold text-white">Anomaly Detection</h2>
            {Object.values(anomalies).some(a => a.is_anomaly) && (
              <span className="text-xs bg-red-500/20 text-red-400 px-2 py-1 rounded animate-pulse">
                Anomalies Detected
              </span>
            )}
          </div>
          {expandedSection === 'anomalies' ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>
        
        <AnimatePresence>
          {expandedSection === 'anomalies' && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="border-t border-gray-700/50"
            >
              <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(anomalies).length > 0 ? (
                  Object.entries(anomalies).map(([metric, anomaly]) => (
                    <div 
                      key={metric} 
                      className={`p-4 rounded-lg border ${anomaly.is_anomaly ? 'bg-red-500/10 border-red-500/40' : 'bg-gray-900/50 border-gray-700/50'}`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="font-medium text-white capitalize">
                          {metric.replace(/_/g, ' ')}
                        </h3>
                        <span className={`text-xs px-2 py-1 rounded ${getSeverityColor(anomaly.severity)}`}>
                          {anomaly.severity}
                        </span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Current Value</span>
                          <span className="text-white font-mono">{anomaly.current_value}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Anomaly Probability</span>
                          <span className={`font-mono ${anomaly.anomaly_probability > 0.5 ? 'text-red-400' : 'text-green-400'}`}>
                            {(anomaly.anomaly_probability * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Z-Score</span>
                          <span className={`font-mono ${Math.abs(anomaly.z_score) > 2 ? 'text-yellow-400' : 'text-gray-300'}`}>
                            {anomaly.z_score > 0 ? '+' : ''}{anomaly.z_score}σ
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Method</span>
                          <span className="text-purple-400 text-xs">{anomaly.method}</span>
                        </div>
                      </div>
                      <div className="mt-3 pt-3 border-t border-gray-700/50">
                        <p className="text-xs text-gray-400">{anomaly.recommendation}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="col-span-3 p-8 text-center text-gray-500">
                    {loading ? (
                      <Loader2 className="w-6 h-6 animate-spin mx-auto" />
                    ) : (
                      'No anomaly data available'
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {/* Alert Correlation */}
      <section className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => setExpandedSection(expandedSection === 'correlation' ? '' : 'correlation')}
          className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-400" />
            <h2 className="text-lg font-semibold text-white">Alert Correlation (24h)</h2>
            <span className="text-xs bg-gray-500/20 text-gray-400 px-2 py-1 rounded">
              {incidents.length} incidents
            </span>
          </div>
          {expandedSection === 'correlation' ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>
        
        <AnimatePresence>
          {expandedSection === 'correlation' && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="border-t border-gray-700/50"
            >
              <div className="p-4">
                {incidents.length > 0 ? (
                  <div className="space-y-3">
                    {incidents.map((incident, idx) => (
                      <div key={incident.id || idx} className="p-4 bg-gray-900/50 rounded-lg border border-gray-700/50">
                        <div className="flex items-center justify-between mb-2">
                          <span className={`text-sm px-2 py-1 rounded ${getSeverityColor(incident.severity)}`}>
                            {incident.severity}
                          </span>
                          <span className="text-xs text-gray-500">{incident.alert_count} alerts</span>
                        </div>
                        <div className="text-sm text-gray-300 mb-2">
                          Hosts: {incident.affected_hosts.join(', ')}
                        </div>
                        {incident.root_cause_candidates.length > 0 && (
                          <div className="text-xs text-gray-400">
                            <Lightbulb className="w-3 h-3 inline mr-1 text-yellow-400" />
                            Root cause: {incident.root_cause_candidates[0].cause} 
                            ({(incident.root_cause_candidates[0].confidence * 100).toFixed(0)}% confidence)
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-8 text-center text-gray-500">
                    <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-green-500/50" />
                    No correlated incidents in the last 24 hours
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
}
