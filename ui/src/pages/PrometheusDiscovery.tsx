import React, { useState, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Server,
  Search,
  RefreshCw,
  TrendingUp,
  Clock,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  BarChart3,
  Database
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

const API_BASE = import.meta.env.VITE_API_URL || 'http://65.109.200.75:6800';

interface Exporter {
  hostname: string;
  exporter_type: string;
  scrape_target: string;
  metric_count: number;
  last_seen: string;
  first_seen: string;
  status: 'up' | 'down';
}

interface Metric {
  hostname: string;
  category: string;
  metric_name: string;
  metric_type: string;
  sample_count: number;
  avg_value: number;
  min_value: number;
  max_value: number;
  last_seen: string;
}

interface Category {
  category: string;
  metric_count: number;
  host_count: number;
  last_seen: string;
}

// Exporter type icons and colors
const exporterConfig: Record<string, { icon: string; color: string; label: string }> = {
  node_exporter: { icon: '🖥️', color: '#10b981', label: 'Node Exporter' },
  prometheus: { icon: '🔥', color: '#e85d04', label: 'Prometheus' },
  mysql: { icon: '🐬', color: '#00758f', label: 'MySQL' },
  postgresql: { icon: '🐘', color: '#336791', label: 'PostgreSQL' },
  redis: { icon: '🔴', color: '#dc382d', label: 'Redis' },
  mongodb: { icon: '🍃', color: '#00ed64', label: 'MongoDB' },
  nginx: { icon: '🟢', color: '#009639', label: 'NGINX' },
  kafka: { icon: '📨', color: '#231f20', label: 'Kafka' },
  docker: { icon: '🐳', color: '#2496ed', label: 'Docker' },
  kubernetes: { icon: '☸️', color: '#326ce5', label: 'Kubernetes' },
  rabbitmq: { icon: '🐰', color: '#ff6600', label: 'RabbitMQ' },
  haproxy: { icon: '⚖️', color: '#106da6', label: 'HAProxy' },
  process: { icon: '⚙️', color: '#6366f1', label: 'Process' },
  go_runtime: { icon: '🔷', color: '#00add8', label: 'Go Runtime' },
  http: { icon: '🌐', color: '#0ea5e9', label: 'HTTP' },
};

const getExporterConfig = (type: string) => {
  return exporterConfig[type] || { icon: '📊', color: '#8b5cf6', label: type };
};

export default function PrometheusDiscovery() {
  const [selectedHostname, setSelectedHostname] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMetric, setSelectedMetric] = useState<Metric | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  // Fetch discovered exporters
  const { data: exportersData, isLoading: loadingExporters, refetch: refetchExporters } = useQuery({
    queryKey: ['prometheus-exporters', selectedHostname],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (selectedHostname) params.append('hostname', selectedHostname);
      const res = await fetch(`${API_BASE}/api/prometheus/discovered/exporters?${params}`);
      if (!res.ok) throw new Error('Failed to fetch exporters');
      return res.json();
    },
    refetchInterval: 30000
  });

  // Fetch categories
  const { data: categoriesData, isLoading: loadingCategories } = useQuery({
    queryKey: ['prometheus-categories', selectedHostname],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (selectedHostname) params.append('hostname', selectedHostname);
      const res = await fetch(`${API_BASE}/api/prometheus/discovered/categories?${params}`);
      if (!res.ok) throw new Error('Failed to fetch categories');
      return res.json();
    },
    refetchInterval: 30000
  });

  // Fetch metrics
  const { data: metricsData, isLoading: loadingMetrics } = useQuery({
    queryKey: ['prometheus-metrics', selectedHostname, selectedCategory, searchQuery],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (selectedHostname) params.append('hostname', selectedHostname);
      if (selectedCategory) params.append('category', selectedCategory);
      if (searchQuery) params.append('search', searchQuery);
      params.append('limit', '200');
      const res = await fetch(`${API_BASE}/api/prometheus/discovered/metrics?${params}`);
      if (!res.ok) throw new Error('Failed to fetch metrics');
      return res.json();
    },
    refetchInterval: 30000
  });

  // Fetch metric series for chart
  const { data: seriesData, isLoading: loadingSeries } = useQuery({
    queryKey: ['prometheus-series', selectedMetric?.hostname, selectedMetric?.metric_name],
    queryFn: async () => {
      if (!selectedMetric) return null;
      const params = new URLSearchParams({
        hostname: selectedMetric.hostname,
        metric_name: selectedMetric.metric_name,
        step: '1m'
      });
      const res = await fetch(`${API_BASE}/api/prometheus/discovered/series?${params}`);
      if (!res.ok) throw new Error('Failed to fetch series');
      return res.json();
    },
    enabled: !!selectedMetric,
    refetchInterval: 15000
  });

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const exporters = exportersData?.exporters || [];
  const hostnames = exportersData?.hostnames || [];
  const categories = categoriesData?.categories || [];
  const metrics = metricsData?.metrics || [];
  const metricsByCategory = metricsData?.by_category || {};

  return (
    <div className="prometheus-discovery" style={{ padding: '24px', backgroundColor: '#0a0a0f', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#fff', margin: 0, display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Activity size={32} style={{ color: '#e85d04' }} />
            Prometheus Metrics
          </h1>
          <p style={{ color: '#888', marginTop: '4px' }}>
            Auto-discovered exporters from agents • {exporters.length} exporters • {metrics.length} metrics
          </p>
        </div>
        <button
          onClick={() => refetchExporters()}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 16px',
            backgroundColor: '#1a1a24',
            border: '1px solid #2a2a3a',
            borderRadius: '8px',
            color: '#fff',
            cursor: 'pointer'
          }}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        {/* Hostname Filter */}
        <select
          value={selectedHostname}
          onChange={(e) => setSelectedHostname(e.target.value)}
          style={{
            padding: '10px 16px',
            backgroundColor: '#1a1a24',
            border: '1px solid #2a2a3a',
            borderRadius: '8px',
            color: '#fff',
            minWidth: '180px'
          }}
        >
          <option value="">All Hosts</option>
          {hostnames.map((h: string) => (
            <option key={h} value={h}>{h}</option>
          ))}
        </select>

        {/* Category Filter */}
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          style={{
            padding: '10px 16px',
            backgroundColor: '#1a1a24',
            border: '1px solid #2a2a3a',
            borderRadius: '8px',
            color: '#fff',
            minWidth: '180px'
          }}
        >
          <option value="">All Categories</option>
          {categories.map((c: Category) => (
            <option key={c.category} value={c.category}>
              {getExporterConfig(c.category).label} ({c.metric_count})
            </option>
          ))}
        </select>

        {/* Search */}
        <div style={{ position: 'relative', flex: 1, maxWidth: '400px' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#666' }} />
          <input
            type="text"
            placeholder="Search metrics..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 16px 10px 40px',
              backgroundColor: '#1a1a24',
              border: '1px solid #2a2a3a',
              borderRadius: '8px',
              color: '#fff'
            }}
          />
        </div>
      </div>

      {/* Main Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '24px' }}>
        {/* Left Sidebar - Exporters */}
        <div style={{ backgroundColor: '#12121a', borderRadius: '12px', padding: '16px', border: '1px solid #1e1e2e' }}>
          <h3 style={{ color: '#fff', fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Server size={18} />
            Discovered Exporters
          </h3>
          
          {loadingExporters ? (
            <div style={{ color: '#888', textAlign: 'center', padding: '20px' }}>Loading...</div>
          ) : exporters.length === 0 ? (
            <div style={{ color: '#888', textAlign: 'center', padding: '20px' }}>
              No exporters discovered yet.
              <br /><br />
              <span style={{ fontSize: '12px' }}>
                Enable PROMETHEUS_ENABLED=true on agents
              </span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {exporters.map((exp: Exporter, idx: number) => {
                const config = getExporterConfig(exp.exporter_type);
                return (
                  <div
                    key={idx}
                    onClick={() => {
                      setSelectedHostname(exp.hostname);
                      setSelectedCategory(exp.exporter_type);
                    }}
                    style={{
                      padding: '12px',
                      backgroundColor: selectedCategory === exp.exporter_type && selectedHostname === exp.hostname
                        ? 'rgba(139, 92, 246, 0.2)'
                        : '#1a1a24',
                      border: `1px solid ${selectedCategory === exp.exporter_type && selectedHostname === exp.hostname ? '#8b5cf6' : '#2a2a3a'}`,
                      borderRadius: '8px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '18px' }}>{config.icon}</span>
                        <div>
                          <div style={{ color: '#fff', fontSize: '14px', fontWeight: '500' }}>{config.label}</div>
                          <div style={{ color: '#888', fontSize: '11px' }}>{exp.hostname}</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {exp.status === 'up' ? (
                          <CheckCircle size={14} style={{ color: '#10b981' }} />
                        ) : (
                          <XCircle size={14} style={{ color: '#ef4444' }} />
                        )}
                        <span style={{ color: '#888', fontSize: '12px' }}>{exp.metric_count}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Content - Metrics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Chart Area */}
          {selectedMetric && (
            <div style={{ backgroundColor: '#12121a', borderRadius: '12px', padding: '20px', border: '1px solid #1e1e2e' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                  <h3 style={{ color: '#fff', fontSize: '16px', margin: 0 }}>{selectedMetric.metric_name}</h3>
                  <p style={{ color: '#888', fontSize: '12px', margin: '4px 0 0' }}>
                    {selectedMetric.hostname} • {selectedMetric.category} • {selectedMetric.metric_type}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedMetric(null)}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#2a2a3a',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#888',
                    cursor: 'pointer'
                  }}
                >
                  Close
                </button>
              </div>
              
              <div style={{ height: '250px' }}>
                {loadingSeries ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#888' }}>
                    Loading chart...
                  </div>
                ) : seriesData?.data?.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={seriesData.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                      <XAxis
                        dataKey="timestamp"
                        stroke="#666"
                        tick={{ fill: '#888', fontSize: 11 }}
                        tickFormatter={(v) => v?.split(' ')[1]?.slice(0, 5) || v}
                      />
                      <YAxis stroke="#666" tick={{ fill: '#888', fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: '8px' }}
                        labelStyle={{ color: '#fff' }}
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="#8b5cf6"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#888' }}>
                    No data available
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Metrics by Category */}
          <div style={{ backgroundColor: '#12121a', borderRadius: '12px', padding: '20px', border: '1px solid #1e1e2e' }}>
            <h3 style={{ color: '#fff', fontSize: '16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BarChart3 size={18} />
              Metrics ({metrics.length})
            </h3>

            {loadingMetrics ? (
              <div style={{ color: '#888', textAlign: 'center', padding: '40px' }}>Loading metrics...</div>
            ) : Object.keys(metricsByCategory).length === 0 ? (
              <div style={{ color: '#888', textAlign: 'center', padding: '40px' }}>
                No metrics found. Select an exporter or adjust filters.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {Object.entries(metricsByCategory).map(([category, categoryMetrics]: [string, any]) => {
                  const config = getExporterConfig(category);
                  const isExpanded = expandedCategories.has(category);
                  
                  return (
                    <div key={category}>
                      {/* Category Header */}
                      <div
                        onClick={() => toggleCategory(category)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '12px 16px',
                          backgroundColor: '#1a1a24',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          border: '1px solid #2a2a3a'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          {isExpanded ? <ChevronDown size={16} color="#888" /> : <ChevronRight size={16} color="#888" />}
                          <span style={{ fontSize: '18px' }}>{config.icon}</span>
                          <span style={{ color: '#fff', fontWeight: '500' }}>{config.label}</span>
                          <span style={{
                            backgroundColor: config.color + '20',
                            color: config.color,
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontSize: '12px'
                          }}>
                            {categoryMetrics.length} metrics
                          </span>
                        </div>
                      </div>

                      {/* Metrics List */}
                      {isExpanded && (
                        <div style={{ 
                          marginTop: '8px', 
                          marginLeft: '24px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '4px'
                        }}>
                          {categoryMetrics.slice(0, 50).map((metric: Metric, idx: number) => (
                            <div
                              key={idx}
                              onClick={() => setSelectedMetric(metric)}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '10px 14px',
                                backgroundColor: selectedMetric?.metric_name === metric.metric_name ? 'rgba(139, 92, 246, 0.15)' : '#15151f',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                border: `1px solid ${selectedMetric?.metric_name === metric.metric_name ? '#8b5cf6' : 'transparent'}`,
                                transition: 'all 0.15s'
                              }}
                            >
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ 
                                  color: '#fff', 
                                  fontSize: '13px',
                                  fontFamily: 'monospace',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap'
                                }}>
                                  {metric.metric_name}
                                </div>
                                <div style={{ color: '#666', fontSize: '11px', marginTop: '2px' }}>
                                  {metric.metric_type} • {metric.sample_count} samples
                                </div>
                              </div>
                              <div style={{ textAlign: 'right', marginLeft: '16px' }}>
                                <div style={{ color: '#10b981', fontSize: '14px', fontWeight: '600' }}>
                                  {metric.avg_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                </div>
                                <div style={{ color: '#666', fontSize: '10px' }}>
                                  {metric.min_value.toFixed(1)} - {metric.max_value.toFixed(1)}
                                </div>
                              </div>
                            </div>
                          ))}
                          {categoryMetrics.length > 50 && (
                            <div style={{ color: '#888', fontSize: '12px', padding: '8px 14px' }}>
                              +{categoryMetrics.length - 50} more metrics...
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
