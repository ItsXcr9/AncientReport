import { useState, useEffect, useCallback, ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Router, Server, Printer, Battery, Wifi, WifiOff,
  Plus, Trash2, RefreshCw, Search, X, AlertTriangle,
  Network, Activity, Zap, Signal, Check
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';

interface SNMPDevice {
  id: string;
  name: string;
  ip_address: string;
  snmp_version: string;
  port: number;
  device_type: string;
  vendor: string;
  model: string;
  sys_name: string;
  sys_location: string;
  enabled: boolean;
  poll_interval: number;
  status: string;
  sys_uptime: number;
  last_poll: string | null;
  last_success: string | null;
  error_message: string;
}

interface SNMPTemplate {
  id: string;
  name: string;
  vendor: string;
  device_type: string;
  description: string;
  icon: string;
  oids: any[];
}

interface SNMPTrap {
  id: string;
  timestamp: string;
  source_ip: string;
  device_name: string;
  trap_type: string;
  severity: string;
  message: string;
  acknowledged: boolean;
}

interface MetricData {
  timestamp: string;
  oid: string;
  oid_name: string;
  value: number;
  unit: string;
}

interface SNMPAlert {
  id: string;
  oid_name: string;
  condition: string;
  threshold: number;
  current_value: number;
  severity: string;
  message: string;
}

const deviceIcons: Record<string, ReactNode> = {
  router: <Router size={24} />,
  switch: <Network size={24} />,
  server: <Server size={24} />,
  printer: <Printer size={24} />,
  ups: <Battery size={24} />,
  firewall: <Zap size={24} />,
  kafka: <Activity size={24} />,
  database: <Activity size={24} />,
  linux: <Server size={24} />,
  unknown: <Server size={24} />
};

const statusColors: Record<string, string> = {
  up: 'text-green-400 bg-green-500/20',
  down: 'text-red-400 bg-red-500/20',
  degraded: 'text-amber-400 bg-amber-500/20',
  unknown: 'text-gray-400 bg-gray-500/20'
};

export default function SNMPMonitoring() {
  const [devices, setDevices] = useState<SNMPDevice[]>([]);
  const [templates, setTemplates] = useState<SNMPTemplate[]>([]);
  const [traps, setTraps] = useState<SNMPTrap[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDevice, setSelectedDevice] = useState<SNMPDevice | null>(null);
  const [deviceMetrics, setDeviceMetrics] = useState<MetricData[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addStep, setAddStep] = useState(1);
  const [testResult, setTestResult] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [alerts, setAlerts] = useState<SNMPAlert[]>([]);
  const [selectedMetricOid, setSelectedMetricOid] = useState<string>('all');

  // Form state for adding device
  const [formData, setFormData] = useState({
    name: '',
    ip_address: '',
    snmp_version: 'v2c',
    community: 'public',
    port: 161,
    device_type: 'server',
    poll_interval: 60,
    timeout_ms: 5000,
    // SNMPv3
    username: '',
    auth_protocol: '',
    auth_password: '',
    priv_protocol: '',
    priv_password: ''
  });

  // Fetch data
  const fetchDevices = useCallback(async () => {
    try {
      const res = await fetch('/api/snmp/devices');
      if (res.ok) {
        const data = await res.json();
        setDevices(data);
      }
    } catch (e) {
      console.error('Failed to fetch devices:', e);
    }
  }, []);

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await fetch('/api/snmp/templates');
      if (res.ok) {
        const data = await res.json();
        setTemplates(data);
      }
    } catch (e) {
      console.error('Failed to fetch templates:', e);
    }
  }, []);

  const fetchTraps = useCallback(async () => {
    try {
      const res = await fetch('/api/snmp/traps?hours=24&limit=50');
      if (res.ok) {
        const data = await res.json();
        setTraps(data.traps || []);
      }
    } catch (e) {
      console.error('Failed to fetch traps:', e);
    }
  }, []);

  const fetchDeviceMetrics = useCallback(async (deviceId: string) => {
    try {
      const res = await fetch(`/api/snmp/metrics/${deviceId}?hours=1`);
      if (res.ok) {
        const data = await res.json();
        setDeviceMetrics(data.metrics || []);
      }
    } catch (e) {
      console.error('Failed to fetch metrics:', e);
    }
  }, []);

  const fetchAlerts = useCallback(async (deviceId: string) => {
    try {
      const res = await fetch(`/api/snmp/alerts?device_id=${deviceId}`);
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts || []);
      }
    } catch (e) {
      console.error('Failed to fetch alerts:', e);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      await Promise.all([fetchDevices(), fetchTemplates(), fetchTraps()]);
      setLoading(false);
    };
    init();
    
    // Poll devices every 30 seconds
    const interval = setInterval(fetchDevices, 30000);
    return () => clearInterval(interval);
  }, [fetchDevices, fetchTemplates, fetchTraps]);

  useEffect(() => {
    if (selectedDevice) {
      fetchDeviceMetrics(selectedDevice.id);
      fetchAlerts(selectedDevice.id);
      const interval = setInterval(() => {
        fetchDeviceMetrics(selectedDevice.id);
        fetchAlerts(selectedDevice.id);
      }, 10000);
      return () => clearInterval(interval);
    }
  }, [selectedDevice, fetchDeviceMetrics, fetchAlerts]);

  // Test connection
  const testConnection = async () => {
    setTestResult({ testing: true });
    try {
      // Create temp device first, then test
      const res = await fetch('/api/snmp/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formData, enabled: false })
      });
      
      if (res.ok) {
        const { id } = await res.json();
        // Test it
        const testRes = await fetch(`/api/snmp/devices/${id}/test`, { method: 'POST' });
        const result = await testRes.json();
        
        if (result.success) {
          setTestResult({ success: true, data: result.system_info });
          // Keep the device but re-enable it
          await fetch(`/api/snmp/devices/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: true })
          });
        } else {
          setTestResult({ success: false, error: result.error });
          // Delete failed device
          await fetch(`/api/snmp/devices/${id}`, { method: 'DELETE' });
        }
      }
    } catch (e: any) {
      setTestResult({ success: false, error: e.message });
    }
  };

  // Add device
  const addDevice = async () => {
    try {
      const res = await fetch('/api/snmp/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      
      if (res.ok) {
        setShowAddModal(false);
        setAddStep(1);
        setTestResult(null);
        setFormData({
          name: '', ip_address: '', snmp_version: 'v2c', community: 'public',
          port: 161, device_type: 'server', poll_interval: 60, timeout_ms: 5000,
          username: '', auth_protocol: '', auth_password: '', priv_protocol: '', priv_password: ''
        });
        await fetchDevices();
      }
    } catch (e) {
      console.error('Failed to add device:', e);
    }
  };

  // Delete device
  const deleteDevice = async (id: string) => {
    if (!confirm('Delete this device and all its data?')) return;
    try {
      await fetch(`/api/snmp/devices/${id}`, { method: 'DELETE' });
      await fetchDevices();
      if (selectedDevice?.id === id) setSelectedDevice(null);
    } catch (e) {
      console.error('Failed to delete device:', e);
    }
  };

  // Poll device manually
  const pollDevice = async (id: string) => {
    try {
      await fetch(`/api/snmp/devices/${id}/poll`, { method: 'POST' });
      setTimeout(fetchDevices, 2000); // Refresh after poll
    } catch (e) {
      console.error('Failed to poll device:', e);
    }
  };

  // Apply template
  const applyTemplate = async (templateId: string, deviceId: string) => {
    try {
      await fetch(`/api/snmp/templates/${templateId}/apply/${deviceId}`, { method: 'POST' });
      await fetchDevices();
    } catch (e) {
      console.error('Failed to apply template:', e);
    }
  };

  // Format uptime
  const formatUptime = (seconds: number) => {
    if (!seconds) return 'Unknown';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  };

  // Filter devices
  const filteredDevices = devices.filter(d =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.ip_address.includes(searchQuery) ||
    d.device_type.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Stats
  const stats = {
    total: devices.length,
    up: devices.filter(d => d.status === 'up').length,
    down: devices.filter(d => d.status === 'down').length,
    unacknowledgedTraps: traps.filter(t => !t.acknowledged).length
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-neon-blue" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Network className="text-neon-blue" size={28} />
            SNMP Monitoring
          </h1>
          <p className="text-gray-400 mt-1">Monitor network devices, servers, and infrastructure</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 transition-colors"
        >
          <Plus size={18} />
          Add Device
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Devices', value: stats.total, icon: <Server size={20} />, color: 'text-blue-400' },
          { label: 'Online', value: stats.up, icon: <Wifi size={20} />, color: 'text-green-400' },
          { label: 'Offline', value: stats.down, icon: <WifiOff size={20} />, color: 'text-red-400' },
          { label: 'Active Traps', value: stats.unacknowledgedTraps, icon: <AlertTriangle size={20} />, color: 'text-amber-400' },
        ].map((stat, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="glass-card rounded-xl p-4"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-400 text-sm">{stat.label}</p>
                <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
              </div>
              <div className={stat.color}>{stat.icon}</div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Device List */}
        <div className="col-span-2 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500" size={18} />
            <input
              type="text"
              placeholder="Search devices..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
            />
          </div>

          {/* Device Cards */}
          <div className="col-span-2 grid grid-cols-2 gap-4 content-start">
          {filteredDevices.length === 0 ? (
              <div className="col-span-2 glass-card rounded-xl p-8 text-center">
                <Server className="mx-auto mb-4 text-gray-500" size={40} />
                <h3 className="text-lg font-semibold text-white mb-2">No Devices</h3>
                <p className="text-gray-400 mb-4">Add your first SNMP device to start monitoring</p>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-neon-blue text-black font-medium rounded-lg"
                >
                  <Plus size={18} />
                  Add Device
                </button>
              </div>
            ) : (
              filteredDevices.map((device) => (
                <motion.div
                  key={device.id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className={`glass-card rounded-xl p-4 cursor-pointer border transition-all ${
                    selectedDevice?.id === device.id 
                      ? 'border-neon-blue' 
                      : 'border-transparent hover:border-white/20'
                  }`}
                  onClick={() => setSelectedDevice(device)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${statusColors[device.status]}`}>
                        {deviceIcons[device.device_type] || deviceIcons.unknown}
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">{device.name}</h3>
                        <p className="text-sm text-gray-400">{device.ip_address}:{device.port}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); pollDevice(device.id); }}
                        className="p-1.5 text-gray-500 hover:text-white transition-colors"
                        title="Poll now"
                      >
                        <RefreshCw size={14} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteDevice(device.id); }}
                        className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div className="bg-white/5 rounded px-2 py-1">
                      <span className="text-gray-500">Type:</span>
                      <span className="text-white ml-1 capitalize">{device.device_type}</span>
                    </div>
                    <div className="bg-white/5 rounded px-2 py-1">
                      <span className="text-gray-500">SNMP:</span>
                      <span className="text-white ml-1">{device.snmp_version}</span>
                    </div>
                    <div className="bg-white/5 rounded px-2 py-1">
                      <span className="text-gray-500">Uptime:</span>
                      <span className="text-white ml-1">{formatUptime(device.sys_uptime)}</span>
                    </div>
                  </div>

                  {device.error_message && (
                    <div className="mt-2 text-xs text-red-400 bg-red-500/10 rounded px-2 py-1 truncate">
                      {device.error_message}
                    </div>
                  )}
                </motion.div>
              ))
            )}

          </div>
        </div>

        {/* Right Panel - Device Details or Traps */}
        <div className="space-y-4">
          {selectedDevice ? (
            <>
              {/* Device Details */}
              <div className="glass-card rounded-xl p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-white">{selectedDevice.name}</h3>
                  <button
                    onClick={() => setSelectedDevice(null)}
                    className="text-gray-500 hover:text-white"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="space-y-3 text-sm">
                  {[
                    { label: 'Status', value: selectedDevice.status, badge: true },
                    { label: 'IP Address', value: `${selectedDevice.ip_address}:${selectedDevice.port}` },
                    { label: 'System Name', value: selectedDevice.sys_name || 'N/A' },
                    { label: 'Location', value: selectedDevice.sys_location || 'N/A' },
                    { label: 'Vendor', value: selectedDevice.vendor || 'Unknown' },
                    { label: 'Uptime', value: formatUptime(selectedDevice.sys_uptime) },
                    { label: 'Last Poll', value: selectedDevice.last_poll ? new Date(selectedDevice.last_poll).toLocaleTimeString() : 'Never' },
                  ].map((item, i) => (
                    <div key={i} className="flex justify-between">
                      <span className="text-gray-500">{item.label}</span>
                      {item.badge ? (
                        <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${statusColors[item.value]}`}>
                          {item.value}
                        </span>
                      ) : (
                        <span className="text-white">{item.value}</span>
                      )}
                    </div>
                  ))}
                </div>

                {/* Apply Template */}
                <div className="mt-4 pt-4 border-t border-white/10">
                  <label className="text-sm text-gray-400 mb-2 block">Apply Template</label>
                  <select
                    onChange={(e) => { if (e.target.value) applyTemplate(e.target.value, selectedDevice.id); }}
                    defaultValue=""
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:border-neon-blue focus:outline-none"
                  >
                    <option value="">Select template...</option>
                    {templates.map(t => (
                      <option key={t.id} value={t.id}>{t.name} ({t.vendor})</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Kafka Specific Stats */}
              {(selectedDevice.device_type === 'kafka' || selectedDevice.name.toLowerCase().includes('kafka')) && (
                <div className="glass-card rounded-xl p-4">
                  <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
                    <Activity className="text-neon-blue" size={18} />
                    Kafka Consumer Lag
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                     <div className="bg-white/5 rounded p-3 text-center">
                        <div className="text-gray-400 text-xs mb-1">Total Lag</div>
                        <div className="text-2xl font-bold text-white">
                          {deviceMetrics.find(m => m.oid_name.includes('Lag'))?.value || 0}
                        </div>
                     </div>
                     <div className="bg-white/5 rounded p-3 text-center">
                        <div className="text-gray-400 text-xs mb-1">Active Consumers</div>
                        <div className="text-2xl font-bold text-neon-blue">3</div>
                     </div>
                  </div>
                </div>
              )}

              {/* Alerts Panel */}
              <div className="glass-card rounded-xl p-4">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-white flex items-center gap-2">
                      <AlertTriangle className={alerts.length > 0 ? "text-red-400" : "text-gray-400"} size={18} />
                      Active Alerts
                    </h3>
                    <button className="text-xs text-neon-blue hover:text-white">Configure</button>
                </div>
                {alerts.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-2">No active alerts</p>
                ) : (
                  <div className="space-y-2">
                    {alerts.map(alert => (
                      <div key={alert.id} className="bg-red-500/10 border border-red-500/20 rounded p-2 flex justify-between items-center">
                        <div>
                          <p className="text-sm text-red-300 font-medium">{alert.message || `${alert.oid_name} ${alert.condition} ${alert.threshold}`}</p>
                          <p className="text-xs text-red-400/60">{new Date().toLocaleTimeString()}</p>
                        </div>
                        <div className="text-xs font-bold text-red-500">{alert.current_value}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Metrics Chart */}
              {deviceMetrics.length > 0 && (
                <div className="glass-card rounded-xl p-4">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-white">Recent Metrics</h3>
                    <select 
                      className="bg-black/30 text-xs text-white border border-white/10 rounded px-2 py-1 outline-none focus:border-neon-blue"
                      value={selectedMetricOid}
                      onChange={(e) => setSelectedMetricOid(e.target.value)}
                    >
                      <option value="all">All Metrics</option>
                      {Array.from(new Set(deviceMetrics.map(m => m.oid_name))).map(name => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={deviceMetrics.slice(0, 100).reverse().filter(m => selectedMetricOid === 'all' || m.oid_name === selectedMetricOid)}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis 
                          dataKey="timestamp" 
                          stroke="#666"
                          tickFormatter={(t) => new Date(t).toLocaleTimeString().slice(0, 5)}
                          fontSize={10}
                        />
                        <YAxis stroke="#666" fontSize={10} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333' }}
                          labelFormatter={(t) => new Date(t).toLocaleTimeString()}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="value" 
                          stroke="#00f0ff" 
                          strokeWidth={2}
                          dot={false}
                          name={selectedMetricOid === 'all' ? undefined : selectedMetricOid}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Trap Feed */
            <div className="glass-card rounded-xl p-4">
              <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
                <AlertTriangle className="text-amber-400" size={18} />
                Recent Traps
              </h3>
              
              {traps.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-4">No traps received</p>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {traps.slice(0, 20).map((trap) => (
                    <div
                      key={trap.id}
                      className={`p-2 rounded-lg text-sm ${
                        trap.acknowledged ? 'bg-white/5' : 'bg-amber-500/10 border border-amber-500/20'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <span className={`font-medium ${
                            trap.severity === 'critical' ? 'text-red-400' :
                            trap.severity === 'major' ? 'text-orange-400' :
                            trap.severity === 'warning' ? 'text-amber-400' :
                            'text-gray-400'
                          }`}>
                            {trap.trap_type || trap.trap_oid}
                          </span>
                          <p className="text-gray-500 text-xs">{trap.source_ip}</p>
                        </div>
                        <span className="text-xs text-gray-500">
                          {new Date(trap.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      {trap.message && (
                        <p className="text-gray-400 text-xs mt-1 truncate">{trap.message}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Add Device Modal */}
      <AnimatePresence>
        {showAddModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
            onClick={() => setShowAddModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card rounded-xl p-6 w-full max-w-lg mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="text-xl font-bold text-white mb-4">Add SNMP Device</h2>

              {/* Step Indicators */}
              <div className="flex items-center gap-2 mb-6">
                {[1, 2, 3].map((step) => (
                  <div key={step} className="flex-1">
                    <div
                      className={`h-1 rounded-full transition-colors ${
                        addStep >= step ? 'bg-neon-blue' : 'bg-white/20'
                      }`}
                    />
                    <span className="text-xs text-gray-500 mt-1 block text-center">
                      {step === 1 ? 'Details' : step === 2 ? 'Test' : 'Confirm'}
                    </span>
                  </div>
                ))}
              </div>

              {/* Step 1: Basic Info */}
              {addStep === 1 && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">Device Name</label>
                      <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="Core Router"
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">IP Address</label>
                      <input
                        type="text"
                        value={formData.ip_address}
                        onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                        placeholder="192.168.1.1"
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">SNMP Version</label>
                      <select
                        value={formData.snmp_version}
                        onChange={(e) => setFormData({ ...formData, snmp_version: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                      >
                        <option value="v1">v1</option>
                        <option value="v2c">v2c</option>
                        <option value="v3">v3</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">Port</label>
                      <input
                        type="number"
                        value={formData.port}
                        onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">Device Type</label>
                      <select
                        value={formData.device_type}
                        onChange={(e) => setFormData({ ...formData, device_type: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                      >
                        <option value="router">Router</option>
                        <option value="switch">Switch</option>
                        <option value="server">Server</option>
                        <option value="firewall">Firewall</option>
                        <option value="printer">Printer</option>
                        <option value="ups">UPS</option>
                        <option value="unknown">Unknown</option>
                      </select>
                    </div>
                  </div>

                  {formData.snmp_version === 'v3' ? (
                    <div className="space-y-4 p-4 bg-white/5 rounded-lg">
                      <h4 className="text-sm font-medium text-white">SNMPv3 Credentials</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Username</label>
                          <input
                            type="text"
                            value={formData.username}
                            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:border-neon-blue focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Auth Protocol</label>
                          <select
                            value={formData.auth_protocol}
                            onChange={(e) => setFormData({ ...formData, auth_protocol: e.target.value })}
                            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:border-neon-blue focus:outline-none"
                          >
                            <option value="">None</option>
                            <option value="MD5">MD5</option>
                            <option value="SHA">SHA</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Auth Password</label>
                          <input
                            type="password"
                            value={formData.auth_password}
                            onChange={(e) => setFormData({ ...formData, auth_password: e.target.value })}
                            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:border-neon-blue focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Privacy Protocol</label>
                          <select
                            value={formData.priv_protocol}
                            onChange={(e) => setFormData({ ...formData, priv_protocol: e.target.value })}
                            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:border-neon-blue focus:outline-none"
                          >
                            <option value="">None</option>
                            <option value="DES">DES</option>
                            <option value="AES">AES</option>
                          </select>
                        </div>
                        {formData.priv_protocol && (
                          <div className="col-span-2">
                            <label className="block text-xs text-gray-400 mb-1">Privacy Password</label>
                            <input
                              type="password"
                              value={formData.priv_password}
                              onChange={(e) => setFormData({ ...formData, priv_password: e.target.value })}
                              className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm focus:border-neon-blue focus:outline-none"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-sm text-gray-300 mb-1">Community String</label>
                      <input
                        type="text"
                        value={formData.community}
                        onChange={(e) => setFormData({ ...formData, community: e.target.value })}
                        placeholder="public"
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:border-neon-blue focus:outline-none"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Step 2: Test Connection */}
              {addStep === 2 && (
                <div className="space-y-4">
                  <div className="text-center py-4">
                    {testResult?.testing ? (
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-neon-blue mx-auto" />
                    ) : testResult?.success ? (
                      <div className="text-green-400">
                        <Check size={48} className="mx-auto mb-2" />
                        <p className="font-semibold">Connection Successful!</p>
                      </div>
                    ) : testResult?.error ? (
                      <div className="text-red-400">
                        <X size={48} className="mx-auto mb-2" />
                        <p className="font-semibold">Connection Failed</p>
                        <p className="text-sm text-gray-400 mt-2">{testResult.error}</p>
                      </div>
                    ) : (
                      <div className="text-gray-400">
                        <Signal size={48} className="mx-auto mb-2" />
                        <p>Ready to test connection</p>
                      </div>
                    )}
                  </div>

                  {testResult?.success && testResult.data && (
                    <div className="bg-white/5 rounded-lg p-3 text-sm">
                      <h4 className="text-white font-medium mb-2">Detected System Info:</h4>
                      <pre className="text-gray-400 text-xs overflow-x-auto">
                        {JSON.stringify(testResult.data, null, 2)}
                      </pre>
                    </div>
                  )}

                  <button
                    onClick={testConnection}
                    disabled={testResult?.testing}
                    className="w-full px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 disabled:opacity-50"
                  >
                    {testResult?.testing ? 'Testing...' : 'Test Connection'}
                  </button>
                </div>
              )}

              {/* Step 3: Confirm */}
              {addStep === 3 && (
                <div className="space-y-4">
                  <div className="bg-white/5 rounded-lg p-4">
                    <h4 className="text-white font-medium mb-3">Device Summary</h4>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="text-gray-500">Name:</div>
                      <div className="text-white">{formData.name}</div>
                      <div className="text-gray-500">IP Address:</div>
                      <div className="text-white">{formData.ip_address}:{formData.port}</div>
                      <div className="text-gray-500">SNMP Version:</div>
                      <div className="text-white">{formData.snmp_version}</div>
                      <div className="text-gray-500">Device Type:</div>
                      <div className="text-white capitalize">{formData.device_type}</div>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1">Apply Template (optional)</label>
                    <select
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:border-neon-blue focus:outline-none"
                    >
                      <option value="">No template</option>
                      {templates.filter(t => 
                        t.device_type === formData.device_type || !formData.device_type
                      ).map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* Navigation */}
              <div className="flex justify-between mt-6 pt-4 border-t border-white/10">
                <button
                  onClick={() => {
                    if (addStep === 1) {
                      setShowAddModal(false);
                    } else {
                      setAddStep(addStep - 1);
                    }
                  }}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                >
                  {addStep === 1 ? 'Cancel' : 'Back'}
                </button>
                <button
                  onClick={() => {
                    if (addStep < 3) {
                      setAddStep(addStep + 1);
                    } else {
                      addDevice();
                    }
                  }}
                  disabled={!formData.name || !formData.ip_address}
                  className="px-4 py-2 bg-neon-blue text-black font-medium rounded-lg hover:bg-neon-blue/90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {addStep === 3 ? 'Add Device' : 'Next'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
