import { useState, useEffect, FormEvent } from 'react';
import { Settings, X, Save, Loader2, Bell, BellOff, Key, Activity, Globe, Plug, Trash2, Plus, Check, AlertTriangle, Clock, Zap } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSettings } from '../hooks/useSettings';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface CustomMonitor {
  id: string;
  name: string;
  type: 'port' | 'http';
  config: {
    host?: string;
    port?: number;
    url?: string;
    timeout_ms: number;
    expected_status?: number[];
  };
  interval_seconds: number;
  enabled: boolean;
}

const API_BASE = '';

type TabType = 'general' | 'monitors' | 'alerts';

export const SettingsModal = ({ isOpen, onClose }: SettingsModalProps) => {
  const { settings, loading, updateSettings, updating } = useSettings();
  const [activeTab, setActiveTab] = useState<TabType>('general');
  
  // General settings form
  const [formData, setFormData] = useState({
    telegram_bot_token: '',
    telegram_chat_id: '',
    telegram_alerts_enabled: 'true',
    gemini_api_key: '',
  });

  // Custom monitors
  const [monitors, setMonitors] = useState<CustomMonitor[]>([]);
  const [monitorsLoading, setMonitorsLoading] = useState(false);
  const [showAddMonitor, setShowAddMonitor] = useState(false);
  const [newMonitor, setNewMonitor] = useState({
    name: '',
    type: 'port' as 'port' | 'http',
    host: 'localhost',
    port: 80,
    url: 'https://example.com/health',
    timeout_ms: 5000,
    interval_seconds: 60,
  });

  const [showSuccess, setShowSuccess] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  // Load settings
  useEffect(() => {
    if (settings) {
      setFormData({
        telegram_bot_token: settings.telegram_bot_token || '',
        telegram_chat_id: settings.telegram_chat_id || '',
        telegram_alerts_enabled: settings.telegram_alerts_enabled || 'true',
        gemini_api_key: settings.gemini_api_key || '',
      });
    }
  }, [settings]);

  // Load monitors when tab changes
  useEffect(() => {
    if (isOpen && activeTab === 'monitors') {
      fetchMonitors();
    }
  }, [isOpen, activeTab]);

  const fetchMonitors = async () => {
    setMonitorsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/v3/monitors`);
      if (response.ok) {
        const data = await response.json();
        setMonitors(data);
      }
    } catch (error) {
      console.error('Failed to fetch monitors:', error);
    } finally {
      setMonitorsLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await updateSettings(formData);
      showSuccessNotification('Settings saved successfully!');
    } catch (error) {
      console.error('Failed to save settings:', error);
    }
  };

  const showSuccessNotification = (message: string) => {
    setSuccessMessage(message);
    setShowSuccess(true);
    setTimeout(() => setShowSuccess(false), 3000);
  };

  const toggleAlerts = () => {
    setFormData({
      ...formData,
      telegram_alerts_enabled: formData.telegram_alerts_enabled === 'true' ? 'false' : 'true',
    });
  };

  const addMonitor = async () => {
    try {
      const config = newMonitor.type === 'port'
        ? { host: newMonitor.host, port: newMonitor.port, timeout_ms: newMonitor.timeout_ms }
        : { url: newMonitor.url, timeout_ms: newMonitor.timeout_ms, expected_status: [200, 201, 204] };

      const response = await fetch(`${API_BASE}/api/v3/monitors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newMonitor.name,
          type: newMonitor.type,
          config,
          interval_seconds: newMonitor.interval_seconds,
          enabled: true,
        }),
      });

      if (response.ok) {
        setShowAddMonitor(false);
        setNewMonitor({
          name: '',
          type: 'port',
          host: 'localhost',
          port: 80,
          url: 'https://example.com/health',
          timeout_ms: 5000,
          interval_seconds: 60,
        });
        fetchMonitors();
        showSuccessNotification('Monitor added successfully!');
      }
    } catch (error) {
      console.error('Failed to add monitor:', error);
    }
  };

  const toggleMonitor = async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/v3/monitors/${id}/toggle`, { method: 'POST' });
      fetchMonitors();
    } catch (error) {
      console.error('Failed to toggle monitor:', error);
    }
  };

  const deleteMonitor = async (id: string) => {
    if (!confirm('Delete this monitor?')) return;
    try {
      await fetch(`${API_BASE}/api/v3/monitors/${id}`, { method: 'DELETE' });
      fetchMonitors();
      showSuccessNotification('Monitor deleted!');
    } catch (error) {
      console.error('Failed to delete monitor:', error);
    }
  };

  if (!isOpen) return null;

  const tabs = [
    { id: 'general' as TabType, label: 'General', icon: Settings },
    { id: 'monitors' as TabType, label: 'Custom Monitors', icon: Activity },
    { id: 'alerts' as TabType, label: 'Alert Rules', icon: Bell },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="relative glass-card-intense rounded-xl w-full max-w-3xl max-h-[90vh] overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-neon-blue/10 rounded-lg">
              <Settings className="w-5 h-5 text-neon-blue" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-display text-white">Settings</h2>
              <p className="text-sm text-gray-400">Configure monitoring, alerts, and integrations</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-white/10 px-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-all border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'text-neon-blue border-neon-blue'
                  : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-240px)]">
          {/* Success Notification */}
          <AnimatePresence>
            {showSuccess && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="mb-4 p-3 bg-neon-green/10 border border-neon-green/20 rounded-lg text-neon-green flex items-center gap-2"
              >
                <Check className="w-4 h-4" />
                <span className="text-sm font-medium">{successMessage}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* General Tab */}
          {activeTab === 'general' && (
            <div className="space-y-6">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-neon-blue" />
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-6">
                  {/* Telegram Settings */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                        <Bell className="w-5 h-5 text-neon-purple" />
                        Telegram Notifications
                      </h3>
                      <button
                        type="button"
                        onClick={toggleAlerts}
                        className={`px-4 py-2 rounded-lg font-medium text-sm transition-all flex items-center gap-2 ${
                          formData.telegram_alerts_enabled === 'true'
                            ? 'bg-neon-green/10 text-neon-green border border-neon-green/20'
                            : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
                        }`}
                      >
                        {formData.telegram_alerts_enabled === 'true' ? (
                          <>
                            <Bell className="w-4 h-4" />
                            Enabled
                          </>
                        ) : (
                          <>
                            <BellOff className="w-4 h-4" />
                            Disabled
                          </>
                        )}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Bot Token
                        </label>
                        <input
                          type="text"
                          value={formData.telegram_bot_token}
                          onChange={(e) => setFormData({ ...formData, telegram_bot_token: e.target.value })}
                          placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                          className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 focus:ring-1 focus:ring-neon-blue/50 transition-colors font-mono text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Chat ID
                        </label>
                        <input
                          type="text"
                          value={formData.telegram_chat_id}
                          onChange={(e) => setFormData({ ...formData, telegram_chat_id: e.target.value })}
                          placeholder="123456789"
                          className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 focus:ring-1 focus:ring-neon-blue/50 transition-colors font-mono text-sm"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="border-t border-white/10" />

                  {/* Gemini AI Settings */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                      <Key className="w-5 h-5 text-neon-blue" />
                      Gemini AI Integration
                    </h3>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        API Key
                      </label>
                      <input
                        type="password"
                        value={formData.gemini_api_key}
                        onChange={(e) => setFormData({ ...formData, gemini_api_key: e.target.value })}
                        placeholder="AIzaSy..."
                        className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 focus:ring-1 focus:ring-neon-blue/50 transition-colors font-mono text-sm"
                      />
                      <p className="text-xs text-gray-500 mt-1">Get your API key from Google AI Studio</p>
                    </div>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Monitors Tab */}
          {activeTab === 'monitors' && (
            <div className="space-y-4">
              {/* Header with Add Button */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-white">Custom Monitors</h3>
                  <p className="text-sm text-gray-400">Monitor ports, HTTP endpoints, and services</p>
                </div>
                <button
                  onClick={() => setShowAddMonitor(!showAddMonitor)}
                  className="px-4 py-2 bg-neon-blue/10 text-neon-blue border border-neon-blue/20 rounded-lg font-medium text-sm transition-all hover:bg-neon-blue/20 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Add Monitor
                </button>
              </div>

              {/* Add Monitor Form */}
              <AnimatePresence>
                {showAddMonitor && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="p-4 bg-white/5 border border-white/10 rounded-lg space-y-4"
                  >
                    <div className="flex gap-4">
                      <div className="flex-1">
                        <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
                        <input
                          type="text"
                          value={newMonitor.name}
                          onChange={(e) => setNewMonitor({ ...newMonitor, name: e.target.value })}
                          placeholder="e.g., Database, API Health"
                          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Type</label>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setNewMonitor({ ...newMonitor, type: 'port' })}
                            className={`px-3 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                              newMonitor.type === 'port'
                                ? 'bg-neon-purple/20 text-neon-purple border border-neon-purple/30'
                                : 'bg-white/5 text-gray-400 border border-white/10'
                            }`}
                          >
                            <Plug className="w-4 h-4" />
                            Port
                          </button>
                          <button
                            type="button"
                            onClick={() => setNewMonitor({ ...newMonitor, type: 'http' })}
                            className={`px-3 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                              newMonitor.type === 'http'
                                ? 'bg-neon-blue/20 text-neon-blue border border-neon-blue/30'
                                : 'bg-white/5 text-gray-400 border border-white/10'
                            }`}
                          >
                            <Globe className="w-4 h-4" />
                            HTTP
                          </button>
                        </div>
                      </div>
                    </div>

                    {newMonitor.type === 'port' ? (
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-2">Host</label>
                          <input
                            type="text"
                            value={newMonitor.host}
                            onChange={(e) => setNewMonitor({ ...newMonitor, host: e.target.value })}
                            placeholder="localhost"
                            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 text-sm font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-2">Port</label>
                          <input
                            type="number"
                            value={newMonitor.port}
                            onChange={(e) => setNewMonitor({ ...newMonitor, port: parseInt(e.target.value) })}
                            min="1"
                            max="65535"
                            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 text-sm font-mono"
                          />
                        </div>
                      </div>
                    ) : (
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">URL</label>
                        <input
                          type="text"
                          value={newMonitor.url}
                          onChange={(e) => setNewMonitor({ ...newMonitor, url: e.target.value })}
                          placeholder="https://api.example.com/health"
                          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 text-sm font-mono"
                        />
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          <Clock className="w-3 h-3 inline mr-1" />
                          Check Interval (seconds)
                        </label>
                        <input
                          type="number"
                          value={newMonitor.interval_seconds}
                          onChange={(e) => setNewMonitor({ ...newMonitor, interval_seconds: parseInt(e.target.value) })}
                          min="10"
                          max="3600"
                          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          <Zap className="w-3 h-3 inline mr-1" />
                          Timeout (ms)
                        </label>
                        <input
                          type="number"
                          value={newMonitor.timeout_ms}
                          onChange={(e) => setNewMonitor({ ...newMonitor, timeout_ms: parseInt(e.target.value) })}
                          min="100"
                          max="60000"
                          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 text-sm"
                        />
                      </div>
                    </div>

                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setShowAddMonitor(false)}
                        className="px-4 py-2 text-gray-400 hover:bg-white/5 rounded-lg transition-colors text-sm"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={addMonitor}
                        disabled={!newMonitor.name}
                        className="px-4 py-2 bg-neon-green/10 text-neon-green border border-neon-green/20 rounded-lg font-medium text-sm transition-all hover:bg-neon-green/20 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Plus className="w-4 h-4" />
                        Add Monitor
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Monitors List */}
              {monitorsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-neon-blue" />
                </div>
              ) : monitors.length === 0 ? (
                <div className="text-center py-12">
                  <Activity className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                  <p className="text-gray-400">No custom monitors configured</p>
                  <p className="text-sm text-gray-500 mt-1">Click "Add Monitor" to create your first monitor</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {monitors.map((monitor) => (
                    <motion.div
                      key={monitor.id}
                      layout
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className={`p-4 rounded-lg border transition-all ${
                        monitor.enabled
                          ? 'bg-white/5 border-white/10'
                          : 'bg-white/2 border-white/5 opacity-60'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${
                            monitor.type === 'port' ? 'bg-neon-purple/10' : 'bg-neon-blue/10'
                          }`}>
                            {monitor.type === 'port' ? (
                              <Plug className={`w-4 h-4 ${monitor.type === 'port' ? 'text-neon-purple' : 'text-neon-blue'}`} />
                            ) : (
                              <Globe className="w-4 h-4 text-neon-blue" />
                            )}
                          </div>
                          <div>
                            <div className="font-medium text-white">{monitor.name}</div>
                            <div className="text-xs text-gray-400 font-mono">
                              {monitor.type === 'port' 
                                ? `${monitor.config.host}:${monitor.config.port}`
                                : monitor.config.url
                              }
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">
                            Every {monitor.interval_seconds}s
                          </span>
                          <button
                            onClick={() => toggleMonitor(monitor.id)}
                            className={`px-3 py-1 rounded text-xs font-medium transition-all ${
                              monitor.enabled
                                ? 'bg-neon-green/10 text-neon-green'
                                : 'bg-gray-500/10 text-gray-400'
                            }`}
                          >
                            {monitor.enabled ? '✓ Active' : 'Paused'}
                          </button>
                          <button
                            onClick={() => deleteMonitor(monitor.id)}
                            className="p-1 hover:bg-red-500/10 rounded transition-colors text-gray-400 hover:text-red-400"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Alerts Tab */}
          {activeTab === 'alerts' && (
            <div className="text-center py-12">
              <AlertTriangle className="w-12 h-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">Alert Rules configuration</p>
              <p className="text-sm text-gray-500 mt-1">Coming soon - Configure custom alert thresholds</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-white/10">
          <button
            type="button"
            onClick={onClose}
            disabled={updating}
            className="px-4 py-2 rounded-lg text-gray-400 hover:bg-white/5 transition-colors font-medium"
          >
            Close
          </button>
          {activeTab === 'general' && (
            <button
              onClick={handleSubmit}
              disabled={updating}
              className={`px-6 py-2 rounded-lg font-medium flex items-center gap-2 transition-all ${
                updating
                  ? 'bg-white/5 text-gray-500 cursor-not-allowed'
                  : 'bg-neon-blue text-white hover:bg-neon-blue/80 hover:shadow-[0_0_15px_rgba(0,243,255,0.3)]'
              }`}
            >
              {updating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Changes
                </>
              )}
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
};
