import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, AlertCircle, CheckCircle, Server, Brain, Cpu, Database, Network, TrendingUp, Loader2, Clock } from 'lucide-react';
import { CPUChart } from './components/CPUChart'
import { MemoryChart } from './components/MemoryChart'
import { DiskIOChart } from './components/DiskIOChart'
import { NetworkChart } from './components/NetworkChart'
import { DockerContainers } from './components/DockerContainers';
import { ContainerHealthchecks } from './components/ContainerHealthchecks';

import ServerSelector from './components/ServerSelector';
import { ServerInfoCard } from './components/ServerInfoCard'

interface SystemHealth {
  status: string
  service: string
  version: string
}

interface Report {
  report_id: string
  system_health: {
    overall_score: number
    status: string
    pressure_points: string[]
  }
  resource_usage: {
    cpu: { average: number; peak: number }
    memory: { average: number; peak: number }
    disk_io: { reads_per_sec: number; writes_per_sec: number; latency_ms: number }
    network: { packets_sent: number; packets_received: number; drops: number }
  }
  top_processes?: {
    cpu: Array<{ name: string; pid: string; average: number; peak: number; command_line?: string }>
    memory: Array<{ name: string; pid: string; average: number; peak: number; command_line?: string }>
    disk_io: Array<{ name: string; pid: string; average: number; peak: number; command_line?: string }>
    network: Array<{ name: string; pid: string; average: number; peak: number; command_line?: string }>
  }
  ai_insights: {
    critical_alerts: string[]
    recommendations: Array<{ title: string; description: string; priority: string }>
    capacity_forecast: any
    config_optimizations: any[]
  }
  anomalies: any[]
}

