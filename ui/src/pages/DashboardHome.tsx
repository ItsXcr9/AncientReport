
import { Activity, Brain, CheckCircle, Database, Cpu, HardDrive, TrendingUp, Loader2, Clock, Server, AlertTriangle, AlertCircle, Zap, RefreshCw } from 'lucide-react';
import { StatCard } from '../components/ui/StatCard';
import { ServerInfoCard } from '../components/ServerInfoCard';
import { useOutletContext } from 'react-router-dom';
import { useState, useEffect } from 'react';

// Type definitions for props we expect to receive from the main App layout wrapper
interface DashboardProps {
  report: any;
  loading: boolean;
  isTriggering: boolean;
  cooldownRemaining: number;
  selectedServer: string | null;
  servers: string[];
  serverInfo: any;
  triggerAnalysis: () => void;
  formatCooldownTime: (ms: number) => string;
}

interface LiveAlert {
  id: string;
  severity: string;
  message: string;
  hostname: string;
  metric: string;
  value: number;
  threshold: number;
  triggered_at: string;
}

export default function DashboardHome() {
  const { 
    report, 
    loading, 
    isTriggering, 
    cooldownRemaining, 
    selectedServer, 
    servers, 
    serverInfo, 
    triggerAnalysis, 
    formatCooldownTime 
  } = useOutletContext<DashboardProps>();

  const [liveAlerts, setLiveAlerts] = useState<LiveAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [lastChecked, setLastChecked] = useState<string>('');

  // Fetch live alerts every 30 seconds
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        setAlertsLoading(true);
        const response = await fetch('/api/alerts/live');
        const data = await response.json();
        setLiveAlerts(data.alerts || []);
        setLastChecked(new Date().toLocaleTimeString());
      } catch (error) {
        console.error('Failed to fetch live alerts:', error);
      } finally {
        setAlertsLoading(false);
      }
    };

    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  const criticalAlerts = liveAlerts.filter(a => a.severity === 'critical');
  const warningAlerts = liveAlerts.filter(a => a.severity === 'warning');

  return (
    <div className="space-y-6">
      {/* LIVE ALERTS BANNER - Always at TOP */}
      {liveAlerts.length > 0 ? (
        <div className={`p-4 rounded-lg border shadow-lg ${
          criticalAlerts.length > 0 
            ? 'bg-red-500/15 border-red-500/40 shadow-red-500/10' 
            : 'bg-yellow-500/15 border-yellow-500/40 shadow-yellow-500/10'
        }`}>
          <div className="flex items-center justify-between mb-3">
            <h4 className={`font-semibold text-lg flex items-center gap-2 ${
              criticalAlerts.length > 0 ? 'text-red-400' : 'text-yellow-400'
            }`}>
              <AlertTriangle className="w-5 h-5" />
              {criticalAlerts.length > 0 
                ? `🚨 ${criticalAlerts.length} Critical Alert${criticalAlerts.length > 1 ? 's' : ''}`
                : `⚠️ ${warningAlerts.length} Warning${warningAlerts.length > 1 ? 's' : ''}`
              }
              {warningAlerts.length > 0 && criticalAlerts.length > 0 && (
                <span className="text-yellow-400 text-sm ml-2">+ {warningAlerts.length} warnings</span>
              )}
            </h4>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              {alertsLoading && <RefreshCw className="w-3 h-3 animate-spin" />}
              <span>Updated: {lastChecked}</span>
            </div>
          </div>
          <div className="space-y-2">
            {criticalAlerts.map((alert, i) => (
              <div key={alert.id || i} className="flex items-start gap-2 text-sm">
                <span className="text-red-400 font-bold">●</span>
                <span className="text-gray-200">{alert.message}</span>
                <span className="text-gray-500 text-xs">({alert.hostname})</span>
              </div>
            ))}
            {warningAlerts.slice(0, 5).map((alert, i) => (
              <div key={alert.id || i} className="flex items-start gap-2 text-sm">
                <span className="text-yellow-400 font-bold">●</span>
                <span className="text-gray-300">{alert.message}</span>
                <span className="text-gray-500 text-xs">({alert.hostname})</span>
              </div>
            ))}
            {warningAlerts.length > 5 && (
              <div className="text-xs text-gray-500 mt-1">
                ...and {warningAlerts.length - 5} more warnings
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="p-4 bg-green-500/10 rounded-lg border border-green-500/30 text-green-400 flex items-center gap-3">
          <CheckCircle className="w-5 h-5" />
          <div>
            <span className="font-medium">All Systems Healthy</span>
            <span className="text-gray-400 text-sm ml-2">• Last checked: {lastChecked || 'checking...'}</span>
          </div>
        </div>
      )}

      {/* Header Section */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white font-display tracking-tight">System Overview</h1>
          <p className="text-gray-400 text-sm">Real-time performance and health metrics</p>
        </div>
        
        {/* Trigger Analysis Button */}
        <button
            onClick={triggerAnalysis}
            disabled={cooldownRemaining > 0 || isTriggering}
            className={`px-4 py-2 rounded-lg transition-colors text-sm font-medium flex items-center gap-2 ${
            cooldownRemaining > 0 || isTriggering
                ? 'bg-gray-600 cursor-not-allowed opacity-60'
                : 'bg-blue-500 hover:bg-blue-600'
            }`}
        >
            {isTriggering ? (
            <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Analyzing...</span>
            </>
            ) : cooldownRemaining > 0 ? (
            <>
                <Clock className="w-4 h-4" />
                <span>Cooldown: {formatCooldownTime(cooldownRemaining)}</span>
            </>
            ) : (
            'Trigger Analysis'
            )}
        </button>
      </div>

       {/* Server Info Cards */}
       {selectedServer ? (
          <div className="mb-6">
            <ServerInfoCard selectedServer={selectedServer} />
          </div>
        ) : (
          <div className="mb-6 grid grid-cols-1 gap-6">
            {servers.map((server) => (
              <ServerInfoCard key={server} selectedServer={server} />
            ))}
          </div>
        )}

      {/* Hero Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
            title="CPU Usage"
            value={`${report?.resource_usage?.cpu?.average?.toFixed(1) || 0}%`}
            icon={Cpu}
            color="blue"
            trend={report?.resource_usage?.cpu?.peak ? `Peak: ${report.resource_usage.cpu.peak.toFixed(1)}%` : undefined}
            trendUp={false}
            delay={0.1}
        />
        <StatCard
            title="Memory"
            value={`${report?.resource_usage?.memory?.average?.toFixed(1) || 0}%`}
            icon={Brain}
            color="purple"
            trend={report?.resource_usage?.memory?.peak ? `Peak: ${report.resource_usage.memory.peak.toFixed(1)}%` : undefined}
            trendUp={false}
            delay={0.2}
        />
        <StatCard
            title="Disk I/O"
            value={`${((report?.resource_usage?.disk_io?.reads_per_sec || 0) + (report?.resource_usage?.disk_io?.writes_per_sec || 0)).toFixed(0)}`}
            icon={HardDrive}
            color="yellow"
            trend={`${report?.resource_usage?.disk_io?.latency_ms?.toFixed(1) || 0}ms lat`}
            trendUp={true}
            delay={0.3}
        />
        <StatCard
            title="Network"
            value={`${((report?.resource_usage?.network?.packets_sent || 0) + (report?.resource_usage?.network?.packets_received || 0)).toLocaleString()}`}
            icon={Activity}
            color="green"
            trend={`${report?.resource_usage?.network?.drops || 0} drops`}
            trendUp={true}
            delay={0.4}
        />
      </div>

      {/* Main Content Split: Analysis vs Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-3 space-y-6">
            {!selectedServer ? (
               // All Servers View
               <div className="space-y-6">
                 {/* General Information Summary */}
                 <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                   <div className="p-4 glass-stat rounded-lg">
                     <div className="text-gray-400 text-sm mb-1">Total Servers</div>
                     <div className="text-2xl font-bold flex items-center gap-2">
                       <Server className="w-5 h-5 text-blue-400" />
                       {servers.length}
                     </div>
                   </div>
                   <div className="p-4 glass-stat rounded-lg">
                     <div className="text-gray-400 text-sm mb-1">Total CPU Cores</div>
                     <div className="text-2xl font-bold flex items-center gap-2">
                       <Cpu className="w-5 h-5 text-purple-400" />
                       {serverInfo ? Object.values(serverInfo).reduce((acc: number, s: any) => acc + (s.cpu_cores || 0), 0) : '-'}
                     </div>
                   </div>
                   <div className="p-4 glass-stat rounded-lg">
                     <div className="text-gray-400 text-sm mb-1">Total Memory</div>
                     <div className="text-2xl font-bold flex items-center gap-2">
                       <Database className="w-5 h-5 text-green-400" />
                       {serverInfo ? Object.values(serverInfo).reduce((acc: number, s: any) => acc + (s.memory_total_gb || 0), 0).toFixed(0) : '-'} GB
                     </div>
                   </div>
                   <div className="p-4 glass-stat rounded-lg">
                     <div className="text-gray-400 text-sm mb-1">Total Storage</div>
                     <div className="text-2xl font-bold flex items-center gap-2">
                       <Database className="w-5 h-5 text-yellow-400" />
                       {serverInfo ? Object.values(serverInfo).reduce((acc: number, s: any) => acc + (s.disk_total_gb || 0), 0).toFixed(0) : '-'} GB
                     </div>
                   </div>
                 </div>
 
                 {/* Critical Alerts Only */}
                 {report && report.ai_insights?.critical_alerts && report.ai_insights.critical_alerts.length > 0 ? (
                   <div className="p-4 bg-red-500/10 rounded-lg border border-red-500/20">
                     <h4 className="font-medium text-red-400 mb-2 flex items-center gap-2">
                       <AlertTriangle className="w-5 h-5" />
                       Critical Alerts Across All Servers
                     </h4>
                     <ul className="text-sm text-gray-300 space-y-1">
                       {report.ai_insights.critical_alerts.map((alert: any, i: number) => (
                         <li key={i}>• {String(alert)}</li>
                       ))}
                     </ul>
                   </div>
                 ) : (
                   <div className="p-4 bg-green-500/10 rounded-lg border border-green-500/20 text-green-400 flex items-center gap-2">
                     <CheckCircle className="w-5 h-5" />
                     No critical alerts detected across the fleet.
                   </div>
                 )}
               </div>
             ) : (
               // Single Server View
               <div className="space-y-4 relative">
                 {loading && !report ? (
                   <div className="p-4 text-center text-gray-400">Loading initial data...</div>
                 ) : report ? (
                   <>
                     <div className="p-4 bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-lg border border-blue-500/20">
                       <div className="flex items-start gap-3">
                         <AlertCircle className={`w-5 h-5 mt-1 ${
                           report.system_health.status === 'excellent' ? 'text-green-400' :
                           report.system_health.status === 'healthy' ? 'text-blue-400' :
                           report.system_health.status === 'warning' ? 'text-yellow-400' :
                           'text-red-400'
                         }`} />
                         <div className="flex-1">
                           <div className="flex items-center justify-between mb-1">
                             <h3 className="font-medium">System Health: {report.system_health.overall_score}/100</h3>
                             <span className={`text-xs px-2 py-1 rounded ${
                               report.system_health.status === 'excellent' ? 'bg-green-500/20 text-green-400' :
                               report.system_health.status === 'healthy' ? 'bg-blue-500/20 text-blue-400' :
                               report.system_health.status === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                               'bg-red-500/20 text-red-400'
                             }`}>
                               {report.system_health.status}
                             </span>
                           </div>
                           <p className="text-sm text-gray-400">
                             Report ID: {report.report_id ? new Date(report.report_id).toLocaleString() : 'N/A'}
                           </p>
                           {report.system_health.pressure_points && report.system_health.pressure_points.length > 0 && (
                             <p className="text-xs text-yellow-400 mt-1">
                               Pressure points: {report.system_health.pressure_points.join(', ')}
                             </p>
                           )}
                         </div>
                       </div>
                     </div>
 
                     {/* AI Hourly Summary */}
                     {report.ai_insights && (
                       <div className="p-4 bg-gradient-to-r from-purple-500/10 to-blue-500/10 rounded-lg border border-purple-500/20">
                         <h4 className="font-medium text-purple-400 mb-3 flex items-center gap-2">
                           <Brain className="w-4 h-4" />
                           AI System Summary (Past Hour)
                         </h4>
                         <div className="space-y-3 text-sm text-gray-300">
                           {report.ai_insights.critical_alerts && report.ai_insights.critical_alerts.length > 0 ? (
                             <p className="text-yellow-300">
                               ⚠️ System has {report.ai_insights.critical_alerts.length} critical alert(s) requiring attention.
                             </p>
                           ) : (
                             <p className="text-green-300">
                               ✓ No critical issues detected in the past hour.
                             </p>
                           )}
                           
                           <div>
                             <p className="text-gray-400 text-xs mb-1">Performance Summary:</p>
                             <p>
                               CPU averaged {report.resource_usage?.cpu?.average?.toFixed(1)}% with peak at {report.resource_usage?.cpu?.peak?.toFixed(1)}%. 
                               Memory utilization at {report.resource_usage?.memory?.average?.toFixed(1)}%.
                               {report.resource_usage?.network?.drops > 0 && (
                                 <span className="text-yellow-300"> Network experienced {report.resource_usage.network.drops} packet drops.</span>
                               )}
                             </p>
                           </div>
                         </div>
                       </div>
                     )}
                   </>
                     ) : (
                       <div className="p-4 text-center text-gray-400">
                         No report available yet. Trigger analysis to start.
                       </div>
                     )}
               </div>
             )}
          </div>
      </div>
    </div>
  );
}
