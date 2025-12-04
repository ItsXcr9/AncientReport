import { useState, useEffect } from 'react';
import './CustomMonitors.css';

interface Monitor {
  id: string;
  name: string;
  type: 'port' | 'http' | 'process' | 'script';
  config: any;
  interval_seconds: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface MonitorResult {
  timestamp: string;
  status: 'ok' | 'warning' | 'critical' | 'unknown';
  latency_ms: number;
  response?: string;
  error?: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8800';

export default function CustomMonitors() {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedType, setSelectedType] = useState<'port' | 'http'>('port');
  const [formData, setFormData] = useState({
    name: '',
    host: '',
    port: 80,
    url: '',
    timeout_ms: 5000,
    interval_seconds: 60,
  });

  useEffect(() => {
    fetchMonitors();
  }, []);

  const fetchMonitors = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v3/monitors`);
      if (response.ok) {
        const data = await response.json();
        setMonitors(data);
      }
    } catch (error) {
      console.error('Failed to fetch monitors:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddMonitor = async () => {
    try {
      const config = selectedType === 'port' 
        ? { host: formData.host, port: formData.port, timeout_ms: formData.timeout_ms }
        : { url: formData.url, timeout_ms: formData.timeout_ms };

      const response = await fetch(`${API_BASE}/api/v3/monitors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          type: selectedType,
          config,
          interval_seconds: formData.interval_seconds,
          enabled: true,
        }),
      });

      if (response.ok) {
        setShowAddModal(false);
        setFormData({ name: '', host: '', port: 80, url: '', timeout_ms: 5000, interval_seconds: 60 });
        fetchMonitors();
      }
    } catch (error) {
      console.error('Failed to add monitor:', error);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/v3/monitors/${id}/toggle`, { method: 'POST' });
      fetchMonitors();
    } catch (error) {
      console.error('Failed to toggle monitor:', error);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this monitor?')) return;
    try {
      await fetch(`${API_BASE}/api/v3/monitors/${id}`, { method: 'DELETE' });
      fetchMonitors();
    } catch (error) {
      console.error('Failed to delete monitor:', error);
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'ok': return '#22c55e';
      case 'warning': return '#f59e0b';
      case 'critical': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'port': return '🔌';
      case 'http': return '🌐';
      case 'process': return '⚙️';
      case 'script': return '📜';
      default: return '📊';
    }
  };

  if (loading) {
    return <div className="monitors-loading">Loading monitors...</div>;
  }

  return (
    <div className="custom-monitors">
      <div className="monitors-header">
        <h2>🔍 Custom Monitors</h2>
        <button className="add-btn" onClick={() => setShowAddModal(true)}>
          + Add Monitor
        </button>
      </div>

      {monitors.length === 0 ? (
        <div className="monitors-empty">
          <p>No custom monitors configured yet.</p>
          <p>Add a port or HTTP monitor to get started!</p>
        </div>
      ) : (
        <div className="monitors-grid">
          {monitors.map((monitor) => (
            <div key={monitor.id} className={`monitor-card ${monitor.enabled ? '' : 'disabled'}`}>
              <div className="monitor-header">
                <span className="monitor-icon">{getTypeIcon(monitor.type)}</span>
                <span className="monitor-name">{monitor.name}</span>
                <span className="monitor-type">{monitor.type.toUpperCase()}</span>
              </div>
              <div className="monitor-config">
                {monitor.type === 'port' && (
                  <span>{monitor.config.host}:{monitor.config.port}</span>
                )}
                {monitor.type === 'http' && (
                  <span className="monitor-url">{monitor.config.url}</span>
                )}
              </div>
              <div className="monitor-meta">
                <span>Every {monitor.interval_seconds}s</span>
                <span>Timeout: {monitor.config.timeout_ms}ms</span>
              </div>
              <div className="monitor-actions">
                <button 
                  className={`toggle-btn ${monitor.enabled ? 'enabled' : 'disabled'}`}
                  onClick={() => handleToggle(monitor.id)}
                >
                  {monitor.enabled ? '✓ Enabled' : '○ Disabled'}
                </button>
                <button className="delete-btn" onClick={() => handleDelete(monitor.id)}>
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Monitor Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Add Custom Monitor</h3>
            
            <div className="form-group">
              <label>Monitor Type</label>
              <div className="type-selector">
                <button 
                  className={selectedType === 'port' ? 'active' : ''}
                  onClick={() => setSelectedType('port')}
                >
                  🔌 Port
                </button>
                <button 
                  className={selectedType === 'http' ? 'active' : ''}
                  onClick={() => setSelectedType('http')}
                >
                  🌐 HTTP
                </button>
              </div>
            </div>

            <div className="form-group">
              <label>Name</label>
              <input 
                type="text" 
                value={formData.name}
                onChange={(e) => setFormData({...formData, name: e.target.value})}
                placeholder="e.g., Database Port, API Health"
              />
            </div>

            {selectedType === 'port' ? (
              <>
                <div className="form-group">
                  <label>Host</label>
                  <input 
                    type="text" 
                    value={formData.host}
                    onChange={(e) => setFormData({...formData, host: e.target.value})}
                    placeholder="e.g., localhost, 192.168.1.1"
                  />
                </div>
                <div className="form-group">
                  <label>Port</label>
                  <input 
                    type="number" 
                    value={formData.port}
                    onChange={(e) => setFormData({...formData, port: parseInt(e.target.value)})}
                    min="1" max="65535"
                  />
                </div>
              </>
            ) : (
              <div className="form-group">
                <label>URL</label>
                <input 
                  type="text" 
                  value={formData.url}
                  onChange={(e) => setFormData({...formData, url: e.target.value})}
                  placeholder="https://example.com/health"
                />
              </div>
            )}

            <div className="form-row">
              <div className="form-group">
                <label>Timeout (ms)</label>
                <input 
                  type="number" 
                  value={formData.timeout_ms}
                  onChange={(e) => setFormData({...formData, timeout_ms: parseInt(e.target.value)})}
                  min="100" max="60000"
                />
              </div>
              <div className="form-group">
                <label>Interval (s)</label>
                <input 
                  type="number" 
                  value={formData.interval_seconds}
                  onChange={(e) => setFormData({...formData, interval_seconds: parseInt(e.target.value)})}
                  min="10" max="3600"
                />
              </div>
            </div>

            <div className="modal-actions">
              <button className="cancel-btn" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button className="save-btn" onClick={handleAddMonitor}>
                Add Monitor
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
