/**
 * Observability Page - Metrics Monitoring Dashboard
 * Replaces Prometheus + Grafana with built-in functionality
 */

import { useState, useEffect } from 'react';
import { useOutletContext, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Activity, Gauge, Clock, BarChart3, 
  RefreshCw, Search, ChevronDown, Radar, Zap, ExternalLink
} from 'lucide-react';

import { MetricTargetsPanel } from '../components/MetricTargetsPanel';
import { ScrapedMetricChart } from '../components/ScrapedMetricChart';
import { DiscoveredMetricChart } from '../components/DiscoveredMetricChart';
import { ContainerApps } from '../components/ContainerApps';

interface Target {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  last_status: string;
  metrics_count: number;
}

interface AvailableMetric {
  name: string;
  sample_count: number;
  last_seen: string;
}

interface DiscoveredExporter {
  hostname: string;
  exporter_type: string;
  scrape_target: string;
  metric_count: number;
  last_seen: string;
  first_seen: string;
  status: 'up' | 'down';
}

interface DiscoveredMetric {
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

interface ObservabilityProps {
  selectedServer: string | null;
}

export default function Observability() {
  const { selectedServer } = useOutletContext<ObservabilityProps>();
  
  const [targets, setTargets] = useState<Target[]>([]);
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const [availableMetrics, setAvailableMetrics] = useState<AvailableMetric[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d'>('1h');
  const [showMetricSelector, setShowMetricSelector] = useState(false);
  
  // Discovered exporters state
  const [discoveredExporters, setDiscoveredExporters] = useState<DiscoveredExporter[]>([]);
  const [discoveredMetrics, setDiscoveredMetrics] = useState<DiscoveredMetric[]>([]);
  const [selectedDiscoveredExporter, setSelectedDiscoveredExporter] = useState<string | null>(null);
  const [selectedDiscoveredMetrics, setSelectedDiscoveredMetrics] = useState<string[]>([]);
  const [discoveredSearchQuery, setDiscoveredSearchQuery] = useState('');
  const [showDiscoveredMetricSelector, setShowDiscoveredMetricSelector] = useState(false);

  // Fetch targets
  useEffect(() => {
    const fetchTargets = async () => {
      try {
        const response = await fetch('/api/prometheus/targets');
        if (response.ok) {
          const data = await response.json();
          setTargets(data);
          
          // Auto-select first enabled target
          if (data.length > 0 && !selectedTarget) {
            const enabledTarget = data.find((t: Target) => t.enabled);
            if (enabledTarget) {
              setSelectedTarget(enabledTarget.id);
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch targets:', error);
      }
    };
    
    fetchTargets();
    const interval = setInterval(fetchTargets, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch available metrics when target changes
  useEffect(() => {
    if (!selectedTarget) {
      setAvailableMetrics([]);
      return;
    }

    const fetchMetrics = async () => {
      setMetricsLoading(true);
      try {
        const response = await fetch(`/api/prometheus/scraped/metrics?target_id=${selectedTarget}`);
        if (response.ok) {
          const data = await response.json();
          setAvailableMetrics(data.metrics || []);
          
          // Auto-select first 4 metrics if none selected
          if (selectedMetrics.length === 0 && data.metrics?.length > 0) {
            const defaultMetrics = data.metrics.slice(0, 4).map((m: AvailableMetric) => m.name);
            setSelectedMetrics(defaultMetrics);
          }
        }
      } catch (error) {
        console.error('Failed to fetch metrics:', error);
      } finally {
        setMetricsLoading(false);
      }
    };

    fetchMetrics();
  }, [selectedTarget]);

  const toggleMetric = (metricName: string) => {
    setSelectedMetrics(prev => {
      if (prev.includes(metricName)) {
        return prev.filter(m => m !== metricName);
      } else {
        return [...prev, metricName];
      }
    });
  };

  // Fetch discovered exporters
  useEffect(() => {
    const fetchDiscoveredExporters = async () => {
      try {
        const response = await fetch('/api/prometheus/discovered/exporters');
        if (response.ok) {
          const data = await response.json();
          setDiscoveredExporters(data.exporters || []);
          
          // Auto-select first exporter if none selected
          if (data.exporters?.length > 0 && !selectedDiscoveredExporter) {
            setSelectedDiscoveredExporter(data.exporters[0].scrape_target);
          }
        }
      } catch (error) {
        console.error('Failed to fetch discovered exporters:', error);
      }
    };

    fetchDiscoveredExporters();
    const interval = setInterval(fetchDiscoveredExporters, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch discovered metrics when exporter changes
  useEffect(() => {
    if (!selectedDiscoveredExporter) {
      setDiscoveredMetrics([]);
      return;
    }

    const fetchDiscoveredMetrics = async () => {
      try {
        const response = await fetch(`/api/prometheus/discovered/metrics?scrape_target=${encodeURIComponent(selectedDiscoveredExporter)}`);
        if (response.ok) {
          const data = await response.json();
          setDiscoveredMetrics(data.metrics || []);
          
          // Auto-select first 4 metrics if none selected
          if (selectedDiscoveredMetrics.length === 0 && data.metrics?.length > 0) {
            const defaultM = data.metrics.slice(0, 4).map((m: DiscoveredMetric) => m.metric_name);
            setSelectedDiscoveredMetrics(defaultM);
          }
        }
      } catch (error) {
        console.error('Failed to fetch discovered metrics:', error);
      }
    };

    fetchDiscoveredMetrics();
  }, [selectedDiscoveredExporter]);

  const toggleDiscoveredMetric = (metricName: string) => {
    setSelectedDiscoveredMetrics(prev => {
      if (prev.includes(metricName)) {
        return prev.filter(m => m !== metricName);
      } else {
        return [...prev, metricName];
      }
    });
  };

  const filteredDiscoveredMetrics = discoveredMetrics.filter(m =>
    m.metric_name.toLowerCase().includes(discoveredSearchQuery.toLowerCase())
  );

  const filteredMetrics = availableMetrics.filter(m => 
    m.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedTargetName = targets.find(t => t.id === selectedTarget)?.name || 'Select Target';

  // Color palette for charts
  const chartColors = [
    '#00F3FF', // neon-blue
    '#A855F7', // purple
    '#10B981', // green
    '#F59E0B', // amber
    '#EF4444', // red
    '#3B82F6', // blue
    '#EC4899', // pink
    '#6366F1'  // indigo
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white font-display tracking-tight mb-2 flex items-center gap-3">
          <Activity className="w-7 h-7 text-neon-blue" />
          Observability
        </h1>
        <p className="text-gray-400 text-sm">
          Metrics collection and visualization • No Prometheus or Grafana needed
        </p>
      </div>

      {/* Scrape Targets Management */}
      <MetricTargetsPanel />

      {/* Metrics Dashboard */}
      {targets.some(t => t.enabled) && (
        <motion.div 
          className="glass-card rounded-xl p-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <BarChart3 className="w-5 h-5 text-neon-purple" />
              <h2 className="text-lg font-semibold">Metrics Dashboard</h2>
            </div>

            <div className="flex items-center gap-4">
              {/* Target Selector */}
              <div className="relative">
                <select
                  value={selectedTarget || ''}
                  onChange={(e) => {
                    setSelectedTarget(e.target.value);
                    setSelectedMetrics([]);
                  }}
                  className="appearance-none bg-white/5 border border-white/10 rounded-lg px-4 py-2 pr-8 text-sm text-white focus:outline-none focus:border-neon-blue cursor-pointer"
                >
                  <option value="" disabled>Select Target</option>
                  {targets.filter(t => t.enabled).map(t => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>

              {/* Time Range */}
              <div className="bg-white/5 rounded-lg p-1 flex border border-white/10">
                {(['1h', '6h', '24h', '7d'] as const).map((range) => (
                  <button
                    key={range}
                    onClick={() => setTimeRange(range)}
                    className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                      timeRange === range 
                        ? 'bg-neon-blue/20 text-neon-blue' 
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Metric Selector */}
          {selectedTarget && (
            <div className="mb-6">
              <div className="flex items-center gap-3 mb-3">
                <button
                  onClick={() => setShowMetricSelector(!showMetricSelector)}
                  className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
                >
                  <Gauge className="w-4 h-4" />
                  {selectedMetrics.length} metrics selected
                  <ChevronDown className={`w-4 h-4 transition-transform ${showMetricSelector ? 'rotate-180' : ''}`} />
                </button>

                {metricsLoading && (
                  <RefreshCw className="w-4 h-4 animate-spin text-gray-400" />
                )}
              </div>

              {showMetricSelector && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="bg-white/5 rounded-lg p-4 border border-white/10"
                >
                  {/* Search */}
                  <div className="relative mb-3">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search metrics..."
                      className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue"
                    />
                  </div>

                  {/* Metrics Grid */}
                  <div className="max-h-48 overflow-y-auto">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {filteredMetrics.map(metric => (
                        <button
                          key={metric.name}
                          onClick={() => toggleMetric(metric.name)}
                          className={`text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                            selectedMetrics.includes(metric.name)
                              ? 'bg-neon-blue/20 text-neon-blue border border-neon-blue/30'
                              : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white border border-transparent'
                          }`}
                        >
                          <div className="truncate font-mono">{metric.name}</div>
                          <div className="text-gray-500 text-[10px] mt-0.5">
                            {metric.sample_count} samples
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {filteredMetrics.length === 0 && (
                    <div className="text-center text-gray-500 text-sm py-4">
                      {searchQuery ? 'No metrics match your search' : 'No metrics available yet'}
                    </div>
                  )}
                </motion.div>
              )}
            </div>
          )}

          {/* Charts Grid */}
          {selectedTarget && selectedMetrics.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {selectedMetrics.map((metric, index) => (
                <ScrapedMetricChart
                  key={`${selectedTarget}-${metric}`}
                  targetId={selectedTarget}
                  metricName={metric}
                  color={chartColors[index % chartColors.length]}
                  timeRange={timeRange}
                  height={180}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              {selectedTarget 
                ? 'Select metrics to display charts'
                : 'Select a target with metrics to view charts'
              }
            </div>
          )}
        </motion.div>
      )}

      {/* Auto-Discovered Prometheus Dashboard */}
      {discoveredExporters.length > 0 && (
        <motion.div 
          className="glass-card rounded-xl p-6 border border-green-500/20"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Radar className="w-5 h-5 text-green-400" />
              <h2 className="text-lg font-semibold text-green-400">Auto-Discovered Metrics</h2>
              <span className="text-xs bg-green-500/10 text-green-400 px-2 py-1 rounded-full border border-green-500/30">
                {discoveredExporters.length} exporter{discoveredExporters.length !== 1 ? 's' : ''}
              </span>
            </div>

            <div className="flex items-center gap-4">
              {/* Exporter Selector */}
              <div className="relative">
                <select
                  value={selectedDiscoveredExporter || ''}
                  onChange={(e) => {
                    setSelectedDiscoveredExporter(e.target.value);
                    setSelectedDiscoveredMetrics([]);
                  }}
                  className="appearance-none bg-green-500/10 border border-green-500/30 rounded-lg px-4 py-2 pr-8 text-sm text-white focus:outline-none focus:border-green-400 cursor-pointer min-w-[250px]"
                >
                  <option value="" disabled>Select Exporter</option>
                  {discoveredExporters.map((exp, idx) => (
                    <option key={`${exp.scrape_target}-${idx}`} value={exp.scrape_target}>
                      {exp.exporter_type || 'unknown'} @ {exp.hostname} ({exp.metric_count} metrics)
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-green-400 pointer-events-none" />
              </div>

              <Link 
                to="/prometheus-discovery"
                className="flex items-center gap-2 px-3 py-2 bg-green-500/10 hover:bg-green-500/20 text-green-400 rounded-lg transition-colors text-sm"
              >
                <ExternalLink className="w-4 h-4" />
                Full View
              </Link>
            </div>
          </div>

          {/* Metric Selector */}
          {selectedDiscoveredExporter && (
            <div className="mb-6">
              <div className="flex items-center gap-3 mb-3">
                <button
                  onClick={() => setShowDiscoveredMetricSelector(!showDiscoveredMetricSelector)}
                  className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
                >
                  <Zap className="w-4 h-4 text-green-400" />
                  {selectedDiscoveredMetrics.length} metrics selected
                  <ChevronDown className={`w-4 h-4 transition-transform ${showDiscoveredMetricSelector ? 'rotate-180' : ''}`} />
                </button>
              </div>

              {showDiscoveredMetricSelector && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="bg-green-500/5 rounded-lg p-4 border border-green-500/20"
                >
                  {/* Search */}
                  <div className="relative mb-3">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-green-400" />
                    <input
                      type="text"
                      value={discoveredSearchQuery}
                      onChange={(e) => setDiscoveredSearchQuery(e.target.value)}
                      placeholder="Search discovered metrics..."
                      className="w-full pl-10 pr-4 py-2 bg-white/5 border border-green-500/20 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-green-400"
                    />
                  </div>

                  {/* Metrics Grid */}
                  <div className="max-h-48 overflow-y-auto">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {filteredDiscoveredMetrics.map(metric => (
                        <button
                          key={metric.metric_name}
                          onClick={() => toggleDiscoveredMetric(metric.metric_name)}
                          className={`text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                            selectedDiscoveredMetrics.includes(metric.metric_name)
                              ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                              : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white border border-transparent'
                          }`}
                        >
                          <div className="truncate font-mono">{metric.metric_name}</div>
                          <div className="text-gray-500 text-[10px] mt-0.5">
                            {metric.sample_count} samples • avg: {metric.avg_value}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {filteredDiscoveredMetrics.length === 0 && (
                    <div className="text-center text-gray-500 text-sm py-4">
                      {discoveredSearchQuery ? 'No metrics match your search' : 'No metrics available yet'}
                    </div>
                  )}
                </motion.div>
              )}
            </div>
          )}

          {/* Info about the selected exporter */}
          {selectedDiscoveredExporter && discoveredExporters.find(e => e.scrape_target === selectedDiscoveredExporter) && (
            <div className="mb-4 p-3 bg-green-500/5 rounded-lg border border-green-500/20">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-4">
                  <span className="text-gray-400">Target:</span>
                  <span className="font-mono text-green-400">
                    {discoveredExporters.find(e => e.scrape_target === selectedDiscoveredExporter)?.scrape_target}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-green-400 shadow-lg shadow-green-500/50" />
                  <span className="text-green-400 text-xs">Live</span>
                </div>
              </div>
            </div>
          )}

          {/* Charts using DiscoveredMetricChart component */}
          {selectedDiscoveredExporter && selectedDiscoveredMetrics.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {selectedDiscoveredMetrics.map((metric, index) => (
                <DiscoveredMetricChart
                  key={metric}
                  scrapeTarget={selectedDiscoveredExporter}
                  metricName={metric}
                  color={chartColors[index % chartColors.length]}
                  timeRange={timeRange}
                  height={180}
                />
              ))}
            </div>
          ) : selectedDiscoveredExporter ? (
            <div className="text-center py-12 text-gray-500">
              Select metrics above to view charts
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              Select an exporter to view its metrics
            </div>
          )}
        </motion.div>
      )}

      {/* Container Applications (existing feature) */}
      <div className="mt-8">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-neon-green" />
          Container Applications
        </h2>
        <p className="text-gray-400 text-sm mb-4">
          Kafka, Redis, and PostgreSQL monitoring
        </p>
        <ContainerApps selectedServer={selectedServer} />
      </div>
    </div>
  );
}
