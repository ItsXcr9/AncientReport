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
    // Reset all form state safely
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
    
    // Explicitly set showModal to true after a small delay to ensure state creates a clean render cycle if needed,
    // though purely React state updates are batched.
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
    // Fetch metrics for the existing target so the dropdown populates
    if (rule.target_id) {
       fetchMetricsForTarget(rule.target_id);
    }
    setShowModal(true);
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

  const COLORS = ['#00F3FF', '#8B5CF6', '#10B981', '#F59E0B', '#EF4444', '#06B6D4'];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="relative">
          <div className="w-12 h-12 rounded-full border-2 border-neon-blue/20 border-t-neon-blue animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-2 h-2 bg-neon-blue rounded-full animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold text-white tracking-tight flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-neon-blue/20 to-neon-purple/20 rounded-xl border border-white/5">
              <Settings className="w-6 h-6 text-neon-blue" />
            </div>
            Recording Rules
          </h1>
          <p className="text-gray-400 text-sm mt-2 ml-1">
            Pre-aggregate expensive queries for ultra-fast dashboard rendering
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="group relative flex items-center gap-2 px-5 py-2.5 bg-neon-blue text-black font-bold rounded-xl hover:bg-neon-blue/90 transition-all shadow-[0_0_20px_rgba(0,243,255,0.3)] hover:shadow-[0_0_30px_rgba(0,243,255,0.5)] transform hover:-translate-y-0.5 overflow-hidden"
        >
          <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
          <Plus className="w-5 h-5 relative z-10" />
          <span className="relative z-10">Create Rule</span>
        </button>
      </div>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-300 backdrop-blur-sm shadow-lg shadow-red-500/5"
          >
            <AlertCircle className="w-5 h-5 text-red-500" />
            {error}
            <button onClick={() => setError(null)} className="ml-auto hover:text-white transition-colors">
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Rules List */}
      <div className="space-y-4">
        {rules.length === 0 ? (
          <div className="glass-card rounded-2xl p-16 text-center border-dashed border-2 border-white/10 bg-black/20">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-white/5 flex items-center justify-center relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-tr from-neon-blue/20 to-neon-purple/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <Activity className="w-10 h-10 text-gray-500 group-hover:text-white transition-colors relative z-10" />
            </div>
            <h3 className="text-2xl font-bold text-white mb-2 font-display">No Rules Configured</h3>
            <p className="text-gray-400 mb-8 max-w-sm mx-auto">Create a recording rule to pre-calculate complex metrics and speed up your dashboards.</p>
            <button
              onClick={openCreateModal}
              className="inline-flex items-center gap-2 px-6 py-3 bg-white/10 border border-white/20 text-white font-medium rounded-xl hover:bg-white/20 hover:border-white/30 transition-all hover:scale-105"
            >
              <Plus size={18} />
              Add First Rule
            </button>
          </div>
        ) : (
          rules.map(rule => (
            <motion.div
              key={rule.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-xl overflow-hidden group hover:border-neon-blue/30 transition-all duration-300 relative"
            >
               {/* Cyberpunk Glow Border on Hover */}
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-neon-blue/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-4">
                      {/* Toggle Switch */}
                      <button
                        onClick={() => handleToggle(rule)}
                        className={`w-11 h-6 rounded-full relative transition-colors duration-300 flex-shrink-0 ${
                          rule.enabled 
                            ? 'bg-neon-blue/20 border border-neon-blue/50 shadow-[0_0_10px_rgba(0,243,255,0.2)]' 
                            : 'bg-white/5 border border-white/10 hover:border-white/20'
                        }`}
                      >
                        <span className={`absolute w-4 h-4 rounded-full top-1/2 -translate-y-1/2 transition-all duration-300 shadow-sm ${
                          rule.enabled 
                            ? 'left-[22px] bg-neon-blue shadow-[0_0_8px_rgba(0,243,255,0.8)]' 
                            : 'left-1 bg-gray-500 group-hover:bg-gray-400'
                        }`} />
                      </button>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3 flex-wrap">
                          <h3 className="text-lg font-bold text-white font-display tracking-tight group-hover:text-neon-blue transition-colors truncate">
                            {rule.name}
                          </h3>
                          <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border flex-shrink-0 ${
                            rule.enabled 
                              ? 'bg-neon-green/10 text-neon-green border-neon-green/20 shadow-[0_0_10px_rgba(16,185,129,0.1)]' 
                              : 'bg-gray-500/10 text-gray-400 border-gray-500/20'
                          }`}>
                            {rule.enabled ? 'Running' : 'Paused'}
                          </span>
                        </div>
                        {rule.description && (
                          <p className="text-gray-400 text-sm mt-1 font-light truncate">{rule.description}</p>
                        )}
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
                      <div className="flex flex-col gap-1 p-2 rounded-lg bg-black/20 border border-white/5">
                        <span className="text-[10px] uppercase text-gray-500 font-semibold tracking-wider">Target</span>
                        <span className="text-sm text-gray-200 font-mono truncate" title={getTargetName(rule.target_id)}>
                          <span className="w-1.5 h-1.5 rounded-full bg-neon-purple inline-block mr-2" />
                          {getTargetName(rule.target_id)}
                        </span>
                      </div>
                      <div className="flex flex-col gap-1 p-2 rounded-lg bg-black/20 border border-white/5">
                        <span className="text-[10px] uppercase text-gray-500 font-semibold tracking-wider">Source Metric</span>
                        <span className="text-sm text-neon-blue font-mono truncate" title={rule.source_metric}>
                          {rule.source_metric}
                        </span>
                      </div>
                      <div className="flex flex-col gap-1 p-2 rounded-lg bg-black/20 border border-white/5">
                        <span className="text-[10px] uppercase text-gray-500 font-semibold tracking-wider">Aggregation</span>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-orange-400 font-mono font-bold uppercase">{rule.aggregation}</span>
                          <span className="text-xs text-gray-500">every {rule.interval_seconds}s</span>
                        </div>
                      </div>
                      <div className="flex flex-col gap-1 p-2 rounded-lg bg-black/20 border border-white/5">
                         <span className="text-[10px] uppercase text-gray-500 font-semibold tracking-wider">Grouping</span>
                         <span className="text-sm text-gray-300 font-mono truncate">
                           {rule.group_by ? rule.group_by : <span className="text-gray-600 italic">None</span>}
                         </span>
                      </div>
                    </div>
                    
                    {Object.keys(rule.labels_filter).length > 0 && (
                      <div className="mt-3 flex items-center gap-2 text-xs font-mono text-gray-500 ml-1">
                        <span className="text-neon-purple">FILTER</span>
                        <code className="bg-white/5 px-2 py-0.5 rounded border border-white/5 text-gray-300">
                           {JSON.stringify(rule.labels_filter)}
                        </code>
                      </div>
                    )}
                  </div>
                  
                  <div className="flex flex-col gap-2 ml-4">
                     <div className="flex items-center gap-1 bg-black/20 p-1 rounded-xl border border-white/5">
                      <button
                        onClick={() => toggleChart(rule.id)}
                        className={`p-2 rounded-lg transition-all ${
                          expandedRuleId === rule.id 
                            ? 'bg-neon-blue text-black shadow-[0_0_15px_rgba(0,243,255,0.4)]' 
                            : 'text-gray-400 hover:text-white hover:bg-white/10'
                        }`}
                        title="Visualize Data"
                      >
                         {expandedRuleId === rule.id ? <ChevronUp className="w-4 h-4" /> : <BarChart3 className="w-4 h-4" />}
                      </button>
                      <button
                        onClick={() => handleEvaluate(rule.id)}
                        className="p-2 text-gray-400 hover:text-neon-green hover:bg-neon-green/10 rounded-lg transition-colors group/play"
                        title="Evaluate Now"
                      >
                        <Play className="w-4 h-4 group-hover/play:fill-neon-green transition-colors" />
                      </button>
                    </div>
                    
                    <div className="flex items-center gap-1 bg-black/20 p-1 rounded-xl border border-white/5">
                       <button
                        onClick={() => openEditModal(rule)}
                        className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        title="Edit Rule"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(rule.id)}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                        title="Delete Rule"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
                
                {rule.last_evaluated && rule.last_evaluated !== '1970-01-01T03:30:00' && (
                  <div className="flex items-center justify-end gap-1.5 mt-2 text-[10px] text-gray-500 font-mono opacity-70">
                    <Clock className="w-3 h-3" />
                    Last evaluated: {new Date(rule.last_evaluated).toLocaleString()}
                  </div>
                )}
              </div>
              
              {/* Chart Section */}
              <AnimatePresence>
                {expandedRuleId === rule.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="border-t border-white/10 bg-black/40"
                  >
                    <div className="p-5">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2 pl-1">
                          <Activity className="w-3 h-3 text-neon-blue" />
                          Evaluation Results (Last 1h)
                        </h4>
                        <button 
                          onClick={() => fetchChartData(rule.id)}
                          className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-gray-400 hover:text-white hover:border-neon-blue/50 flex items-center gap-2 transition-all"
                        >
                          <RefreshCw className={`w-3 h-3 ${chartLoading ? 'animate-spin' : ''}`} /> 
                          Refresh Data
                        </button>
                      </div>
                      
                      {chartLoading ? (
                        <div className="flex items-center justify-center h-48">
                          <div className="flex flex-col items-center gap-3">
                             <RefreshCw className="w-8 h-8 animate-spin text-neon-blue/50" />
                             <span className="text-xs text-neon-blue/70 font-mono animate-pulse">LOADING METRICS...</span>
                          </div>
                        </div>
                      ) : chartData.length === 0 ? (
                        <div className="flex items-center justify-center h-48 text-gray-500 bg-white/5 rounded-xl border border-dashed border-white/10 mx-1">
                          <div className="text-center">
                            <Activity className="w-10 h-10 mx-auto mb-3 opacity-20" />
                            <p className="text-sm font-medium text-gray-400">No recorded data found</p>
                            <p className="text-xs mt-1 text-gray-600">Wait for the next evaluation cycle or trigger it manually.</p>
                          </div>
                        </div>
                      ) : (
                        <div className="h-64 w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={processChartData().data}>
                              <defs>
                                <linearGradient id="grid-gradient" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="rgba(255,255,255,0.1)" />
                                  <stop offset="95%" stopColor="rgba(255,255,255,0)" />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                              <XAxis 
                                dataKey="time" 
                                stroke="#64748b" 
                                fontSize={10} 
                                tickLine={false}
                                axisLine={false}
                                dy={10}
                                fontFamily="JetBrains Mono"
                              />
                              <YAxis 
                                stroke="#64748b" 
                                fontSize={10} 
                                tickLine={false}
                                axisLine={false}
                                dx={-10}
                                fontFamily="JetBrains Mono"
                              />
                              <Tooltip 
                                contentStyle={{ 
                                  backgroundColor: 'rgba(10, 15, 25, 0.95)', 
                                  border: '1px solid rgba(0, 243, 255, 0.2)',
                                  borderRadius: '12px',
                                  boxShadow: '0 10px 40px -10px rgba(0,0,0,0.8)',
                                  fontSize: '12px',
                                  padding: '12px'
                                }} 
                                itemStyle={{ padding: '2px 0', fontFamily: 'JetBrains Mono' }}
                                labelStyle={{ color: '#94a3b8', marginBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '4px' }}
                              />
                              <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '15px', fontFamily: 'JetBrains Mono' }} iconType="circle" />
                              {processChartData().labels.map((label, idx) => (
                                <Line
                                  key={label}
                                  type="monotone"
                                  dataKey={label}
                                  stroke={COLORS[idx % COLORS.length]}
                                  strokeWidth={2}
                                  dot={false}
                                  activeDot={{ r: 4, strokeWidth: 0, fill: '#fff' }}
                                  animationDuration={1000}
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
            className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-50 p-4"
            onClick={() => setShowModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 20 }}
              className="glass-card-intense rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto border border-white/10 shadow-2xl relative"
              onClick={e => e.stopPropagation()}
            >
              <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-neon-blue via-neon-purple to-neon-blue" />
              
              <div className="p-6 border-b border-white/10 flex items-center justify-between sticky top-0 bg-[#0f1117]/95 backdrop-blur-xl z-10">
                <h2 className="text-xl font-bold text-white flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-neon-blue/10 border border-neon-blue/20 flex items-center justify-center shadow-[0_0_15px_rgba(0,243,255,0.15)]">
                    {editingRule ? <Edit2 className="w-5 h-5 text-neon-blue" /> : <Plus className="w-5 h-5 text-neon-blue" />}
                  </div>
                  <span className="font-display tracking-tight">{editingRule ? 'Edit Recording Rule' : 'Create New Rule'}</span>
                </h2>
                <button 
                  onClick={() => setShowModal(false)} 
                  className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="p-6 space-y-6">
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Rule Name</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={e => setFormName(e.target.value)}
                    placeholder="e.g., kafka_lag_sum_by_topic"
                    className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all placeholder-gray-600 shadow-inner"
                  />
                  <p className="text-xs text-gray-500 mt-2 ml-1 flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-neon-blue"></span>
                    Unique identifier used in ClickHouse tables
                  </p>
                </div>
                
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Target</label>
                    <select
                      value={formTargetId}
                      onChange={e => {
                        setFormTargetId(e.target.value);
                        setFormSourceMetric(''); // Reset metric when target changes
                      }}
                      className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all appearance-none cursor-pointer hover:bg-white/5"
                    >
                      <option value="">Select target</option>
                      {targets.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">
                      Metric
                      {metricsLoading && <span className="ml-2 text-neon-blue text-[10px] animate-pulse">LOADING...</span>}
                    </label>
                    <select
                      value={formSourceMetric}
                      onChange={e => setFormSourceMetric(e.target.value)}
                      className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all appearance-none cursor-pointer disabled:opacity-50 hover:bg-white/5"
                      disabled={!formTargetId || metricsLoading}
                    >
                      <option value="">Select metric</option>
                      {metrics.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Aggregation</label>
                    <div className="relative">
                      <select
                        value={formAggregation}
                        onChange={e => setFormAggregation(e.target.value)}
                        className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all appearance-none cursor-pointer hover:bg-white/5"
                      >
                        <option value="avg">Average (avg)</option>
                        <option value="sum">Sum (sum)</option>
                        <option value="max">Maximum (max)</option>
                        <option value="min">Minimum (min)</option>
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Interval (s)</label>
                    <input
                      type="number"
                      value={formInterval}
                      onChange={e => setFormInterval(Number(e.target.value))}
                      min={10}
                      className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all shadow-inner"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Group By Labels</label>
                  <input
                    type="text"
                    value={formGroupBy}
                    onChange={e => setFormGroupBy(e.target.value)}
                    placeholder="topic, partition"
                    className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all placeholder-gray-600 font-mono text-sm shadow-inner"
                  />
                  <p className="text-xs text-gray-500 mt-2 ml-1 flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-gray-500"></span>
                    Comma-separated keys (e.g. topic, partition)
                  </p>
                </div>
                
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Filter Labels (JSON)</label>
                  <input
                    type="text"
                    value={formLabelsFilter}
                    onChange={e => setFormLabelsFilter(e.target.value)}
                    placeholder='{"env": "prod"}'
                    className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all placeholder-gray-600 font-mono text-sm shadow-inner"
                  />
                </div>
                
                <div>
                  <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 ml-1">Description</label>
                  <textarea
                    value={formDescription}
                    onChange={e => setFormDescription(e.target.value)}
                    placeholder="Explain the purpose of this rule..."
                    rows={3}
                    className="w-full px-4 py-3 bg-black/30 border border-white/10 rounded-xl text-white focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue/50 transition-all placeholder-gray-600 resize-none shadow-inner"
                  />
                </div>
              </div>
              
              <div className="p-6 border-t border-white/10 flex justify-end gap-4 bg-black/20 backdrop-blur-sm">
                <button
                  onClick={() => setShowModal(false)}
                  className="px-6 py-3 text-sm font-bold text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={!formName || !formTargetId || !formSourceMetric}
                  className="flex items-center gap-2 px-8 py-3 bg-neon-blue text-black font-bold rounded-xl hover:bg-neon-blue/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-[0_0_20px_rgba(0,243,255,0.3)] hover:shadow-[0_0_30px_rgba(0,243,255,0.5)] transform hover:-translate-y-0.5"
                >
                  <Check className="w-4 h-4" />
                  {editingRule ? 'Save Changes' : 'Create Rule'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
