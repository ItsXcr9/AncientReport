/**
 * MetricTargetsPanel - Manage Prometheus-compatible scrape targets
 * Replaces the need for prometheus.yml configuration
 */

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { 
  Plus, Trash2, Edit2, RefreshCw, Check, X, 
  Activity, AlertCircle, Clock, Link2, Play,
  Server, Gauge, Radar, ExternalLink, Zap
} from 'lucide-react';


interface Target {
  id: string;
  name: string;
  url: string;
  scrape_interval: number;
  timeout: number;
  labels: Record<string, string>;
  enabled: boolean;
  last_scrape: string;
  last_status: string;
  last_error: string;
  metrics_count: number;
  created_at: string;
}

interface TestResult {
  status: 'success' | 'error';
  latency_ms?: number;
  metrics_count?: number;
  error?: string;
}

interface DiscoveredExporter {
  hostname: string;
  exporter_type: string;
  scrape_target: string;
  metric_count: number;
  last_seen: string;
  first_seen: string;
  status: 'up' | 'down';
}

export function MetricTargetsPanel() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [discoveredExporters, setDiscoveredExporters] = useState<DiscoveredExporter[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingTarget, setEditingTarget] = useState<Target | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set());

  // Form state
  const [formName, setFormName] = useState('');
  const [formUrl, setFormUrl] = useState('');
  const [formInterval, setFormInterval] = useState(15);
  const [formTimeout, setFormTimeout] = useState(10);
  const [formEnabled, setFormEnabled] = useState(true);

  useEffect(() => {
    fetchTargets();
    fetchDiscoveredExporters();
    const interval = setInterval(() => {
      fetchTargets();
      fetchDiscoveredExporters();
    }, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const fetchTargets = async () => {
    try {
      const response = await fetch('/api/prometheus/targets');
      if (response.ok) {
        const data = await response.json();
        setTargets(data);
      }
    } catch (error) {
      console.error('Failed to fetch targets:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDiscoveredExporters = async () => {
    try {
      const response = await fetch('/api/prometheus/discovered/exporters');
      console.log('[DEBUG] fetchDiscoveredExporters response status:', response.status);
      if (response.ok) {
        const data = await response.json();
        console.log('[DEBUG] fetchDiscoveredExporters data:', data);
        console.log('[DEBUG] exporters array:', data.exporters);
        setDiscoveredExporters(data.exporters || []);
      }
    } catch (error) {
      console.error('Failed to fetch discovered exporters:', error);
    }
  };

  const handleAddTarget = async () => {
    try {
      const response = await fetch('/api/prometheus/targets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formName,
          url: formUrl,
          scrape_interval: formInterval,
          timeout: formTimeout,
          enabled: formEnabled,
          labels: {}
        })
      });
      
      if (response.ok) {
        await fetchTargets();
        resetForm();
        setShowAddModal(false);
      }
    } catch (error) {
      console.error('Failed to add target:', error);
    }
  };

  const handleUpdateTarget = async () => {
    if (!editingTarget) return;

    try {
      const response = await fetch(`/api/prometheus/targets/${editingTarget.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formName,
          url: formUrl,
          scrape_interval: formInterval,
          timeout: formTimeout,
          enabled: formEnabled
        })
      });
      
      if (response.ok) {
        await fetchTargets();
        resetForm();
        setEditingTarget(null);
      }
    } catch (error) {
      console.error('Failed to update target:', error);
    }
  };

  const handleDeleteTarget = async (id: string) => {
    if (!confirm('Delete this scrape target? All associated metrics will also be deleted.')) return;

    try {
      const response = await fetch(`/api/prometheus/targets/${id}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        await fetchTargets();
      }
    } catch (error) {
      console.error('Failed to delete target:', error);
    }
  };

  const handleTestTarget = async (id: string) => {
    setTestingIds(prev => new Set(prev).add(id));
    
    try {
      const response = await fetch(`/api/prometheus/targets/${id}/test`, {
        method: 'POST'
      });
      
      if (response.ok) {
        const result = await response.json();
        setTestResults(prev => ({ ...prev, [id]: result }));
      }
    } catch (error) {
      setTestResults(prev => ({ 
        ...prev, 
        [id]: { status: 'error', error: 'Request failed' }
      }));
    } finally {
      setTestingIds(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const resetForm = () => {
    setFormName('');
    setFormUrl('');
    setFormInterval(15);
    setFormTimeout(10);
    setFormEnabled(true);
  };

  const openEditModal = (target: Target) => {
    setEditingTarget(target);
    setFormName(target.name);
    setFormUrl(target.url);
    setFormInterval(target.scrape_interval);
    setFormTimeout(target.timeout);
    setFormEnabled(target.enabled);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success': return 'text-green-400';
      case 'error': return 'text-red-400';
      case 'pending': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'success': return 'bg-green-500/10 border-green-500/30';
      case 'error': return 'bg-red-500/10 border-red-500/30';
      case 'pending': return 'bg-yellow-500/10 border-yellow-500/30';
      default: return 'bg-gray-500/10 border-gray-500/30';
    }
  };

  const formatLastScrape = (timestamp: string) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now.getTime() - date.getTime()) / 1000;
    
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="glass-card rounded-xl p-6">
        <div className="flex items-center gap-3 mb-6">
          <Server className="w-6 h-6 text-neon-blue" />
          <h2 className="text-lg font-semibold">Scrape Targets</h2>
        </div>
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Server className="w-6 h-6 text-neon-blue" />
          <h2 className="text-lg font-semibold">Scrape Targets</h2>
          <span className="text-xs text-gray-400 bg-white/5 px-2 py-1 rounded-full">
            {targets.length} {targets.length === 1 ? 'target' : 'targets'}
          </span>
        </div>
        
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-neon-blue/20 hover:bg-neon-blue/30 text-neon-blue rounded-lg transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          Add Target
        </button>
      </div>

      {/* Targets List */}
      {targets.length === 0 ? (
        <div className="text-center py-12">
          <Gauge className="w-12 h-12 text-gray-500 mx-auto mb-4" />
          <p className="text-gray-400 mb-2">No scrape targets configured</p>
          <p className="text-gray-500 text-sm mb-4">
            Add a target to start collecting metrics from your services
          </p>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-neon-blue/20 hover:bg-neon-blue/30 text-neon-blue rounded-lg transition-colors text-sm"
          >
            Add Your First Target
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {targets.map((target) => (
            <motion.div
              key={target.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`p-4 rounded-lg border ${getStatusBg(target.last_status)} transition-colors`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <div className={`w-2 h-2 rounded-full ${
                      target.last_status === 'success' ? 'bg-green-400 shadow-lg shadow-green-500/50' :
                      target.last_status === 'error' ? 'bg-red-400' : 'bg-yellow-400'
                    }`} />
                    <h3 className="font-medium text-white">{target.name}</h3>
                    {!target.enabled && (
                      <span className="text-xs bg-gray-600/50 text-gray-400 px-2 py-0.5 rounded">
                        Disabled
                      </span>
                    )}
                  </div>
                  
                  <div className="flex flex-wrap items-center gap-4 text-sm text-gray-400">
                    <div className="flex items-center gap-1">
                      <Link2 className="w-3 h-3" />
                      <span className="font-mono text-xs">{target.url}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      <span>Every {target.scrape_interval}s</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Activity className="w-3 h-3" />
                      <span>{target.metrics_count} metrics</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span>Last: {formatLastScrape(target.last_scrape)}</span>
                    </div>
                  </div>

                  {target.last_error && (
                    <div className="mt-2 text-xs text-red-400 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" />
                      {target.last_error}
                    </div>
                  )}

                  {/* Test Result */}
                  {testResults[target.id] && (
                    <div className={`mt-2 text-xs flex items-center gap-2 ${
                      testResults[target.id].status === 'success' ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {testResults[target.id].status === 'success' ? (
                        <>
                          <Check className="w-3 h-3" />
                          Connected in {testResults[target.id].latency_ms}ms - {testResults[target.id].metrics_count} metrics found
                        </>
                      ) : (
                        <>
                          <X className="w-3 h-3" />
                          {testResults[target.id].error}
                        </>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 ml-4">
                  <button
                    onClick={() => handleTestTarget(target.id)}
                    disabled={testingIds.has(target.id)}
                    className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-green-400"
                    title="Test Connection"
                  >
                    {testingIds.has(target.id) ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => openEditModal(target)}
                    className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-blue-400"
                    title="Edit"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteTarget(target.id)}
                    className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Agent-Discovered Exporters Section */}
      {discoveredExporters.length > 0 && (
        <div className="mt-8 pt-6 border-t border-white/10">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Radar className="w-5 h-5 text-green-400" />
              <h3 className="text-md font-semibold text-green-400">Auto-Discovered Exporters</h3>
              <span className="text-xs text-gray-400 bg-green-500/10 px-2 py-1 rounded-full border border-green-500/30">
                {discoveredExporters.length} found
              </span>
            </div>
            <Link 
              to="/prometheus-discovery"
              className="flex items-center gap-2 px-3 py-1.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 rounded-lg transition-colors text-sm"
            >
              <ExternalLink className="w-4 h-4" />
              View Details
            </Link>
          </div>
          
          <p className="text-xs text-gray-500 mb-4">
            These exporters were automatically discovered by agents running on your servers.
          </p>

          <div className="space-y-2">
            {discoveredExporters.map((exporter, idx) => (
              <div
                key={`${exporter.hostname}-${exporter.scrape_target}-${idx}`}
                className={`p-3 rounded-lg border transition-colors ${
                  exporter.status === 'up' 
                    ? 'bg-green-500/5 border-green-500/20' 
                    : 'bg-red-500/5 border-red-500/20'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${
                      exporter.status === 'up' 
                        ? 'bg-green-400 shadow-lg shadow-green-500/50' 
                        : 'bg-red-400'
                    }`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white text-sm">{exporter.hostname}</span>
                        {exporter.exporter_type && (
                          <span className="text-xs bg-white/5 text-gray-400 px-2 py-0.5 rounded">
                            {exporter.exporter_type}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-400 mt-1">
                        <span className="font-mono">{exporter.scrape_target}</span>
                        <span className="flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          {exporter.metric_count} metrics
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500">
                    Last seen: {formatLastScrape(exporter.last_seen)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add/Edit Modal - Rendered via Portal to avoid clipping */}
      {createPortal(
        <AnimatePresence>
        {(showAddModal || editingTarget) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => { setShowAddModal(false); setEditingTarget(null); resetForm(); }}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-deep border border-white/10 rounded-xl p-6 w-full max-w-md shadow-2xl"
            >
              <h3 className="text-lg font-semibold mb-4">
                {editingTarget ? 'Edit Scrape Target' : 'Add Scrape Target'}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Name</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g., Production Node Exporter"
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue"
                  />
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">URL</label>
                  <input
                    type="text"
                    value={formUrl}
                    onChange={(e) => setFormUrl(e.target.value)}
                    placeholder="http://localhost:9100/metrics"
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white font-mono text-sm placeholder-gray-500 focus:outline-none focus:border-neon-blue"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Prometheus exposition format endpoint
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Scrape Interval (s)</label>
                    <input
                      type="number"
                      value={formInterval}
                      onChange={(e) => setFormInterval(Number(e.target.value))}
                      min={5}
                      max={300}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-neon-blue"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Timeout (s)</label>
                    <input
                      type="number"
                      value={formTimeout}
                      onChange={(e) => setFormTimeout(Number(e.target.value))}
                      min={1}
                      max={60}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-neon-blue"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setFormEnabled(!formEnabled)}
                    className={`w-10 h-6 rounded-full transition-colors ${
                      formEnabled ? 'bg-neon-blue' : 'bg-gray-600'
                    }`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full transition-transform ${
                      formEnabled ? 'translate-x-5' : 'translate-x-1'
                    }`} />
                  </button>
                  <span className="text-sm text-gray-300">Enabled</span>
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => { setShowAddModal(false); setEditingTarget(null); resetForm(); }}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-lg transition-colors text-gray-300"
                >
                  Cancel
                </button>
                <button
                  onClick={editingTarget ? handleUpdateTarget : handleAddTarget}
                  disabled={!formName || !formUrl}
                  className="px-4 py-2 bg-neon-blue/20 hover:bg-neon-blue/30 text-neon-blue rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {editingTarget ? 'Save Changes' : 'Add Target'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
        </AnimatePresence>,
        document.body
      )}
    </div>
  );
}

export default MetricTargetsPanel;
