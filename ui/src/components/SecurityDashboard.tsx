import { useState, useEffect } from 'react';
import './SecurityDashboard.css';

interface SecurityScan {
  hostname: string;
  target: string;
  timestamp: string;
  open_ports: OpenPort[];
  risky_ports: OpenPort[];
  risk_score: number;
}

interface OpenPort {
  port: number;
  protocol: string;
  service?: string;
  state: string;
  is_risky: boolean;
  risk_reason?: string;
}

interface SecurityEvent {
  timestamp: string;
  hostname: string;
  event_type: string;
  severity: 'info' | 'warning' | 'critical';
  description: string;
  resolved: boolean;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8800';

export default function SecurityDashboard() {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState({
    overall_score: 0,
    hosts_scanned: 0,
    total_open_ports: 0,
    risky_ports_count: 0,
    active_threats: 0,
  });
  const [latestScan, setLatestScan] = useState<SecurityScan | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);

  useEffect(() => {
    fetchSecurityData();
  }, []);

  const fetchSecurityData = async () => {
    try {
      const [dashboardRes, scanRes, eventsRes] = await Promise.all([
        fetch(`${API_BASE}/api/v3/security/dashboard`),
        fetch(`${API_BASE}/api/v3/security/scans/latest`),
        fetch(`${API_BASE}/api/v3/security/events?limit=10`),
      ]);

      if (dashboardRes.ok) {
        setDashboard(await dashboardRes.json());
      }
      if (scanRes.ok) {
        const data = await scanRes.json();
        if (data) setLatestScan(data);
      }
      if (eventsRes.ok) {
        setEvents(await eventsRes.json());
      }
    } catch (error) {
      console.error('Failed to fetch security data:', error);
    } finally {
      setLoading(false);
    }
  };

  const triggerScan = async () => {
    try {
      await fetch(`${API_BASE}/api/v3/security/scans/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_type: 'port', target: '127.0.0.1' }),
      });
      // Refresh after a delay to allow scan to complete
      setTimeout(fetchSecurityData, 5000);
    } catch (error) {
      console.error('Failed to trigger scan:', error);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return '#22c55e';
    if (score >= 60) return '#f59e0b';
    return '#ef4444';
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return '#ef4444';
      case 'warning': return '#f59e0b';
      default: return '#3b82f6';
    }
  };

  if (loading) {
    return <div className="security-loading">Loading security data...</div>;
  }

  return (
    <div className="security-dashboard">
      <div className="security-header">
        <h2>🛡️ Security Dashboard</h2>
        <button className="scan-btn" onClick={triggerScan}>
          🔍 Run Scan
        </button>
      </div>

      {/* Score & Summary */}
      <div className="security-summary">
        <div className="score-card">
          <div 
            className="score-circle"
            style={{ 
              background: `conic-gradient(${getScoreColor(dashboard.overall_score)} ${dashboard.overall_score}%, #1e293b ${dashboard.overall_score}%)`
            }}
          >
            <div className="score-inner">
              <span className="score-value">{dashboard.overall_score}</span>
              <span className="score-label">Score</span>
            </div>
          </div>
        </div>

        <div className="stat-cards">
          <div className="stat-card">
            <span className="stat-icon">🖥️</span>
            <span className="stat-value">{dashboard.hosts_scanned}</span>
            <span className="stat-label">Hosts Scanned</span>
          </div>
          <div className="stat-card">
            <span className="stat-icon">🔌</span>
            <span className="stat-value">{dashboard.total_open_ports}</span>
            <span className="stat-label">Open Ports</span>
          </div>
          <div className="stat-card risky">
            <span className="stat-icon">⚠️</span>
            <span className="stat-value">{dashboard.risky_ports_count}</span>
            <span className="stat-label">Risky Ports</span>
          </div>
          <div className="stat-card threats">
            <span className="stat-icon">🚨</span>
            <span className="stat-value">{dashboard.active_threats}</span>
            <span className="stat-label">Active Threats</span>
          </div>
        </div>
      </div>

      {/* Open Ports */}
      <div className="security-section">
        <h3>Open Ports</h3>
        {latestScan && latestScan.open_ports.length > 0 ? (
          <div className="ports-grid">
            {latestScan.open_ports.map((port, idx) => (
              <div key={idx} className={`port-card ${port.is_risky ? 'risky' : ''}`}>
                <span className="port-number">{port.port}</span>
                <span className="port-service">{port.service || 'Unknown'}</span>
                <span className="port-protocol">{port.protocol.toUpperCase()}</span>
                {port.is_risky && (
                  <span className="port-warning" title={port.risk_reason}>⚠️</span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="no-data">No port scan data available. Click "Run Scan" to start.</div>
        )}
      </div>

      {/* Recent Events */}
      <div className="security-section">
        <h3>Recent Security Events</h3>
        {events.length > 0 ? (
          <div className="events-list">
            {events.map((event, idx) => (
              <div key={idx} className={`event-item ${event.resolved ? 'resolved' : ''}`}>
                <div 
                  className="event-severity"
                  style={{ background: getSeverityColor(event.severity) }}
                />
                <div className="event-content">
                  <span className="event-type">{event.event_type.replace('_', ' ')}</span>
                  <span className="event-desc">{event.description}</span>
                </div>
                <span className="event-time">{new Date(event.timestamp).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="no-data">No security events recorded.</div>
        )}
      </div>
    </div>
  );
}
