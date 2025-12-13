import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ArrowLeft, 
  Plus, 
  Trash2, 
  BarChart2,
  Activity,
  Clock
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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-neon-blue" />
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="p-6">
        <div className="glass-card rounded-xl p-12 text-center">
          <h2 className="text-xl font-bold text-white mb-2">Dashboard Not Found</h2>
          <Link to="/dashboards" className="text-neon-blue hover:underline">
            Back to Dashboards
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link 
            to="/dashboards" 
            className="p-2 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
          >
            <ArrowLeft size={20} />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white">{dashboard.name}</h1>
            {dashboard.description && (
              <p className="text-gray-400 text-sm mt-1">{dashboard.description}</p>
            )}
          </div>
        </div>
        <button
          onClick={() => setShowAddPanel(true)}
          className="flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
        >
          <Plus size={18} />
          Add Panel
        </button>
      </div>

      {/* Panels Grid */}
      {(!dashboard.panels || dashboard.panels.length === 0) ? (
        <div className="glass-card rounded-xl p-12 text-center">
          <BarChart2 className="mx-auto mb-4 text-gray-500" size={48} />
          <h3 className="text-xl font-semibold text-white mb-2">No Panels Yet</h3>
          <p className="text-gray-400 mb-6">Add your first chart panel to start monitoring</p>
          <button
            onClick={() => setShowAddPanel(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
          >
            <Plus size={18} />
            Add Panel
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {dashboard.panels.map((panel) => (
            <motion.div
              key={panel.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-xl p-4 relative group"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-white flex items-center gap-2">
                  <Activity size={16} className="text-neon-blue" />
                  {panel.title}
                </h3>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 flex items-center gap-1">
                    <Clock size={12} />
                    {panel.time_range}
                  </span>
                  <button
                    onClick={() => handleDeletePanel(panel.id)}
                    className="p-1.5 text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <div className="h-48">
                <ScrapedMetricChart
                  targetId={panel.target_id}
                  metricName={panel.metric_name}
                  height={180}
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
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => setShowAddPanel(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card rounded-xl p-6 w-full max-w-md mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-bold text-white mb-4">Add Panel</h2>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Title</label>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    placeholder="e.g., Kafka Consumer Lag"
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Target</label>
                  <select
                    value={newTargetId}
                    onChange={(e) => setNewTargetId(e.target.value)}
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
                    value={newMetric}
                    onChange={(e) => setNewMetric(e.target.value)}
                    disabled={!newTargetId}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none disabled:opacity-50"
                  >
                    <option value="">Select metric...</option>
                    {metrics.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Time Range</label>
                  <select
                    value={newTimeRange}
                    onChange={(e) => setNewTimeRange(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                  >
                    <option value="1h">Last 1 hour</option>
                    <option value="6h">Last 6 hours</option>
                    <option value="24h">Last 24 hours</option>
                    <option value="7d">Last 7 days</option>
                  </select>
                </div>
              </div>
              
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowAddPanel(false)}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddPanel}
                  disabled={!newTitle.trim() || !newTargetId || !newMetric}
                  className="px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
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
