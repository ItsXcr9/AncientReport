import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Bell, 
  Plus, 
  Trash2, 
  Edit2,
  Clock,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Activity,
  ArrowUp,
  ArrowDown,
  Equal
} from 'lucide-react';

interface AlertRule {
  id: string;
  name: string;
  target_id: string;
  metric_name: string;
  condition: string;
  threshold: number;
  duration_seconds: number;
  notification_channel: string;
  notification_config: string;
  enabled: boolean;
  last_triggered: string | null;
  created_at: string;
}

interface AlertHistory {
  id: string;
  rule_id: string;
  rule_name: string;
  triggered_at: string;
  value: number;
  threshold: number;
  status: string;
  notified: boolean;
}

interface Target {
  id: string;
  name: string;
}

export default function Alerts() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [history, setHistory] = useState<AlertHistory[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  // Form state
  const [formName, setFormName] = useState('');
  const [formTargetId, setFormTargetId] = useState('');
  const [formMetric, setFormMetric] = useState('');
  const [formCondition, setFormCondition] = useState('gt');
  const [formThreshold, setFormThreshold] = useState('');
  const [formWebhookUrl, setFormWebhookUrl] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (formTargetId) {
      fetchMetrics(formTargetId);
    }
  }, [formTargetId]);

  const fetchAll = async () => {
    await Promise.all([fetchRules(), fetchHistory(), fetchTargets()]);
    setLoading(false);
  };

  const fetchRules = async () => {
    try {
      const res = await fetch('/api/alerts/rules');
      if (res.ok) {
        const data = await res.json();
        setRules(data);
      }
    } catch (e) {
      console.error('Failed to fetch rules:', e);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch('/api/alerts/history?limit=50');
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
    } catch (e) {
      console.error('Failed to fetch history:', e);
    }
  };

  const fetchTargets = async () => {
    try {
      const res = await fetch('/api/prometheus/targets');
      if (res.ok) {
        const data = await res.json();
        setTargets(data.filter((t: any) => t.enabled));
      }
    } catch (e) {
      console.error('Failed to fetch targets:', e);
    }
  };

  const fetchMetrics = async (targetId: string) => {
    try {
      const res = await fetch(`/api/prometheus/scraped/metrics?target_id=${targetId}`);
      if (res.ok) {
        const data = await res.json();
        const metricNames = (data.metrics || []).map((m: any) => typeof m === 'string' ? m : m.name);
        setMetrics(metricNames);
      }
    } catch (e) {
      console.error('Failed to fetch metrics:', e);
    }
  };

  const handleCreate = async () => {
    if (!formName.trim() || !formTargetId || !formMetric || !formThreshold) return;
    setCreating(true);
    
    try {
      const res = await fetch('/api/alerts/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formName,
          target_id: formTargetId,
          metric_name: formMetric,
          condition: formCondition,
          threshold: parseFloat(formThreshold),
          notification_config: formWebhookUrl ? JSON.stringify({ url: formWebhookUrl }) : '{}'
        })
      });
      
      if (res.ok) {
        await fetchRules();
        setShowCreateModal(false);
        resetForm();
      }
    } catch (e) {
      console.error('Failed to create rule:', e);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this alert rule?')) return;
    try {
      await fetch(`/api/alerts/rules/${id}`, { method: 'DELETE' });
      await fetchRules();
    } catch (e) {
      console.error('Failed to delete rule:', e);
    }
  };

  const resetForm = () => {
    setFormName('');
    setFormTargetId('');
    setFormMetric('');
    setFormCondition('gt');
    setFormThreshold('');
    setFormWebhookUrl('');
  };

  const getConditionIcon = (condition: string) => {
    switch (condition) {
      case 'gt':
      case 'gte':
        return <ArrowUp size={14} />;
      case 'lt':
      case 'lte':
        return <ArrowDown size={14} />;
      default:
        return <Equal size={14} />;
    }
  };

  const getConditionText = (condition: string) => {
    const map: Record<string, string> = {
      'gt': '>',
      'gte': '≥',
      'lt': '<',
      'lte': '≤',
      'eq': '='
    };
    return map[condition] || condition;
  };

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Bell className="text-neon-blue" size={28} />
            Metric Alerts
          </h1>
          <p className="text-gray-400 mt-1">Configure threshold alerts with webhook notifications</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
        >
          <Plus size={18} />
          Create Alert
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-neon-blue" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Alert Rules */}
          <div className="lg:col-span-2 space-y-4">
            <h2 className="text-lg font-semibold text-white">Alert Rules</h2>
            
            {rules.length === 0 ? (
              <div className="glass-card rounded-xl p-8 text-center">
                <Bell className="mx-auto mb-4 text-gray-500" size={40} />
                <h3 className="text-lg font-semibold text-white mb-2">No Alert Rules</h3>
                <p className="text-gray-400 mb-4">Create your first alert rule to start monitoring</p>
                <button
                  onClick={() => setShowCreateModal(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
                >
                  <Plus size={18} />
                  Create Alert
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {rules.map((rule) => (
                  <motion.div
                    key={rule.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="glass-card rounded-xl p-4 border border-white/5 hover:border-neon-blue/30 transition-all group"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          rule.enabled ? 'bg-green-500/10' : 'bg-gray-500/10'
                        }`}>
                          {rule.enabled ? (
                            <CheckCircle className="text-green-400" size={20} />
                          ) : (
                            <XCircle className="text-gray-500" size={20} />
                          )}
                        </div>
                        <div>
                          <h3 className="font-semibold text-white">{rule.name}</h3>
                          <p className="text-sm text-gray-400">
                            {rule.metric_name} {getConditionText(rule.condition)} {rule.threshold}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleDelete(rule.id)}
                        className="p-2 text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    
                    {rule.last_triggered && (
                      <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-2 text-xs text-amber-400">
                        <AlertTriangle size={12} />
                        Last triggered: {formatDate(rule.last_triggered)}
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            )}
          </div>

          {/* Alert History */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Recent Alerts</h2>
            
            {history.length === 0 ? (
              <div className="glass-card rounded-xl p-6 text-center">
                <Activity className="mx-auto mb-3 text-gray-500" size={32} />
                <p className="text-gray-400 text-sm">No alerts triggered yet</p>
              </div>
            ) : (
              <div className="glass-card rounded-xl p-4 max-h-96 overflow-y-auto space-y-3">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-start gap-3 p-3 rounded-lg bg-white/5"
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      item.status === 'firing' ? 'bg-red-500/20' : 'bg-green-500/20'
                    }`}>
                      {item.status === 'firing' ? (
                        <AlertTriangle className="text-red-400" size={16} />
                      ) : (
                        <CheckCircle className="text-green-400" size={16} />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-white truncate">{item.rule_name}</p>
                      <p className="text-xs text-gray-400">
                        Value: {item.value.toFixed(2)} (threshold: {item.threshold})
                      </p>
                      <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                        <Clock size={10} />
                        {formatDate(item.triggered_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => setShowCreateModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card rounded-xl p-6 w-full max-w-md mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-bold text-white mb-4">Create Alert Rule</h2>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Alert Name</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g., High Kafka Lag"
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Target</label>
                  <select
                    value={formTargetId}
                    onChange={(e) => setFormTargetId(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                  >
                    <option value="">Select target...</option>
                    {targets.map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Metric</label>
                  <select
                    value={formMetric}
                    onChange={(e) => setFormMetric(e.target.value)}
                    disabled={!formTargetId}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none disabled:opacity-50"
                  >
                    <option value="">Select metric...</option>
                    {metrics.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Condition</label>
                    <select
                      value={formCondition}
                      onChange={(e) => setFormCondition(e.target.value)}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                    >
                      <option value="gt">{'>'} (greater than)</option>
                      <option value="gte">{'≥'} (greater or equal)</option>
                      <option value="lt">{'<'} (less than)</option>
                      <option value="lte">{'≤'} (less or equal)</option>
                      <option value="eq">{'='} (equal)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">Threshold</label>
                    <input
                      type="number"
                      value={formThreshold}
                      onChange={(e) => setFormThreshold(e.target.value)}
                      placeholder="1000"
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Webhook URL (optional)</label>
                  <input
                    type="url"
                    value={formWebhookUrl}
                    onChange={(e) => setFormWebhookUrl(e.target.value)}
                    placeholder="https://hooks.slack.com/..."
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    POST request will be sent when threshold is exceeded
                  </p>
                </div>
              </div>
              
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => { setShowCreateModal(false); resetForm(); }}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={!formName.trim() || !formTargetId || !formMetric || !formThreshold || creating}
                  className="px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {creating ? 'Creating...' : 'Create Alert'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
