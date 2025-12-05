import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Shield, AlertTriangle, FileText, Activity, 
  Search, RefreshCw, Clock, Calendar
} from 'lucide-react';

interface Vulnerability {
  id: string;
  cve_id: string;
  severity: string;
  package: string;
  version: string;
  fixed_version: string;
  description: string;
  link: string;
}

interface SecurityScanResult {
  id: string;
  target: string;
  scan_type: string;
  status: string;
  started_at: string;
  completed_at: string;
  vulnerabilities: Vulnerability[];
  score: number;
}

interface FileIntegrityEvent {
  id: string;
  path: string;
  event_type: string;
  severity: string;
  timestamp: string;
  user: string;
  process: string;
  diff: string;
}

interface RuntimeSecurityEvent {
  id: string;
  rule_name: string;
  severity: string;
  container_id: string;
  process_name: string;
  pid: number;
  timestamp: string;
  details: string;
}

interface ScheduleInfo {
  enabled: boolean;
  next_run: string | null;
  last_run: string | null;
  cron_expression: string;
}

interface SecurityStats {
  vulnerabilities_total: number;
  critical_vulns: number;
  high_vulns: number;
  scans_last_24h: number;
  runtime_incidents: number;
  fim_events: number;
  average_score: number;
  scheduled_scan_enabled: boolean;
  last_scheduled_scan: string | null;
}

const API_BASE = '';

