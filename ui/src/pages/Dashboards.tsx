import { useState, useEffect } from 'react';
import { motion , AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import { 
  LayoutGrid, 
  Plus, 
  Trash2, 
  Clock, 
  ChevronRight,
  BarChart2
} from 'lucide-react';

interface Dashboard {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  panel_count: number;
}

export default function Dashboards() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchDashboards();
  }, []);

  const fetchDashboards = async () => {
    try {
      const res = await fetch('/api/dashboards');
      if (res.ok) {
        const data = await res.json();
        setDashboards(data);
      }
    } catch (e) {
      console.error('Failed to fetch dashboards:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch('/api/dashboards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, description: newDescription })
      });
      if (res.ok) {
        await fetchDashboards();
        setShowCreateModal(false);
        setNewName('');
        setNewDescription('');
      }
    } catch (e) {
      console.error('Failed to create dashboard:', e);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this dashboard?')) return;
    try {
      await fetch(`/api/dashboards/${id}`, { method: 'DELETE' });
      await fetchDashboards();
    } catch (e) {
      console.error('Failed to delete dashboard:', e);
    }
  };

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <LayoutGrid className="text-neon-blue" size={28} />
            Custom Dashboards
          </h1>
          <p className="text-gray-400 mt-1">Create and manage persistent metric dashboards</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
        >
          <Plus size={18} />
          New Dashboard
        </button>
      </div>

      {/* Dashboard Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-neon-blue" />
        </div>
      ) : dashboards.length === 0 ? (
        <div className="glass-card rounded-xl p-12 text-center">
          <LayoutGrid className="mx-auto mb-4 text-gray-500" size={48} />
          <h3 className="text-xl font-semibold text-white mb-2">No Dashboards Yet</h3>
          <p className="text-gray-400 mb-6">Create your first custom dashboard to start monitoring metrics</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
          >
            <Plus size={18} />
            Create Dashboard
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {dashboards.map((dashboard) => (
            <motion.div
              key={dashboard.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-xl p-5 border border-white/5 hover:border-neon-blue/30 transition-all group"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-neon-blue/10 flex items-center justify-center">
                    <BarChart2 className="text-neon-blue" size={20} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-white">{dashboard.name}</h3>
                    <p className="text-xs text-gray-500">{dashboard.panel_count} panels</p>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(dashboard.id)}
                  className="p-2 text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              
              {dashboard.description && (
                <p className="text-sm text-gray-400 mb-4 line-clamp-2">{dashboard.description}</p>
              )}
              
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-white/5">
                <div className="flex items-center gap-1 text-xs text-gray-500">
                  <Clock size={12} />
                  {formatDate(dashboard.updated_at)}
                </div>
                <Link
                  to={`/dashboards/${dashboard.id}`}
                  className="flex items-center gap-1 text-sm text-neon-blue hover:underline"
                >
                  Open
                  <ChevronRight size={14} />
                </Link>
              </div>
            </motion.div>
          ))}
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
              <h2 className="text-xl font-bold text-white mb-4">Create Dashboard</h2>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Name</label>
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g., Kafka Monitoring"
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Description (optional)</label>
                  <textarea
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="Describe this dashboard..."
                    rows={3}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none resize-none"
                  />
                </div>
              </div>
              
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={!newName.trim() || creating}
                  className="px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {creating ? 'Creating...' : 'Create'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
