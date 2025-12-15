import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ArrowLeft, 
  Plus, 
  Trash2, 
  BarChart2,
  Activity,
  Clock,
  X,
  Edit2
} from 'lucide-react';
import ScrapedMetricChart from '../components/ScrapedMetricChart';

interface Panel {
  id: string;
  title: string;
  target_id: string;
  metric_name: string;
  chart_type: string;
  color: string;
  time_range: string;
}

interface Target {
  id: string;
  name: string;
}

interface DashboardData {
  id: string;
  name: string;
  description: string;
  panels: Panel[];
}

export default function DashboardView() {
  const { id } = useParams<{ id: string }>();
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddPanel, setShowAddPanel] = useState(false);
  
  // New panel form
  const [newTitle, setNewTitle] = useState('');
  const [newTargetId, setNewTargetId] = useState('');
  const [newMetric, setNewMetric] = useState('');
  const [newTimeRange, setNewTimeRange] = useState('1h');

  useEffect(() => {
    fetchDashboard();
    fetchTargets();
  }, [id]);

  useEffect(() => {
    if (newTargetId) {
      fetchMetrics(newTargetId);
    }
  }, [newTargetId]);

  const fetchDashboard = async () => {
    try {
      const res = await fetch(`/api/dashboards/${id}`);
      if (res.ok) {
        const data = await res.json();
        setDashboard(data);
      }
    } catch (e) {
      console.error('Failed to fetch dashboard:', e);
    } finally {
      setLoading(false);
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
        // Extract just the name strings from metric objects
        const metricNames = (data.metrics || []).map((m: any) => typeof m === 'string' ? m : m.name);
        setMetrics(metricNames);
      }
    } catch (e) {
      console.error('Failed to fetch metrics:', e);
    }
  };

  const handleAddPanel = async () => {
    if (!newTitle.trim() || !newTargetId || !newMetric) return;
    
    try {
      const res = await fetch(`/api/dashboards/${id}/panels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle,
          target_id: newTargetId,
          metric_name: newMetric,
          time_range: newTimeRange
        })
      });
      
      if (res.ok) {
        await fetchDashboard();
        setShowAddPanel(false);
        setNewTitle('');
        setNewTargetId('');
        setNewMetric('');
      }
    } catch (e) {
      console.error('Failed to add panel:', e);
    }
  };

  const handleDeletePanel = async (panelId: string) => {
    if (!confirm('Delete this panel?')) return;
    
    try {
      await fetch(`/api/dashboards/${id}/panels/${panelId}`, { method: 'DELETE' });
      await fetchDashboard();
    } catch (e) {
      console.error('Failed to delete panel:', e);
    }
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[60vh]">
        <div className="relative">
          <div className="w-12 h-12 rounded-full border-2 border-neon-blue/20 border-t-neon-blue animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-2 h-2 bg-neon-blue rounded-full animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="p-6">
        <div className="glass-card rounded-xl p-12 text-center border border-white/10">
          <h2 className="text-xl font-bold text-white mb-2">Dashboard Not Found</h2>
          <Link to="/dashboards" className="text-neon-blue hover:text-neon-blue/80 transition-colors inline-flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" /> Back to Dashboards
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8 pb-20">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link 
            to="/dashboards" 
            className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 hover:border-white/20 transition-all group"
          >
            <ArrowLeft size={20} className="group-hover:-translate-x-1 transition-transform" />
          </Link>
          <div>
            <h1 className="text-3xl font-display font-bold text-white tracking-tight">{dashboard.name}</h1>
            {dashboard.description && (
              <p className="text-gray-400 text-sm mt-1 flex items-center gap-2">
                <span className="w-1 h-1 rounded-full bg-neon-blue"></span>
                {dashboard.description}
              </p>
            )}
          </div>
        </div>
        <button
          onClick={() => setShowAddPanel(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-neon-blue text-black font-bold rounded-xl hover:bg-neon-blue/90 transition-all shadow-lg shadow-neon-blue/20 hover:shadow-neon-blue/30 transform hover:-translate-y-0.5"
        >
          <Plus size={18} />
          Add Panel
        </button>
      </div>

      {/* Panels Grid */}
      {(!dashboard.panels || dashboard.panels.length === 0) ? (
        <div className="glass-card rounded-2xl p-16 text-center border-dashed border-2 border-white/10 bg-black/20">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-white/5 flex items-center justify-center">
            <BarChart2 className="text-gray-600" size={40} />
          </div>
          <h3 className="text-2xl font-bold text-white mb-2 font-display">No Panels Yet</h3>
          <p className="text-gray-400 mb-8 max-w-sm mx-auto">Build your custom view by adding charts connected to your metrics.</p>
          <button
            onClick={() => setShowAddPanel(true)}
            className="inline-flex items-center gap-2 px-6 py-3 bg-white/10 border border-white/20 text-white font-medium rounded-xl hover:bg-white/20 hover:border-white/30 transition-all"
          >
            <Plus size={18} />
            Create First Panel
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {dashboard.panels.map((panel, idx) => (
            <motion.div
              key={panel.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="glass-card rounded-2xl p-5 relative group border border-white/10 hover:border-white/20 transition-colors"
            >
              <div className="flex items-center justify-between mb-4 pb-4 border-b border-white/5">
                <h3 className="font-semibold text-white flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-neon-blue/10 flex items-center justify-center flex-shrink-0">
                    <Activity size={16} className="text-neon-blue" />
                  </div>
                  <span className="truncate">{panel.title}</span>
                </h3>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-xs font-mono text-gray-500 flex items-center gap-1.5 bg-black/20 px-2 py-1 rounded-md border border-white/5">
                    <Clock size={12} />
                    {panel.time_range}
                  </span>
                  <button
                    onClick={() => handleDeletePanel(panel.id)}
                    className="p-2 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                    title="Remove Panel"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              <div className="h-[280px] min-h-[280px] chart-container">
                <ScrapedMetricChart
                  targetId={panel.target_id}
                  metricName={panel.metric_name}
                  height={270}
                />
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Add Panel Modal */}
      <AnimatePresence>
        {showAddPanel && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={() => setShowAddPanel(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 20 }}
              className="glass-card-intense rounded-2xl w-full max-w-lg border border-white/10 shadow-2xl overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-white/10 bg-[#161b22]/95 backdrop-blur-md flex items-center justify-between">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-neon-blue/10 flex items-center justify-center">
                    <Plus className="w-4 h-4 text-neon-blue" />
                  </div>
                  Add Panel
                </h2>
              </div>
              
              <div className="p-6 space-y-5">
                <div>
                  <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Panel Title</label>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    placeholder="e.g., Kafka Consumer Lag"
                    className="w-full px-4 py-3 bg-black/20 border border-white/10 rounded-xl text-white placeholder-gray-600 focus:border-neon-blue focus:outline-none focus:ring-1 focus:ring-neon-blue/50 transition-all"
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-5">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Data Source</label>
                    <select
                      value={newTargetId}
                      onChange={(e) => setNewTargetId(e.target.value)}
                      className="w-full px-4 py-3 bg-black/20 border border-white/10 rounded-xl text-white focus:border-neon-blue focus:outline-none focus:ring-1 focus:ring-neon-blue/50 transition-all appearance-none cursor-pointer"
                    >
                      <option value="">Select target...</option>
                      {targets.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Metric</label>
                    <select
                      value={newMetric}
                      onChange={(e) => setNewMetric(e.target.value)}
                      disabled={!newTargetId}
                      className="w-full px-4 py-3 bg-black/20 border border-white/10 rounded-xl text-white focus:border-neon-blue focus:outline-none focus:ring-1 focus:ring-neon-blue/50 transition-all appearance-none cursor-pointer disabled:opacity-50"
                    >
                      <option value="">Select metric...</option>
                      {metrics.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                <div>
                  <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Default Time Range</label>
                  <div className="grid grid-cols-4 gap-2">
                    {['1h', '6h', '24h', '7d'].map((range) => (
                      <button
                        key={range}
                        onClick={() => setNewTimeRange(range)}
                        className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                          newTimeRange === range 
                            ? 'bg-neon-blue text-black shadow-lg shadow-neon-blue/20' 
                            : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
                        }`}
                      >
                        {range}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              
              <div className="p-6 border-t border-white/10 flex justify-end gap-3 bg-black/20">
                <button
                  onClick={() => setShowAddPanel(false)}
                  className="px-5 py-2.5 text-sm font-medium text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddPanel}
                  disabled={!newTitle.trim() || !newTargetId || !newMetric}
                  className="flex items-center gap-2 px-6 py-2.5 bg-neon-blue text-black font-bold rounded-xl hover:bg-neon-blue/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-neon-blue/20"
                >
                  <Plus size={16} />
                  Add Panel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