export const SecurityDashboard = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'vulnerabilities' | 'fim' | 'runtime'>('overview');
  const [scans, setScans] = useState<SecurityScanResult[]>([]);
  const [fimEvents, setFimEvents] = useState<FileIntegrityEvent[]>([]);
  const [runtimeEvents, setRuntimeEvents] = useState<RuntimeSecurityEvent[]>([]);
  const [stats, setStats] = useState<SecurityStats | null>(null);
  const [schedule, setSchedule] = useState<ScheduleInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);

  const fetchData = async () => {
    try {
      const [scansRes, fimRes, runtimeRes, statsRes, scheduleRes] = await Promise.all([
        fetch(`${API_BASE}/api/v3/security/scanning/results`),
        fetch(`${API_BASE}/api/v3/security/scanning/file-integrity`),
        fetch(`${API_BASE}/api/v3/security/scanning/runtime`),
        fetch(`${API_BASE}/api/v3/security/scanning/stats`),
        fetch(`${API_BASE}/api/v3/security/scanning/schedule`)
      ]);

      if (scansRes.ok) setScans(await scansRes.json());
      if (fimRes.ok) setFimEvents(await fimRes.json());
      if (runtimeRes.ok) setRuntimeEvents(await runtimeRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
      if (scheduleRes.ok) setSchedule(await scheduleRes.json());
    } catch (error) {
      console.error('Failed to fetch security data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const triggerFullScan = async () => {
    setScanning(true);
    try {
      const res = await fetch(`${API_BASE}/api/v3/security/scanning/trigger-all`, {
        method: 'POST'
      });
      if (res.ok) {
        await fetchData();
      }
    } catch (error) {
      console.error('Failed to trigger scan:', error);
    } finally {
      setScanning(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'text-red-500 bg-red-500/10 border-red-500/20';
      case 'high': return 'text-orange-500 bg-orange-500/10 border-orange-500/20';
      case 'medium': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20';
      case 'low': return 'text-blue-500 bg-blue-500/10 border-blue-500/20';
      default: return 'text-gray-500 bg-gray-500/10 border-gray-500/20';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-500';
    if (score >= 60) return 'text-yellow-500';
    if (score >= 40) return 'text-orange-500';
    return 'text-red-500';
  };

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-xl flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-neon-blue animate-spin" />
      </div>
    );
  }

  return (
    <div className="glass-card p-6 rounded-xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-neon-purple/10 rounded-lg">
            <Shield className="w-6 h-6 text-neon-purple" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Security Center</h2>
            <p className="text-sm text-gray-400">Vulnerability Scanning & Runtime Protection</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {/* Schedule Info */}
          {schedule && schedule.enabled && (
            <div className="flex items-center gap-2 text-xs text-gray-400 bg-white/5 px-3 py-1.5 rounded-lg">
              <Calendar className="w-3 h-3" />
              <span>Daily scan at 2:00 AM</span>
              {schedule.next_run && (
                <span className="text-neon-purple">
                  Next: {new Date(schedule.next_run).toLocaleString()}
                </span>
              )}
            </div>
          )}
          
          {/* Scan Button */}
          <button
            onClick={triggerFullScan}
            disabled={scanning}
            className="flex items-center gap-2 px-4 py-2 bg-neon-purple/20 hover:bg-neon-purple/30 text-neon-purple rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
            {scanning ? 'Scanning...' : 'Scan Now'}
          </button>
          
          {/* Tab Buttons */}
          <div className="flex gap-2">
            {['overview', 'vulnerabilities', 'fim', 'runtime'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab as any)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === tab 
                    ? 'bg-neon-purple/20 text-neon-purple border border-neon-purple/30' 
                    : 'text-gray-400 hover:bg-white/5'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {activeTab === 'overview' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
              <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">Security Score</span>
                  <Shield className="w-4 h-4 text-neon-green" />
                </div>
                <div className={`text-2xl font-bold ${getScoreColor(stats?.average_score || 0)}`}>
                  {stats?.average_score || 0}/100
                </div>
                <div className="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-500 ${
                      (stats?.average_score || 0) >= 80 ? 'bg-green-500' :
                      (stats?.average_score || 0) >= 60 ? 'bg-yellow-500' :
                      (stats?.average_score || 0) >= 40 ? 'bg-orange-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${stats?.average_score || 0}%` }}
                  />
                </div>
              </div>

              <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">Critical Vulns</span>
                  <AlertTriangle className="w-4 h-4 text-red-500" />
                </div>
                <div className="text-2xl font-bold text-red-500">
                  {stats?.critical_vulns || 0}
                </div>
                <p className="text-xs text-gray-500 mt-1">Immediate action required</p>
              </div>

              <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">High Severity</span>
                  <AlertTriangle className="w-4 h-4 text-orange-500" />
                </div>
                <div className="text-2xl font-bold text-orange-500">
                  {stats?.high_vulns || 0}
                </div>
                <p className="text-xs text-gray-500 mt-1">Should be addressed soon</p>
              </div>

              <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">Runtime Incidents</span>
                  <Activity className="w-4 h-4 text-orange-500" />
                </div>
                <div className="text-2xl font-bold text-white">
                  {stats?.runtime_incidents || 0}
                </div>
                <p className="text-xs text-gray-500 mt-1">Last 24 hours</p>
              </div>

              <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">File Changes</span>
                  <FileText className="w-4 h-4 text-blue-500" />
                </div>
                <div className="text-2xl font-bold text-white">
                  {stats?.fim_events || 0}
                </div>
                <p className="text-xs text-gray-500 mt-1">Integrity alerts</p>
              </div>
            </div>

            {/* Recent Scans */}
            <div>
              <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">Recent Scans</h3>
              <div className="space-y-3">
                {scans.slice(0, 5).map(scan => (
                  <div key={scan.id} className="p-4 bg-white/5 rounded-lg border border-white/10 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                        scan.score >= 80 ? 'bg-green-500/20' : 
                        scan.score >= 60 ? 'bg-yellow-500/20' : 'bg-red-500/20'
                      }`}>
                        <span className={`text-lg font-bold ${getScoreColor(scan.score)}`}>{scan.score}</span>
                      </div>
                      <div>
                        <div className="text-white font-medium">{scan.target}</div>
                        <div className="text-xs text-gray-500">
                          {new Date(scan.completed_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="text-sm text-gray-300">{scan.vulnerabilities.length} vulnerabilities</div>
                        <div className="text-xs text-gray-500">
                          {scan.vulnerabilities.filter(v => v.severity === 'critical').length} critical
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {activeTab === 'vulnerabilities' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4 max-h-[500px] overflow-y-auto"
          >
            {scans.flatMap(scan => scan.vulnerabilities.map(vuln => ({ ...vuln, target: scan.target })))
              .sort((a, b) => {
                const order = { critical: 0, high: 1, medium: 2, low: 3 };
                return (order[a.severity as keyof typeof order] || 4) - (order[b.severity as keyof typeof order] || 4);
              })
              .map((vuln, idx) => (
              <div key={`${vuln.id}-${idx}`} className="p-4 bg-white/5 rounded-lg border border-white/10 hover:bg-white/10 transition-colors">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getSeverityColor(vuln.severity)}`}>
                        {vuln.severity.toUpperCase()}
                      </span>
                      <span className="text-neon-blue font-mono text-sm">{vuln.cve_id}</span>
                      <span className="text-gray-400 text-sm">• {vuln.package} {vuln.version}</span>
                    </div>
                    <p className="text-gray-300 text-sm mb-2">{vuln.description}</p>
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>Target: {vuln.target}</span>
                      {vuln.fixed_version && (
                        <span className="text-neon-green">Fixed in: {vuln.fixed_version}</span>
                      )}
                    </div>
                  </div>
                  <a 
                    href={vuln.link} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                  >
                    <Search className="w-4 h-4 text-gray-400" />
                  </a>
                </div>
              </div>
            ))}
            {scans.flatMap(s => s.vulnerabilities).length === 0 && (
              <div className="text-center py-12 text-gray-500">
                No vulnerabilities detected
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'fim' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4 max-h-[500px] overflow-y-auto"
          >
            {fimEvents.map((event) => (
              <div key={event.id} className="p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center gap-3 mb-2">
                  <FileText className="w-4 h-4 text-blue-400" />
                  <span className="text-white font-mono text-sm">{event.path}</span>
                  <span className={`ml-auto px-2 py-0.5 rounded text-xs font-medium border ${getSeverityColor(event.severity)}`}>
                    {event.event_type.toUpperCase()}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-xs text-gray-400 mb-2">
                  <div>User: <span className="text-gray-300">{event.user}</span></div>
                  <div>Process: <span className="text-gray-300">{event.process}</span></div>
                </div>
                {event.diff && (
                  <div className="mt-2 p-2 bg-black/30 rounded font-mono text-xs text-gray-400 overflow-x-auto">
                    {event.diff}
                  </div>
                )}
                <div className="mt-2 text-xs text-gray-500">
                  {new Date(event.timestamp).toLocaleString()}
                </div>
              </div>
            ))}
            {fimEvents.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                No file integrity events
              </div>
            )}
          </motion.div>
        )}

        {activeTab === 'runtime' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4 max-h-[500px] overflow-y-auto"
          >
            {runtimeEvents.map((event) => (
              <div key={event.id} className="p-4 bg-white/5 rounded-lg border border-white/10 border-l-4 border-l-red-500">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-white font-medium flex items-center gap-2">
                    <Activity className="w-4 h-4 text-red-500" />
                    {event.rule_name}
                  </h4>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getSeverityColor(event.severity)}`}>
                    {event.severity.toUpperCase()}
                  </span>
                </div>
                <p className="text-gray-300 text-sm mb-3">{event.details}</p>
                <div className="flex items-center gap-4 text-xs text-gray-400 bg-black/20 p-2 rounded">
                  <span>Container: {event.container_id}</span>
                  <span>Process: {event.process_name} (PID: {event.pid})</span>
                  <span className="ml-auto">{new Date(event.timestamp).toLocaleTimeString()}</span>
                </div>
              </div>
            ))}
            {runtimeEvents.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                No runtime security events
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
