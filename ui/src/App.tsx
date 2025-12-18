import { useEffect, useState } from 'react'
import { Brain, Settings } from 'lucide-react';
import { motion } from 'framer-motion';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

// Layout & Sections
import { DashboardLayout } from './layouts/DashboardLayout';

// Page imports (Default exports)
import DashboardHome from './pages/DashboardHome';
import Infrastructure from './pages/Infrastructure';
import Observability from './pages/Observability';
import Security from './pages/Security';
import Analysis from './pages/Analysis';
import SettingsPage from './pages/SettingsPage';
import Dashboards from './pages/Dashboards';
import DashboardView from './pages/DashboardView';
import Alerts from './pages/Alerts';
import RecordingRules from './pages/RecordingRules';
import SNMPMonitoring from './pages/SNMPMonitoring';
import SystemHealth from './pages/SystemHealth';
import PrometheusDiscovery from './pages/PrometheusDiscovery';
import AIIntelligence from './pages/AIIntelligence';

import { SettingsModal } from './components/SettingsModal';
import { AIChat } from './components/AIChat';
import { useRealtimeMetrics } from './hooks/useRealtimeMetrics';
import { useRealtimeAlerts } from './hooks/useRealtimeAlerts';
import { useConfig } from './hooks/useConfig';

// Components needed for the Header
import { Badge } from './components/ui/Badge';
import ServerSelector from './components/ServerSelector';
import { AlertCenter } from './components/AlertCenter';

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
    active_flows?: Array<{ remote: string; state: string; count: number }>
  }
  ai_insights: {
    critical_alerts: string[]
    recommendations: Array<{ 
      title: string; 
      description: string; 
      priority: string;
      action?: string;
      name?: string;
      details?: string;
      explanation?: string;
    }>

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
    const stored = localStorage.getItem('lastTriggerTime')
    if (stored) {
      const time = parseInt(stored, 10)
      const COOLDOWN_MS = 5 * 60 * 1000
      const elapsed = Date.now() - time
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
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  
  const { isConnected: wsConnected } = useRealtimeMetrics({ 
    enabled: true,
    server: selectedServer
  });

  const config = useConfig();
  
  // Realtime alerts hook
  useRealtimeAlerts({
    enabled: true,
    onAlert: (alert) => {
        console.log('New Alert:', alert);
    }
  });

  useEffect(() => {
    fetchServers()
    fetchHealth()

    const interval = setInterval(() => {
        fetchHealth()
    }, 30000) // Poll health every 30s as backup

    const serverInterval = setInterval(() => {
        fetchServers()
    }, 60000)

    return () => {
      clearInterval(interval)
      clearInterval(serverInterval)
    }
  }, [])

  useEffect(() => {
    fetchLatestReport()
  }, [selectedServer])

  useEffect(() => {
    if (lastTriggerTime) {
      const COOLDOWN_MS = 5 * 60 * 1000
      const updateCooldown = () => {
        const remaining = COOLDOWN_MS - (Date.now() - lastTriggerTime)
        if (remaining <= 0) {
          setCooldownRemaining(0)
          setLastTriggerTime(null)
          localStorage.removeItem('lastTriggerTime')
        } else {
          setCooldownRemaining(remaining)
        }
      }
      updateCooldown()
      const interval = setInterval(updateCooldown, 1000)
      return () => clearInterval(interval)
    }
  }, [lastTriggerTime])

  const fetchServers = async () => {
    try {
      const res = await fetch('/api/servers')
      if (res.ok) {
        const data = await res.json()
        setServers(data.servers || [])
      }
      const infoRes = await fetch('/api/servers/info')
      if (infoRes.ok) {
        const infoData = await infoRes.json()
        setServerInfo(infoData.servers || {})
      }
    } catch (error) {
      console.error('Failed to fetch servers:', error)
    }
  }

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/health')
      if (res.ok) {
        const data = await res.json()
        setHealth(data)
      }
      setLoading(false)
    } catch (error) {
      console.error('Failed to fetch health:', error)
      setLoading(false)
      setHealth({ status: 'offline', service: 'AncientReport AI', version: '1.0.0' })
    }
  }

  const fetchLatestReport = async () => {
    try {
      setReportLoading(true)
      let url = '/api/reports/latest'
      if (selectedServer) url += `?hostname=${selectedServer}`
      
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        // Basic data structure validation for safety, though backend should ensure this
        if (data.report_id) {
          if (!data.top_processes) data.top_processes = { cpu: [], memory: [], disk_io: [], network: [], active_flows: [] }
          if (!Array.isArray(data.top_processes.cpu)) data.top_processes.cpu = []
          if (!Array.isArray(data.top_processes.memory)) data.top_processes.memory = []
          if (!Array.isArray(data.top_processes.disk_io)) data.top_processes.disk_io = []
          if (!Array.isArray(data.top_processes.network)) data.top_processes.network = []
          if (!Array.isArray(data.top_processes.active_flows)) data.top_processes.active_flows = []
          
          if (!data.ai_insights) data.ai_insights = { critical_alerts: [], recommendations: [], capacity_forecast: {}, config_optimizations: [] }
          if (!data.ai_insights.critical_alerts) data.ai_insights.critical_alerts = []
          else if (!Array.isArray(data.ai_insights.critical_alerts)) {
            data.ai_insights.critical_alerts = typeof data.ai_insights.critical_alerts === 'string' ? [data.ai_insights.critical_alerts] : []
          }
          data.ai_insights.critical_alerts = data.ai_insights.critical_alerts.filter((alert: any) => alert && String(alert).trim())
          
          setReport(data)
        }
      }
    } catch (error) {
      console.error('Failed to fetch report:', error)
    } finally {
      setReportLoading(false)
    }
  }

  const triggerAnalysis = async () => {
    if (cooldownRemaining > 0 || isTriggering) return

    try {
      setIsTriggering(true)
      setReportLoading(true)
      
      const now = Date.now()
      setLastTriggerTime(now)
      setCooldownRemaining(5 * 60 * 1000)
      localStorage.setItem('lastTriggerTime', now.toString())

      const res = await fetch('/api/analysis/trigger/hourly', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            source: 'manual_trigger',
            hostname: selectedServer // Trigger for specific server if selected
        })
      })

      if (res.ok) {
        // Wait a bit for processing then fetch
        setTimeout(() => {
            fetchLatestReport()
            setIsTriggering(false)
        }, 5000)
      } else {
        setIsTriggering(false)
      }
    } catch (error) {
      console.error('Analysis trigger error:', error)
      setIsTriggering(false)
      setReportLoading(false)
    }
  }

  const formatCooldownTime = (ms: number) => {
    const totalSeconds = Math.ceil(ms / 1000)
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  // Dashboard context to pass to pages
  const dashboardContext = {
    report,
    health,
    loading,
    isTriggering,
    cooldownRemaining,
    selectedServer,
    servers,
    serverInfo,
    triggerAnalysis,
    formatCooldownTime,
    config
  };

  // Header Component (rendered inside App to access state)
  const Header = (
    <header className="sticky top-0 left-0 right-0 z-20 glass-header border-b border-white/10 backdrop-blur-md bg-deep/80">
        <div className="px-6 h-16 flex items-center justify-between">
            {/* Left side usually empty or Breadcrumbs if needed, but we have Sidebar Logo */}
            <div className="flex items-center gap-4">
               {/* Mobile toggle could go here if not in Sidebar */}
            </div>

            <div className="flex items-center gap-4 md:gap-6">
              <ServerSelector 
                servers={servers}
                selectedServer={selectedServer}
                onServerChange={setSelectedServer}
              />
              
              <div className="hidden md:block h-8 w-px bg-white/10" />
              
              <AlertCenter />
              
              <button
                onClick={() => setIsSettingsOpen(true)}
                className="p-2 hover:bg-white/5 rounded-lg transition-colors group"
                title="Settings"
              >
                <Settings className="w-5 h-5 text-gray-400 group-hover:text-neon-blue transition-colors" />
              </button>
              
              <div className="hidden md:flex items-center gap-2">
                  <Badge 
                    variant={wsConnected ? 'success' : 'neutral'} 
                    pulse={wsConnected}
                    className="font-mono text-xs"
                  >
                    {wsConnected ? 'LIVE' : 'POLLING'}
                  </Badge>
                  
                  <div className="flex items-center gap-2 font-mono text-xs text-gray-400 pl-2 border-l border-white/10">
                    <div className={`w-1.5 h-1.5 rounded-full ${health?.status === 'running' ? 'bg-neon-green shadow-[0_0_8px_rgba(10,255,104,0.5)]' : 'bg-neon-red'}`} />
                    <span className="hidden lg:inline">{loading ? '...' : (health?.status?.toUpperCase() || 'OFF')}</span>
                  </div>
              </div>
            </div>
        </div>
      </header>
  );

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-deep text-white selection:bg-neon-blue/30 selection:text-neon-blue font-sans">
        <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
        
        <Routes>
            <Route element={
                <DashboardLayout header={Header} outletContext={dashboardContext} />
            }>
                <Route index element={<DashboardHome />} />
                <Route path="infrastructure" element={<Infrastructure />} />
                <Route path="observability" element={<Observability />} />
                <Route path="security" element={<Security />} />
                <Route path="analysis" element={<Analysis />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="dashboards" element={<Dashboards />} />
                <Route path="dashboards/:id" element={<DashboardView />} />
                <Route path="alerts" element={<Alerts />} />
                <Route path="recording-rules" element={<RecordingRules />} />
                <Route path="snmp" element={<SNMPMonitoring />} />
                <Route path="system-health" element={<SystemHealth />} />
                <Route path="prometheus-discovery" element={<PrometheusDiscovery />} />
                <Route path="ai-intelligence" element={<AIIntelligence />} />
            </Route>
        </Routes>
        
        {/* Global Components */}
        <AIChat />
      </div>
    </BrowserRouter>
  )
}

export default App