function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [reportLoading, setReportLoading] = useState(false)
  const [lastTriggerTime, setLastTriggerTime] = useState<number | null>(() => {
    // Load from localStorage on mount
    const stored = localStorage.getItem('lastTriggerTime')
    if (stored) {
      const time = parseInt(stored, 10)
      const COOLDOWN_MS = 5 * 60 * 1000
      const elapsed = Date.now() - time
      // Only restore if still in cooldown
      if (elapsed < COOLDOWN_MS) {
        return time
      } else {
        localStorage.removeItem('lastTriggerTime')
      }
    }
    return null
  })
  const [cooldownRemaining, setCooldownRemaining] = useState<number>(0)
  const [isTriggering, setIsTriggering] = useState(false)
  const [servers, setServers] = useState<string[]>([])
  const [selectedServer, setSelectedServer] = useState<string | null>(null)
  const [serverInfo, setServerInfo] = useState<any>(null)

  useEffect(() => {
    fetchServers()
    fetchHealth()
    fetchLatestReport()
    const interval = setInterval(() => {
      fetchServers()
      fetchHealth()
      fetchLatestReport()
    }, 600000) // Refresh every 10 minutes (600000ms)
    return () => clearInterval(interval)
  }, [])

  // Refetch report when selected server changes
  useEffect(() => {
    fetchLatestReport()
  }, [selectedServer])

  const fetchServers = async () => {
    try {
      const res = await fetch('/api/servers')
      if (res.ok) {
        const data = await res.json()
        setServers(data.servers || [])
      }
      
      // Also fetch server info for the summary view
      const infoRes = await fetch('/api/servers/info')
      if (infoRes.ok) {
        const infoData = await infoRes.json()
        setServerInfo(infoData.servers || {})
      }
    } catch (error) {
      console.error('Failed to fetch servers:', error)
    }
  }

  // Cooldown timer for trigger analysis button
  useEffect(() => {
    if (lastTriggerTime === null) {
      setCooldownRemaining(0)
      return
    }

    const COOLDOWN_MS = 5 * 60 * 1000 // 5 minutes in milliseconds
    const updateCooldown = () => {
      const elapsed = Date.now() - lastTriggerTime!
      const remaining = Math.max(0, COOLDOWN_MS - elapsed)
      setCooldownRemaining(remaining)

      if (remaining > 0) {
        // Update every second
        setTimeout(updateCooldown, 1000)
      } else {
        setLastTriggerTime(null)
        localStorage.removeItem('lastTriggerTime')
      }
    }

    updateCooldown()
  }, [lastTriggerTime])

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/')
      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`)
      }
      const data = await res.json()
      setHealth(data)
      setLoading(false)
    } catch (error) {
      console.error('Failed to fetch health:', error)
      setLoading(false)
      setHealth({
        status: 'offline',
        service: 'AncientReport AI',
        version: '1.0.0'
      })
    }
  }

  const fetchLatestReport = async () => {
    try {
      setReportLoading(true)
      let url = '/api/reports/latest'
      if (selectedServer) {
        url += `?hostname=${selectedServer}`
      }
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`)
      }
      const data = await res.json()
      if (data.report_id) {
        // Ensure top_processes structure exists with safe defaults
        if (!data.top_processes) {
          data.top_processes = {
            cpu: [],
            memory: [],
            disk_io: [],
            network: []
          }
        }
        // Ensure arrays exist and are valid
        if (!Array.isArray(data.top_processes.cpu)) data.top_processes.cpu = []
        if (!Array.isArray(data.top_processes.memory)) data.top_processes.memory = []
        if (!Array.isArray(data.top_processes.disk_io)) data.top_processes.disk_io = []
        if (!Array.isArray(data.top_processes.network)) data.top_processes.network = []
        
        // Debug logging for top_processes
        console.log('Top Processes Data:', {
          exists: !!data.top_processes,
          cpu_count: data.top_processes?.cpu?.length || 0,
          memory_count: data.top_processes?.memory?.length || 0,
          disk_io_count: data.top_processes?.disk_io?.length || 0,
          network_count: data.top_processes?.network?.length || 0,
          cpu_sample: data.top_processes?.cpu?.[0] || null
        })
        
        // Ensure ai_insights structure exists with safe defaults
        if (!data.ai_insights) {
          data.ai_insights = {
            critical_alerts: [],
            recommendations: [],
            capacity_forecast: {},
            config_optimizations: []
          }
        }
        
        // Ensure critical_alerts is always an array
        if (!data.ai_insights.critical_alerts) {
          data.ai_insights.critical_alerts = []
        } else if (!Array.isArray(data.ai_insights.critical_alerts)) {
          // Convert to array if it's not
          if (typeof data.ai_insights.critical_alerts === 'string') {
            data.ai_insights.critical_alerts = [data.ai_insights.critical_alerts]
          } else {
            data.ai_insights.critical_alerts = []
          }
        }
        
        // Filter out empty strings
        data.ai_insights.critical_alerts = data.ai_insights.critical_alerts.filter(
          (alert: any) => alert && String(alert).trim()
        )
        
        // Log for debugging
        if (data.ai_insights.critical_alerts.length > 0) {
          console.log('Critical alerts found:', data.ai_insights.critical_alerts)
        } else {
          console.log('No critical alerts in report')
        }
        
        setReport(data)
      }
    } catch (error) {
      console.error('Failed to fetch report:', error)
    } finally {
      setReportLoading(false)
    }
  }

  const triggerAnalysis = async () => {
    // Check cooldown
    if (cooldownRemaining > 0 || isTriggering) {
      return
    }

    try {
      setIsTriggering(true)
      setReportLoading(true)
      const triggerTime = Date.now()
      setLastTriggerTime(triggerTime)
      // Persist to localStorage to survive page refreshes
      localStorage.setItem('lastTriggerTime', triggerTime.toString())
      
      console.log('Triggering analysis...', {
        browser: navigator.userAgent,
        timestamp: new Date().toISOString()
      })
      
      let url = '/api/analysis/trigger/hourly'
      if (selectedServer) {
        url += `?hostname=${selectedServer}`
      }
      const res = await fetch(url, { method: 'POST' })
      
      console.log('Analysis trigger response:', {
        status: res.status,
        statusText: res.statusText,
        ok: res.ok,
        headers: Object.fromEntries(res.headers.entries())
      })
      
      if (!res.ok) {
        const errorText = await res.text()
        console.error('Analysis trigger failed:', {
          status: res.status,
          statusText: res.statusText,
          body: errorText
        })
        throw new Error(`Failed to trigger analysis: ${res.status} ${res.statusText}`)
      }
      
      const data = await res.json()
      console.log('Analysis trigger response data:', {
        has_report: !!data.report,
        has_status: !!data.status,
        report_keys: data.report ? Object.keys(data.report) : [],
        ai_insights: data.report?.ai_insights ? {
          has_recommendations: !!data.report.ai_insights.recommendations,
          recommendations_count: Array.isArray(data.report.ai_insights.recommendations) ? data.report.ai_insights.recommendations.length : 'N/A',
          recommendations_type: typeof data.report.ai_insights.recommendations
        } : null
      })
      
      if (data.report) {
        setReport(data.report)
      } else {
        // Fetch the latest report after a short delay
        console.log('No report in response, fetching latest report in 2 seconds...')
        setTimeout(fetchLatestReport, 2000)
      }
      alert('Analysis triggered successfully!')
    } catch (error) {
      console.error('Analysis trigger error:', error, {
        name: error instanceof Error ? error.name : 'Unknown',
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      })
      alert(`Failed to trigger analysis: ${error instanceof Error ? error.message : 'Unknown error'}`)
      // Reset cooldown on error so user can retry
      setLastTriggerTime(null)
      setCooldownRemaining(0)
      localStorage.removeItem('lastTriggerTime')
    } finally {
      setIsTriggering(false)
      setReportLoading(false)
    }
  }

  const formatCooldownTime = (ms: number): string => {
    const minutes = Math.floor(ms / 60000)
    const seconds = Math.floor((ms % 60000) / 1000)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      {/* Header */}
      <header className="border-b border-white/10 backdrop-blur-xl bg-slate-900/50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Brain className="w-8 h-8 text-blue-400" />
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                Ancient Report AI
              </h1>
            </div>
            <div className="flex items-center gap-4">
              <ServerSelector 
                servers={servers}
                selectedServer={selectedServer}
                onServerChange={setSelectedServer}
              />
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${health?.status === 'running' ? 'bg-green-400' : 'bg-red-400'}`} />
                <span className="text-sm text-gray-400">
                  {loading ? 'Connecting...' : health?.status || 'Offline'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {/* Server Info Card */}
        {selectedServer && (
          <div className="mb-6">
            <ServerInfoCard selectedServer={selectedServer} />
          </div>
        )}


        {/* Latest Analysis Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <section className="lg:col-span-3 bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-blue-400" />
                Latest Analysis
              </h2>
              <div className="flex items-center gap-2">
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
                      <span>Triggering...</span>
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
            </div>
            
            {!selectedServer ? (
              // All Servers View
              <div className="space-y-6">
                {/* General Information Summary */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                    <div className="text-gray-400 text-sm mb-1">Total Servers</div>
                    <div className="text-2xl font-bold flex items-center gap-2">
                      <Server className="w-5 h-5 text-blue-400" />
                      {servers.length}
                    </div>
                  </div>
                  <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                    <div className="text-gray-400 text-sm mb-1">Total CPU Cores</div>
                    <div className="text-2xl font-bold flex items-center gap-2">
                      <Cpu className="w-5 h-5 text-purple-400" />
                      {serverInfo ? Object.values(serverInfo).reduce((acc: number, s: any) => acc + (s.cpu_cores || 0), 0) : '-'}
                    </div>
                  </div>
                  <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                    <div className="text-gray-400 text-sm mb-1">Total Memory</div>
                    <div className="text-2xl font-bold flex items-center gap-2">
                      <Database className="w-5 h-5 text-green-400" />
                      {serverInfo ? Object.values(serverInfo).reduce((acc: number, s: any) => acc + (s.memory_total_gb || 0), 0).toFixed(0) : '-'} GB
                    </div>
                  </div>
                  <div className="p-4 bg-white/5 rounded-lg border border-white/10">
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
                      {report.ai_insights.critical_alerts.map((alert, i) => (
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
                
                <div className="text-center text-sm text-gray-500 mt-4">
                  Select a specific server to view detailed analysis, health scores, and top processes.
                </div>
              </div>
            ) : (
              // Single Server View (Existing Logic)
              <div className="space-y-4 relative">
                {isTriggering && (
                  <div className="absolute inset-0 bg-black/50 backdrop-blur-sm rounded-lg z-10 flex items-center justify-center">
                    <div className="bg-white/10 rounded-lg p-6 border border-white/20">
                      <div className="flex flex-col items-center gap-3">
                        <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
                        <p className="text-sm font-medium text-gray-200">Triggering Analysis...</p>
                        <p className="text-xs text-gray-400">This may take a few moments</p>
                      </div>
                    </div>
                  </div>
                )}
                {reportLoading && !isTriggering ? (
                  <div className="p-4 text-center text-gray-400">Loading report...</div>
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


                    {(() => {
                      const alerts = report.ai_insights?.critical_alerts;
                      const hasAlerts = Array.isArray(alerts) && alerts.length > 0;
                      if (hasAlerts) {
                        return (
                          <div className="p-4 bg-red-500/10 rounded-lg border border-red-500/20">
                            <h4 className="font-medium text-red-400 mb-2">Critical Alerts</h4>
                            <ul className="text-sm text-gray-300 space-y-1">
                              {alerts.map((alert, i) => (
                                <li key={i}>• {String(alert)}</li>
                              ))}
                            </ul>
                          </div>
                        );
                      }
                      return null;
                    })()}

                    {/* AI Hourly Summary - New Section */}
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

                          {report.anomalies && report.anomalies.length > 0 && (
                            <div>
                              <p className="text-gray-400 text-xs mb-1">Anomalies Detected:</p>
                              <p className="text-yellow-300">
                                {report.anomalies.length} metric(s) deviated from baseline behavior.
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                      <MetricBox 
                        label="CPU Usage" 
                        value={`${report.resource_usage?.cpu?.average?.toFixed(1) || 0}%`} 
                        trend={`Peak: ${report.resource_usage?.cpu?.peak?.toFixed(1) || 0}%`} 
                      />
                      <MetricBox 
                        label="Memory" 
                        value={`${report.resource_usage?.memory?.average?.toFixed(1) || 0}%`} 
                        trend={`Peak: ${report.resource_usage?.memory?.peak?.toFixed(1) || 0}%`} 
                      />
                      <MetricBox 
                        label="Disk I/O" 
                        value={`${((report.resource_usage?.disk_io?.reads_per_sec || 0) + (report.resource_usage?.disk_io?.writes_per_sec || 0)).toFixed(0)} IOPS`} 
                        trend={`${report.resource_usage?.disk_io?.latency_ms?.toFixed(1) || 0}ms latency`} 
                      />
                      <MetricBox 
                        label="Network" 
                        value={`${((report.resource_usage?.network?.packets_sent || 0) + (report.resource_usage?.network?.packets_received || 0)).toLocaleString()} packets`} 
                        trend={`${report.resource_usage?.network?.drops || 0} drops`} 
                      />
                    </div>

                    <div className="mt-4 space-y-3">
                      <h4 className="font-semibold text-base mb-3 flex items-center gap-2">
                        <Activity className="w-4 h-4 text-blue-400" />
                        Top Processes (Hourly Summary)
                      </h4>
                      {report.top_processes ? (
                        <>
                          {report.top_processes.cpu && Array.isArray(report.top_processes.cpu) && report.top_processes.cpu.length > 0 && (
                          <div className="p-4 bg-gradient-to-r from-blue-500/10 to-blue-600/5 rounded-lg border border-blue-500/20">
                            <h5 className="text-sm font-medium text-blue-400 mb-3 flex items-center gap-2">
                              <Activity className="w-4 h-4" />
                              Top 3 CPU Consumers
                            </h5>
                            <div className="space-y-2">
                              {report.top_processes.cpu.map((proc, i) => (
                                <div key={i} className="p-2 bg-white/5 rounded border border-white/10">
                                  <div className="flex items-center justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-bold text-blue-400 w-6">#{i + 1}</span>
                                      <span className="text-sm font-medium text-gray-200">{proc?.name || 'unknown'}</span>
                                      <span className="text-xs text-gray-500">(PID: {proc?.pid || 'N/A'})</span>
                                    </div>
                                    <div className="text-right">
                                      <span className="text-sm font-semibold text-blue-300">{(proc?.average || 0).toFixed(1)}%</span>
                                      <span className="text-xs text-gray-500 ml-2">peak: {(proc?.peak || 0).toFixed(1)}%</span>
                                    </div>
                                  </div>
                                  {proc?.command_line && (
                                    <div className="ml-8 mt-1">
                                      <span className="text-xs text-gray-400 font-mono break-all">{proc.command_line}</span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {report.top_processes.memory && Array.isArray(report.top_processes.memory) && report.top_processes.memory.length > 0 && (
                          <div className="p-4 bg-gradient-to-r from-purple-500/10 to-purple-600/5 rounded-lg border border-purple-500/20">
                            <h5 className="text-sm font-medium text-purple-400 mb-3 flex items-center gap-2">
                              <Database className="w-4 h-4" />
                              Top 3 Memory Consumers
                            </h5>
                            <div className="space-y-2">
                              {report.top_processes.memory.map((proc, i) => (
                                <div key={i} className="p-2 bg-white/5 rounded border border-white/10">
                                  <div className="flex items-center justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-bold text-purple-400 w-6">#{i + 1}</span>
                                      <span className="text-sm font-medium text-gray-200">{proc?.name || 'unknown'}</span>
                                      <span className="text-xs text-gray-500">(PID: {proc?.pid || 'N/A'})</span>
                                    </div>
                                    <div className="text-right">
                                      <span className="text-sm font-semibold text-purple-300">{(proc?.average || 0).toFixed(1)} MB</span>
                                      <span className="text-xs text-gray-500 ml-2">peak: {(proc?.peak || 0).toFixed(1)} MB</span>
                                    </div>
                                  </div>
                                  {proc?.command_line && (
                                    <div className="ml-8 mt-1">
                                      <span className="text-xs text-gray-400 font-mono break-all">{proc.command_line}</span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {report.top_processes.disk_io && Array.isArray(report.top_processes.disk_io) && report.top_processes.disk_io.length > 0 && (
                          <div className="p-4 bg-gradient-to-r from-green-500/10 to-green-600/5 rounded-lg border border-green-500/20">
                            <h5 className="text-sm font-medium text-green-400 mb-3 flex items-center gap-2">
                              <Activity className="w-4 h-4" />
                              Top 3 Disk I/O Consumers
                            </h5>
                            <div className="space-y-2">
                              {report.top_processes.disk_io.map((proc, i) => (
                                <div key={i} className="p-2 bg-white/5 rounded border border-white/10">
                                  <div className="flex items-center justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs font-bold text-green-400 w-6">#{i + 1}</span>
                                      <span className="text-sm font-medium text-gray-200">{proc?.name || 'unknown'}</span>
                                      <span className="text-xs text-gray-500">(PID: {proc?.pid || 'N/A'})</span>
                                    </div>
                                    <div className="text-right">
                                      <span className="text-sm font-semibold text-green-300">{(proc?.average || 0).toFixed(1)} MB</span>
                                      <span className="text-xs text-gray-500 ml-2">peak: {(proc?.peak || 0).toFixed(1)} MB</span>
                                    </div>
                                  </div>
                                  {proc?.command_line && (
                                    <div className="ml-8 mt-1">
                                      <span className="text-xs text-gray-400 font-mono break-all">{proc.command_line}</span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {(!report.top_processes.cpu || !Array.isArray(report.top_processes.cpu) || report.top_processes.cpu.length === 0) && 
                         (!report.top_processes.memory || !Array.isArray(report.top_processes.memory) || report.top_processes.memory.length === 0) && 
                         (!report.top_processes.disk_io || !Array.isArray(report.top_processes.disk_io) || report.top_processes.disk_io.length === 0) && (
                          <div className="p-4 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400 text-sm">
                            {report.top_processes ? 
                              'Top processes data exists but is empty. Process metrics may not be available for the selected time period.' :
                              'No process data available yet. Wait for the next hourly analysis.'
                            }
                          </div>
                        )}
                        </>
                      ) : (
                        <div className="p-4 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400 text-sm">
                          No process data available yet. Wait for the next hourly analysis.
                        </div>
                      )}
                    </div>

                    {(() => {
                      try {
                        const recommendations = report.ai_insights?.recommendations;
                        
                        // Validate recommendations array
                        if (!recommendations || !Array.isArray(recommendations) || recommendations.length === 0) {
                          if (report.ai_insights) {
                            console.log('No recommendations available:', {
                              has_ai_insights: !!report.ai_insights,
                              recommendations_type: typeof recommendations,
                              recommendations_is_array: Array.isArray(recommendations),
                              recommendations_length: Array.isArray(recommendations) ? recommendations.length : 'N/A',
                              recommendations_value: recommendations
                            });
                          }
                          return (
                            <div className="mt-4 p-3 bg-white/5 rounded-lg border border-white/10 text-center text-gray-400 text-sm">
                              No AI recommendations available yet.
                            </div>
                          );
                        }
                        
                        console.log(`Rendering ${recommendations.length} recommendations`);
                        
                        return (
                          <div className="mt-4 space-y-2">
                            <h4 className="font-medium text-sm mb-2">AI Recommendations</h4>
                            {recommendations.slice(0, 5).map((rec, i) => {
                              try {
                                // Handle different formats: string, object with action/details, or object with title/description
                                let action = '';
                                let details = '';
                                let priority = 'medium';
                                
                                if (typeof rec === 'string') {
                                  action = rec;
                                  details = rec;
                                } else if (typeof rec === 'object' && rec !== null) {
                                  // Try multiple possible formats
                                  action = rec.title || rec.action || rec.name || '';
                                  details = rec.description || rec.details || rec.explanation || action || '';
                                  priority = (rec.priority || 'medium').toLowerCase();
                                  
                                  // Validate priority
                                  if (!['high', 'medium', 'low'].includes(priority)) {
                                    priority = 'medium';
                                  }
                                } else {
                                  console.warn(`Unexpected recommendation format at index ${i}:`, typeof rec, rec);
                                  action = String(rec || 'Unknown recommendation');
                                  details = action;
                                }
                                
                                // Ensure we have at least a title
                                if (!action && details) {
                                  action = details.substring(0, 80);
                                } else if (!action) {
                                  action = `Recommendation ${i + 1}`;
                                }
                                
                                return (
                                  <div key={i} className="p-3 bg-white/5 rounded-lg border border-white/10">
                                    <div className="flex items-start gap-2">
                                      <span className={`font-bold ${
                                        priority === 'high' ? 'text-red-400' :
                                        priority === 'medium' ? 'text-yellow-400' :
                                        'text-blue-400'
                                      }`}>#{i + 1}</span>
                                      <div className="flex-1">
                                        {action && <p className="text-sm font-medium text-gray-200">{action}</p>}
                                        {details && details !== action && (
                                          <p className="text-xs text-gray-400 mt-1">{details}</p>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                );
                              } catch (error) {
                                console.error(`Error rendering recommendation ${i}:`, error, rec);
                                return (
                                  <div key={i} className="p-3 bg-red-500/10 rounded-lg border border-red-500/20 text-red-400 text-sm">
                                    Error displaying recommendation {i + 1}
                                  </div>
                                );
                              }
                            })}
                          </div>
                        );
                      } catch (error) {
                        console.error('Error rendering recommendations section:', error, {
                          ai_insights: report.ai_insights,
                          recommendations: report.ai_insights?.recommendations
                        });
                        return (
                          <div className="mt-4 p-3 bg-red-500/10 rounded-lg border border-red-500/20 text-center text-red-400 text-sm">
                            Error loading recommendations. Please check the console for details.
                          </div>
                        );
                      }
                    })()}
                  </>
                ) : (
                  <div className="p-4 text-center text-gray-400">
                    No report available yet. Click "Trigger Analysis" to generate one.
                  </div>
                )}
              </div>
            )}
        </section>
        </div>

        {/* Docker Containers Section - Horizontal Layout */}
        <div className="mt-8 mb-8">
          <DockerContainers selectedServer={selectedServer} />
        </div>

        {/* Container Healthchecks Section */}
        <div className="mt-8 mb-8">
          <ContainerHealthchecks selectedServer={selectedServer} />
        </div>

        {/* Metrics History Charts */}
        <div className="mt-8">
          <h2 className="text-2xl font-semibold mb-4">Metrics History</h2>
          
          {selectedServer ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <CPUChart timeRange="1h" hostname={selectedServer} />
              <MemoryChart timeRange="1h" hostname={selectedServer} />
              <DiskIOChart timeRange="1h" hostname={selectedServer} />
              <NetworkChart timeRange="1h" hostname={selectedServer} />
            </div>
          ) : (
            <div className="space-y-12">
              {servers.map(server => (
                <div key={server} className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
                  <h3 className="text-xl font-medium mb-4 flex items-center gap-2 text-blue-300">
                    <Server className="w-5 h-5" />
                    {server}
                  </h3>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <CPUChart timeRange="1h" hostname={server} />
                    <MemoryChart timeRange="1h" hostname={server} />
                    <DiskIOChart timeRange="1h" hostname={server} />
                    <NetworkChart timeRange="1h" hostname={server} />
                  </div>
                </div>
              ))}
              {servers.length === 0 && (
                <div className="text-center text-gray-400 py-8">
                  No active servers found.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Features */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <FeatureCard
            title="eBPF Monitoring"
            description="Kernel-level monitoring with <3% overhead"
            icon={<Activity className="w-8 h-8" />}
          />
          <FeatureCard
            title="AI Analysis"
            description="Gemini-powered insights every hour"
            icon={<Brain className="w-8 h-8" />}
          />
          <FeatureCard
            title="Capacity Planning"
            description="Predictive recommendations"
            icon={<TrendingUp className="w-8 h-8" />}
          />
        </div>
        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-8 mb-8">
          <StatusCard
            icon={<Activity className="w-6 h-6" />}
            title="System Health"
            value="Operational"
            color="text-green-400"
          />
          <StatusCard
            icon={<Server className="w-6 h-6" />}
            title="Monitoring"
            value="Active"
            color="text-blue-400"
          />
          <StatusCard
            icon={<Database className="w-6 h-6" />}
            title="ClickHouse"
            value="Online"
            color="text-purple-400"
          />
          <StatusCard
            icon={<Brain className="w-6 h-6" />}
            title="AI Engine"
            value="Gemini"
            color="text-pink-400"
          />
        </div>
      </main>
    </div>
  )
}

function StatusCard({ icon, title, value, color }: {
  icon: React.ReactNode
  title: string
  value: string
  color: string
}) {
  return (
    <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm hover:bg-white/10 transition-colors">
      <div className={`${color} mb-3`}>{icon}</div>
      <div className="text-sm text-gray-400 mb-1">{title}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  )
}

function MetricBox({ label, value, trend }: {
  label: string
  value: string
  trend: string
}) {
  return (
    <div className="p-3 bg-white/5 rounded-lg border border-white/10">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-gray-500">{trend}</div>
    </div>
  )
}


function FeatureCard({ title, description, icon }: {
  title: string
  description: string
  icon: React.ReactNode
}) {
  return (
    <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
      <div className="text-blue-400 mb-4">{icon}</div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-gray-400">{description}</p>
    </div>
  )
}

export default App
