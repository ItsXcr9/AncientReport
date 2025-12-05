import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Wrench, Play, CheckCircle, XCircle, Clock, 
  AlertTriangle, Shield, ChevronRight, User, RefreshCw, X
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
  approved_by: string | null;
  completed_at: string | null;
  logs: string[];
}

interface SystemStatus {
  docker_available: boolean;
  real_execution_mode: boolean;
  docker_connected: boolean;
  total_jobs: number;
  pending_jobs: number;
}

const API_BASE = '';

interface RemediationCenterProps {
  selectedServer: string | null;
}

export const RemediationCenter = ({ selectedServer }: RemediationCenterProps) => {
  const [actions, setActions] = useState<RemediationAction[]>([]);
  const [jobs, setJobs] = useState<RemediationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAction, setSelectedAction] = useState<RemediationAction | null>(null);
  const [targetInput, setTargetInput] = useState('');
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      const [actionsRes, jobsRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/api/v3/remediation/actions`),
        fetch(`${API_BASE}/api/v3/remediation/jobs?limit=20`),
        fetch(`${API_BASE}/api/v3/remediation/status`)
      ]);

      if (actionsRes.ok) setActions(await actionsRes.json());
      if (jobsRes.ok) setJobs(await jobsRes.json());
      if (statusRes.ok) setSystemStatus(await statusRes.json());
    } catch (error) {
      console.error('Failed to fetch remediation data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

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

  const handleReject = async (jobId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v3/remediation/reject/${jobId}?user=admin&reason=Manual rejection`, {
        method: 'POST'
      });
      
      if (res.ok) {
        fetchData();
      }
    } catch (error) {
      console.error('Failed to reject job:', error);
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'high': return 'text-red-500 border-red-500/20 bg-red-500/10';
      case 'medium': return 'text-orange-500 border-orange-500/20 bg-orange-500/10';
      case 'low': return 'text-green-500 border-green-500/20 bg-green-500/10';
      default: return 'text-gray-500 border-gray-500/20 bg-gray-500/10';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'failed': return <XCircle className="w-4 h-4 text-red-500" />;
      case 'rejected': return <XCircle className="w-4 h-4 text-gray-500" />;
      case 'running': return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'pending_approval': return <AlertTriangle className="w-4 h-4 text-orange-500" />;
      default: return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'border-l-green-500';
      case 'failed': return 'border-l-red-500';
      case 'rejected': return 'border-l-gray-500';
      case 'running': return 'border-l-blue-500';
      case 'pending_approval': return 'border-l-orange-500';
      default: return 'border-l-gray-500';
    }
  };

  // Split jobs: first 2 are "recent", rest are in scrollable history
  const recentJobs = jobs.slice(0, 2);
  const historyJobs = jobs.slice(2);

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-xl flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-neon-blue animate-spin" />
      </div>
    );
  }

  return (
    <div className="glass-card p-6 rounded-xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-neon-blue/10 rounded-lg">
            <Wrench className="w-6 h-6 text-neon-blue" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Auto-Remediation</h2>
            <p className="text-sm text-gray-400">Automated System Recovery & Actions</p>
          </div>
        </div>
        
        {/* Status indicators */}
        <div className="flex items-center gap-4">
          {systemStatus && (
            <div className="flex items-center gap-3 text-xs">
              <div className={`flex items-center gap-1 px-2 py-1 rounded ${systemStatus.docker_connected ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${systemStatus.docker_connected ? 'bg-green-400' : 'bg-red-400'}`} />
                Docker
              </div>
              <div className={`px-2 py-1 rounded ${systemStatus.real_execution_mode ? 'bg-orange-500/10 text-orange-400' : 'bg-gray-500/10 text-gray-400'}`}>
                {systemStatus.real_execution_mode ? 'LIVE MODE' : 'SIMULATION'}
              </div>
              {systemStatus.pending_jobs > 0 && (
                <div className="px-2 py-1 rounded bg-orange-500/10 text-orange-400 animate-pulse">
                  {systemStatus.pending_jobs} Pending
                </div>
              )}
            </div>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <RefreshCw className={`w-4 h-4 text-gray-400 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
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

        {/* Action Trigger / Job Display */}
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
                  <span className={`ml-auto px-2 py-0.5 rounded text-xs border ${getRiskColor(selectedAction.risk_level)}`}>
                    {selectedAction.risk_level.toUpperCase()} RISK
                  </span>
                </h3>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={targetInput}
                    onChange={(e) => setTargetInput(e.target.value)}
                    placeholder={`Enter ${selectedAction.target} name or ID...`}
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

          {/* Recent Activity - Last 2 Jobs Featured */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">Recent Activity</h3>
            
            {recentJobs.length > 0 ? (
              <div className="space-y-3 mb-4">
                {recentJobs.map(job => (
                  <div 
                    key={job.id} 
                    className={`bg-white/5 border border-white/10 rounded-lg p-4 border-l-4 ${getStatusColor(job.status)}`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        {getStatusIcon(job.status)}
                        <div>
                          <div className="text-white font-medium text-sm">
                            {actions.find(a => a.id === job.action_id)?.name || job.action_id}
                          </div>
                          <div className="text-xs text-gray-500">
                            Target: <span className="text-gray-300 font-mono">{job.target}</span>
                          </div>
                        </div>
                      </div>
                      
                      {job.status === 'pending_approval' && (
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleApprove(job.id)}
                            className="px-3 py-1.5 bg-green-500/20 hover:bg-green-500/30 text-green-500 border border-green-500/30 rounded text-xs font-medium transition-colors"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => handleReject(job.id)}
                            className="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-500 border border-red-500/30 rounded text-xs font-medium transition-colors"
                          >
                            Reject
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Logs */}
                    <div className="bg-black/30 rounded p-2 space-y-1 max-h-32 overflow-y-auto">
                      {job.logs.map((log, i) => (
                        <div key={i} className="text-xs font-mono text-gray-400 flex items-start gap-2">
                          <ChevronRight className="w-3 h-3 mt-0.5 shrink-0 opacity-50" />
                          {log}
                        </div>
                      ))}
                    </div>
                    
                    <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
                      <span>{new Date(job.created_at).toLocaleString()}</span>
                      {job.approved_by && (
                        <span className="flex items-center gap-1">
                          <User className="w-3 h-3" />
                          {job.approved_by}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 bg-white/5 rounded-lg mb-4">
                No recent activity
              </div>
            )}

            {/* History - Scrollable */}
            {historyJobs.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">History</h4>
                <div className="bg-black/20 rounded-lg border border-white/5 max-h-64 overflow-y-auto">
                  {historyJobs.map((job, idx) => (
                    <div 
                      key={job.id}
                      className={`p-3 flex items-center justify-between ${idx !== historyJobs.length - 1 ? 'border-b border-white/5' : ''} hover:bg-white/5 transition-colors`}
                    >
                      <div className="flex items-center gap-3">
                        {getStatusIcon(job.status)}
                        <div>
                          <div className="text-sm text-gray-300">
                            {actions.find(a => a.id === job.action_id)?.name || job.action_id}
                          </div>
                          <div className="text-xs text-gray-500">
                            {job.target} • {new Date(job.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                      <div className="text-xs text-gray-500">
                        {job.status === 'pending_approval' ? (
                          <button
                            onClick={() => handleApprove(job.id)}
                            className="text-orange-400 hover:text-orange-300"
                          >
                            Approve
                          </button>
                        ) : (
                          <span className={job.status === 'completed' ? 'text-green-400' : job.status === 'failed' ? 'text-red-400' : ''}>
                            {job.status}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
