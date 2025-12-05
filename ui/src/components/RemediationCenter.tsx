import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Wrench, Play, CheckCircle, XCircle, Clock, 
  AlertTriangle, Shield, ChevronRight, User 
} from 'lucide-react';

interface RemediationAction {
  id: string;
  name: string;
  description: string;
  target: string;
  action_type: string;
  risk_level: string;
  requires_approval: boolean;
}

interface RemediationJob {
  id: string;
  action_id: string;
  target: string;
  status: string;
  created_at: string;
  approved_by: string;
  completed_at: string;
  logs: string[];
}

const API_BASE = '';

export const RemediationCenter = () => {
  const [actions, setActions] = useState<RemediationAction[]>([]);
  const [jobs, setJobs] = useState<RemediationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAction, setSelectedAction] = useState<RemediationAction | null>(null);
  const [targetInput, setTargetInput] = useState('');

  const fetchData = async () => {
    try {
      const [actionsRes, jobsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v3/remediation/actions`),
        fetch(`${API_BASE}/api/v3/remediation/jobs`)
      ]);

      if (actionsRes.ok) setActions(await actionsRes.json());
      if (jobsRes.ok) setJobs(await jobsRes.json());
    } catch (error) {
      console.error('Failed to fetch remediation data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleTrigger = async () => {
    if (!selectedAction || !targetInput) return;

    try {
      const res = await fetch(`${API_BASE}/api/v3/remediation/trigger?action_id=${selectedAction.id}&target=${targetInput}`, {
        method: 'POST'
      });
      
      if (res.ok) {
        setSelectedAction(null);
        setTargetInput('');
        fetchData();
      }
    } catch (error) {
      console.error('Failed to trigger action:', error);
    }
  };

  const handleApprove = async (jobId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v3/remediation/approve/${jobId}?user=admin`, {
        method: 'POST'
      });
      
      if (res.ok) {
        fetchData();
      }
    } catch (error) {
      console.error('Failed to approve job:', error);
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'high': return 'text-red-500 border-red-500/20 bg-red-500/10';
      case 'medium': return 'text-orange-500 border-orange-500/20 bg-orange-500/10';
      case 'low': return 'text-blue-500 border-blue-500/20 bg-blue-500/10';
      default: return 'text-gray-500 border-gray-500/20 bg-gray-500/10';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'failed': return <XCircle className="w-4 h-4 text-red-500" />;
      case 'running': return <Clock className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'pending_approval': return <AlertTriangle className="w-4 h-4 text-orange-500" />;
      default: return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  if (loading) return null;

  return (
    <div className="glass-card p-6 rounded-xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-neon-blue/10 rounded-lg">
          <Wrench className="w-6 h-6 text-neon-blue" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">Auto-Remediation</h2>
          <p className="text-sm text-gray-400">Automated System Recovery & Actions</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Available Actions */}
        <div className="lg:col-span-1 space-y-4">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Available Actions</h3>
          <div className="space-y-3">
            {actions.map(action => (
              <div 
                key={action.id}
                onClick={() => setSelectedAction(action)}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  selectedAction?.id === action.id 
                    ? 'bg-neon-blue/10 border-neon-blue' 
                    : 'bg-white/5 border-white/10 hover:bg-white/10'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <span className="font-medium text-white">{action.name}</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getRiskColor(action.risk_level)}`}>
                    {action.risk_level.toUpperCase()}
                  </span>
                </div>
                <p className="text-xs text-gray-400 mb-3">{action.description}</p>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Shield className="w-3 h-3" />
                  {action.requires_approval ? 'Requires Approval' : 'Auto-Execute'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Action Trigger / Job History */}
        <div className="lg:col-span-2 space-y-6">
          {/* Trigger Panel */}
          <AnimatePresence>
            {selectedAction && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="bg-white/5 border border-white/10 rounded-lg p-4"
              >
                <h3 className="text-white font-medium mb-4 flex items-center gap-2">
                  <Play className="w-4 h-4 text-neon-blue" />
                  Execute: {selectedAction.name}
                </h3>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={targetInput}
                    onChange={(e) => setTargetInput(e.target.value)}
                    placeholder={`Enter target ${selectedAction.target} ID...`}
                    className="flex-1 bg-black/20 border border-white/10 rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:border-neon-blue/50"
                  />
                  <button
                    onClick={handleTrigger}
                    disabled={!targetInput}
                    className="px-6 py-2 bg-neon-blue hover:bg-neon-blue/80 text-black font-medium rounded-lg transition-colors disabled:opacity-50"
                  >
                    Execute
                  </button>
                  <button
                    onClick={() => setSelectedAction(null)}
                    className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Recent Jobs */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">Recent Activity</h3>
            <div className="space-y-3">
              {jobs.map(job => (
                <div key={job.id} className="bg-white/5 border border-white/10 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      {getStatusIcon(job.status)}
                      <div>
                        <div className="text-white font-medium text-sm">
                          {actions.find(a => a.id === job.action_id)?.name || job.action_id}
                        </div>
                        <div className="text-xs text-gray-500">
                          Target: {job.target} • {new Date(job.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    
                    {job.status === 'pending_approval' && (
                      <button
                        onClick={() => handleApprove(job.id)}
                        className="px-3 py-1.5 bg-orange-500/20 hover:bg-orange-500/30 text-orange-500 border border-orange-500/30 rounded text-xs font-medium transition-colors"
                      >
                        Approve Action
                      </button>
                    )}
                  </div>

                  {/* Logs */}
                  <div className="bg-black/30 rounded p-2 space-y-1">
                    {job.logs.map((log, i) => (
                      <div key={i} className="text-xs font-mono text-gray-400 flex items-start gap-2">
                        <ChevronRight className="w-3 h-3 mt-0.5 shrink-0 opacity-50" />
                        {log}
                      </div>
                    ))}
                  </div>
                  
                  {job.approved_by && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-gray-500">
                      <User className="w-3 h-3" />
                      Approved by {job.approved_by}
                    </div>
                  )}
                </div>
              ))}
              {jobs.length === 0 && (
                <div className="text-center py-8 text-gray-500">
                  No remediation history
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
