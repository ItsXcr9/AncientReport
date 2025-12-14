/**
 * Recording Rules Management Page
 * 
 * Allows users to create, view, edit, and delete recording rules
 * that pre-aggregate expensive Prometheus queries.
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Plus, Edit2, Trash2, RefreshCw, Play, Clock, 
  Activity, X, Check, AlertCircle, Settings, BarChart3, ChevronDown, ChevronUp
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

interface RecordingRule {
  id: string;
  name: string;
  target_id: string;
  source_metric: string;
  labels_filter: Record<string, string>;
  aggregation: string;
  group_by: string;
  interval_seconds: number;
  enabled: boolean;
  description: string;
  last_evaluated: string | null;
  created_at: string;
  updated_at: string;
}

interface Target {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
}

interface RecordedDataPoint {
  timestamp: string;
  group_labels: Record<string, string>;
  value: number;
}

export default function RecordingRules() {
  const [rules, setRules] = useState<RecordingRule[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Chart expansion state
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [chartData, setChartData] = useState<RecordedDataPoint[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  
  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<RecordingRule | null>(null);
  
  // Form state
  const [formName, setFormName] = useState('');
  const [formTargetId, setFormTargetId] = useState('');
  const [formSourceMetric, setFormSourceMetric] = useState('');
  const [formAggregation, setFormAggregation] = useState('avg');
  const [formGroupBy, setFormGroupBy] = useState('');
  const [formInterval, setFormInterval] = useState(60);
  const [formDescription, setFormDescription] = useState('');
  const [formLabelsFilter, setFormLabelsFilter] = useState('');

  const fetchRules = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/recording-rules');
      const data = await res.json();
      setRules(data.rules || []);
    } catch (err) {
      setError('Failed to load recording rules');
    } finally {
      setLoading(false);
    }
  };

  const fetchTargets = async () => {
    try {
      const res = await fetch('/api/prometheus/targets');
      const data = await res.json();
      // Handle both array response and {targets: [...]} response
      const targetList = Array.isArray(data) ? data : (data.targets || []);
      setTargets(targetList);
    } catch (err) {
      console.error('Failed to load targets:', err);
    }
  };

  const fetchMetricsForTarget = async (targetId: string) => {
    if (!targetId) {
      setMetrics([]);
      return;
    }
    try {
      setMetricsLoading(true);
      const res = await fetch(`/api/prometheus/scraped/metrics?target_id=${targetId}`);
      const data = await res.json();
      const metricNames = (data.metrics || []).map((m: any) => typeof m === 'string' ? m : m.name);
      setMetrics(metricNames);
    } catch (err) {
      console.error('Failed to load metrics:', err);
      setMetrics([]);
    } finally {
      setMetricsLoading(false);
    }
  };

  const fetchChartData = async (ruleId: string) => {
    try {
      setChartLoading(true);
      const res = await fetch(`/api/recording-rules/${ruleId}/series`);
      const data = await res.json();
      setChartData(data.data || []);
    } catch (err) {
      console.error('Failed to load chart data:', err);
      setChartData([]);
    } finally {
      setChartLoading(false);
    }
  };

  useEffect(() => {
    fetchRules();
    fetchTargets();
  }, []);

  useEffect(() => {
    if (formTargetId) {
      fetchMetricsForTarget(formTargetId);
    } else {
      setMetrics([]);
    }
  }, [formTargetId]);

  useEffect(() => {
    if (expandedRuleId) {
      fetchChartData(expandedRuleId);
    }
  }, [expandedRuleId]);

  const openCreateModal = () => {
    setEditingRule(null);
    setFormName('');
    setFormTargetId('');
    setFormSourceMetric('');
    setFormAggregation('avg');
    setFormGroupBy('');
    setFormInterval(60);
    setFormDescription('');
    setFormLabelsFilter('');
    setMetrics([]);
    setShowModal(true);
  };

  const openEditModal = (rule: RecordingRule) => {
    setEditingRule(rule);
    setFormName(rule.name);
    setFormTargetId(rule.target_id);
    setFormSourceMetric(rule.source_metric);
    setFormAggregation(rule.aggregation);
    setFormGroupBy(rule.group_by);
    setFormInterval(rule.interval_seconds);
    setFormDescription(rule.description);
    setFormLabelsFilter(Object.keys(rule.labels_filter).length > 0 ? JSON.stringify(rule.labels_filter) : '');
    setShowModal(true);
    fetchMetricsForTarget(rule.target_id);
  };

  const handleSubmit = async () => {
    try {
      let labelsFilter = {};
      if (formLabelsFilter.trim()) {
        try {
          labelsFilter = JSON.parse(formLabelsFilter);
        } catch {
          setError('Invalid JSON in labels filter');
          return;
        }
      }

      const payload = {
        name: formName,
        target_id: formTargetId,
        source_metric: formSourceMetric,
        aggregation: formAggregation,
        group_by: formGroupBy,
        interval_seconds: formInterval,
        description: formDescription,
        labels_filter: labelsFilter
      };

      if (editingRule) {
        await fetch(`/api/recording-rules/${editingRule.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        await fetch('/api/recording-rules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      setShowModal(false);
      fetchRules();
    } catch (err) {
      setError('Failed to save recording rule');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this recording rule? This will also delete all pre-aggregated data.')) return;
    
    try {
      await fetch(`/api/recording-rules/${id}`, { method: 'DELETE' });
      fetchRules();
    } catch (err) {
      setError('Failed to delete recording rule');
    }
  };

  const handleEvaluate = async (id: string) => {
    try {
      await fetch(`/api/recording-rules/${id}/evaluate`, { method: 'POST' });
      fetchRules();
      // Refresh chart if expanded
      if (expandedRuleId === id) {
        fetchChartData(id);
      }
    } catch (err) {
      setError('Failed to evaluate recording rule');
    }
  };

  const handleToggle = async (rule: RecordingRule) => {
    try {
      await fetch(`/api/recording-rules/${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !rule.enabled })
      });
      fetchRules();
    } catch (err) {
      setError('Failed to toggle recording rule');
    }
  };

  const toggleChart = (ruleId: string) => {
    if (expandedRuleId === ruleId) {
      setExpandedRuleId(null);
      setChartData([]);
    } else {
      setExpandedRuleId(ruleId);
    }
  };

  const getTargetName = (targetId: string) => {
    const target = targets.find(t => t.id === targetId);
    return target?.name || targetId;
  };

  // Process chart data for recharts - group by label combination
  const processChartData = () => {
    const groups: Record<string, { time: string; value: number }[]> = {};
    
    chartData.forEach(point => {
      const labelKey = Object.keys(point.group_labels).length > 0 
        ? Object.values(point.group_labels).join(', ')
        : 'value';
      
      if (!groups[labelKey]) {
        groups[labelKey] = [];
      }
      groups[labelKey].push({
        time: new Date(point.timestamp).toLocaleTimeString(),
        value: point.value
      });
    });
    
    // Merge into single array with time as key
    const timeMap: Record<string, Record<string, number>> = {};
    Object.entries(groups).forEach(([label, points]) => {
      points.forEach(p => {
        if (!timeMap[p.time]) timeMap[p.time] = { time: p.time } as any;
        timeMap[p.time][label] = p.value;
      });
    });
    
    return { 
      data: Object.values(timeMap),
      labels: Object.keys(groups)
    };
  };

  const COLORS = ['#00F3FF', '#FF6B6B', '#4ECDC4', '#FFE66D', '#95E1D3', '#F38181'];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-cyan-500" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Settings className="w-6 h-6 text-cyan-400" />
            Recording Rules
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Pre-aggregate expensive queries for faster dashboard loading
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded-lg text-white transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Rule
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300">
          <AlertCircle className="w-5 h-5" />
          {error}
          <button onClick={() => setError(null)} className="ml-auto">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Rules List */}
      <div className="space-y-4">
        {rules.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Activity className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>No recording rules configured</p>
            <p className="text-sm mt-2">Create a rule to pre-aggregate expensive metrics</p>
          </div>
        ) : (
          rules.map(rule => (
            <motion.div
              key={rule.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-xl overflow-hidden"
            >
              <div className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => handleToggle(rule)}
                        className={`w-10 h-5 rounded-full relative transition-colors ${
                          rule.enabled ? 'bg-cyan-500' : 'bg-gray-600'
                        }`}
                      >
                        <span className={`absolute w-4 h-4 bg-white rounded-full top-0.5 transition-transform ${
                          rule.enabled ? 'translate-x-5' : 'translate-x-0.5'
                        }`} />
                      </button>
                      <h3 className="text-lg font-medium text-white">{rule.name}</h3>
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        rule.enabled 
                          ? 'bg-green-500/20 text-green-400' 
                          : 'bg-gray-500/20 text-gray-400'
                      }`}>
                        {rule.enabled ? 'Active' : 'Disabled'}
                      </span>
                    </div>
                    
                    {rule.description && (
                      <p className="text-gray-400 text-sm mt-1">{rule.description}</p>
                    )}
                    
                    <div className="flex flex-wrap gap-4 mt-3 text-sm text-gray-400">
                      <span>Target: <span className="text-gray-300">{getTargetName(rule.target_id)}</span></span>
                      <span>Metric: <code className="text-cyan-400">{rule.source_metric}</code></span>
                      <span>Aggregation: <span className="text-orange-400">{rule.aggregation}</span></span>
                      <span>Interval: <span className="text-gray-300">{rule.interval_seconds}s</span></span>
                    </div>
                    
                    {rule.group_by && (
                      <div className="text-sm text-gray-400 mt-1">
                        Group By: <code className="text-purple-400">{rule.group_by}</code>
                      </div>
                    )}
                    
                    {Object.keys(rule.labels_filter).length > 0 && (
                      <div className="text-sm text-gray-400 mt-1">
                        Labels: <code className="text-yellow-400">{JSON.stringify(rule.labels_filter)}</code>
                      </div>
                    )}
                    
                    {rule.last_evaluated && rule.last_evaluated !== '1970-01-01T03:30:00' && (
                      <div className="flex items-center gap-1 mt-2 text-xs text-gray-500">
                        <Clock className="w-3 h-3" />
                        Last evaluated: {new Date(rule.last_evaluated).toLocaleString()}
                      </div>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => toggleChart(rule.id)}
                      className={`p-2 rounded-lg transition-colors ${
                        expandedRuleId === rule.id 
                          ? 'text-cyan-400 bg-cyan-500/10' 
                          : 'text-gray-400 hover:text-cyan-400 hover:bg-cyan-500/10'
                      }`}
                      title="View Results"
                    >
                      <BarChart3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleEvaluate(rule.id)}
                      className="p-2 text-gray-400 hover:text-green-400 hover:bg-green-500/10 rounded-lg transition-colors"
                      title="Evaluate now"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => openEditModal(rule)}
                      className="p-2 text-gray-400 hover:text-cyan-400 hover:bg-cyan-500/10 rounded-lg transition-colors"
                      title="Edit"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(rule.id)}
                      className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
              
              {/* Chart Section */}
              <AnimatePresence>
                {expandedRuleId === rule.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="border-t border-gray-700/50"
                  >
                    <div className="p-4">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-sm font-medium text-gray-300">Pre-aggregated Results (Last Hour)</h4>
                        <button 
                          onClick={() => fetchChartData(rule.id)}
                          className="text-xs text-gray-500 hover:text-cyan-400 flex items-center gap-1"
                        >
                          <RefreshCw className="w-3 h-3" /> Refresh
                        </button>
                      </div>
                      
                      {chartLoading ? (
                        <div className="flex items-center justify-center h-48">
                          <RefreshCw className="w-6 h-6 animate-spin text-cyan-500" />
                        </div>
                      ) : chartData.length === 0 ? (
                        <div className="flex items-center justify-center h-48 text-gray-500">
                          <div className="text-center">
                            <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">No data yet</p>
                            <p className="text-xs mt-1">Wait for evaluations or click "Evaluate now"</p>
                          </div>
                        </div>
                      ) : (
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={processChartData().data}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                              <XAxis 
                                dataKey="time" 
                                stroke="#9CA3AF" 
                                fontSize={11}
                              />
                              <YAxis stroke="#9CA3AF" fontSize={11} />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: '#1F2937', 
                                  border: '1px solid #374151',
                                  borderRadius: '8px'
                                }} 
                              />
                              <Legend />
                              {processChartData().labels.map((label, idx) => (
                                <Line
                                  key={label}
                                  type="monotone"
                                  dataKey={label}
                                  stroke={COLORS[idx % COLORS.length]}
                                  strokeWidth={2}
                                  dot={false}
                                />
                              ))}
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))
        )}
      </div>

      {/* Create/Edit Modal */}
      <AnimatePresence>
        {showModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => setShowModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto"
              onClick={e => e.stopPropagation()}
            >
              <h2 className="text-xl font-bold text-white mb-4">
                {editingRule ? 'Edit Recording Rule' : 'Create Recording Rule'}
              </h2>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Rule Name *</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={e => setFormName(e.target.value)}
                    placeholder="e.g., kafka_lag_sum_by_topic"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Target * ({targets.length} available)</label>
                  <select
                    value={formTargetId}
                    onChange={e => {
                      setFormTargetId(e.target.value);
                      setFormSourceMetric(''); // Reset metric when target changes
                    }}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="">Select a target...</option>
                    {targets.map(t => (
                      <option key={t.id} value={t.id}>{t.name} ({t.url})</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    Source Metric * {metricsLoading && <span className="text-cyan-400">(loading...)</span>}
                    {!metricsLoading && formTargetId && <span className="text-gray-500">({metrics.length} available)</span>}
                  </label>
                  <select
                    value={formSourceMetric}
                    onChange={e => setFormSourceMetric(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500 disabled:opacity-50"
                    disabled={!formTargetId || metricsLoading}
                  >
                    <option value="">
                      {!formTargetId 
                        ? 'Select a target first...' 
                        : metricsLoading 
                          ? 'Loading metrics...' 
                          : 'Select a metric...'}
                    </option>
                    {metrics.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Aggregation</label>
                    <select
                      value={formAggregation}
                      onChange={e => setFormAggregation(e.target.value)}
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option value="avg">Average (avg)</option>
                      <option value="sum">Sum (sum)</option>
                      <option value="max">Maximum (max)</option>
                      <option value="min">Minimum (min)</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Interval (seconds)</label>
                    <input
                      type="number"
                      value={formInterval}
                      onChange={e => setFormInterval(Number(e.target.value))}
                      min={10}
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Group By (comma-separated label keys)</label>
                  <input
                    type="text"
                    value={formGroupBy}
                    onChange={e => setFormGroupBy(e.target.value)}
                    placeholder="e.g., topic, partition"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Labels Filter (JSON)</label>
                  <input
                    type="text"
                    value={formLabelsFilter}
                    onChange={e => setFormLabelsFilter(e.target.value)}
                    placeholder='{"topic": "orders"}'
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Description</label>
                  <textarea
                    value={formDescription}
                    onChange={e => setFormDescription(e.target.value)}
                    placeholder="What does this rule aggregate?"
                    rows={2}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-cyan-500 resize-none"
                  />
                </div>
              </div>
              
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={!formName || !formTargetId || !formSourceMetric}
                  className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-white transition-colors"
                >
                  <Check className="w-4 h-4" />
                  {editingRule ? 'Update' : 'Create'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
