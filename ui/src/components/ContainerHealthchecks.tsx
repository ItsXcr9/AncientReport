import React, { useEffect, useState } from 'react';
import { Activity, CheckCircle, XCircle, Clock, AlertCircle, ChevronDown, ChevronUp, Filter, History } from 'lucide-react';

interface ContainerHealthcheck {
  id: string;
  name: string;
  health_status: 'healthy' | 'unhealthy' | 'starting' | 'none';
  health_test: string;
  failing_streak: number;
  last_log: string;
  hostname: string;
}

interface ContainerHealthchecksProps {
  selectedServer: string | null;
}

export const ContainerHealthchecks: React.FC<ContainerHealthchecksProps> = ({ selectedServer }) => {
  const [healthchecks, setHealthchecks] = useState<ContainerHealthcheck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [showAll, setShowAll] = useState(false);
  const [showProblemsOnly, setShowProblemsOnly] = useState(false);
  const [selectedContainer, setSelectedContainer] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>([]);

  const fetchHealthchecks = async () => {
    try {
      const url = selectedServer 
        ? `/api/healthchecks?hostname=${encodeURIComponent(selectedServer)}`
        : '/api/healthchecks';
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Failed to fetch healthcheck status');
      }
      const data = await response.json();
      setHealthchecks(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error('Error fetching healthchecks:', err);
      setError('Failed to load healthcheck data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealthchecks();
    const interval = setInterval(fetchHealthchecks, 180000);
    return () => clearInterval(interval);
  }, [selectedServer]);

  // Sort: problems first (unhealthy > starting > none > healthy)
  const sortedHealthchecks = [...healthchecks].sort((a, b) => {
    const priority: Record<string, number> = {
      'unhealthy': 0,
      'starting': 1,
      'none': 2,
      'healthy': 3
    };
    return (priority[a.health_status] || 4) - (priority[b.health_status] || 4);
  });

  // Apply filter if showProblemsOnly is active
  const filteredHealthchecks = showProblemsOnly
    ? sortedHealthchecks.filter(h => h.health_status === 'unhealthy' || h.health_status === 'starting')
    : sortedHealthchecks;

  // Split into visible (top 3) and rest
  const visibleHealthchecks = filteredHealthchecks.slice(0, 3);
  const otherHealthchecks = filteredHealthchecks.slice(3);

  // Count problems - unhealthy or starting with failures
  const unhealthyCount = healthchecks.filter(h => h.health_status === 'unhealthy').length;
  const startingCount = healthchecks.filter(h => h.health_status === 'starting').length;
  const healthyCount = healthchecks.filter(h => h.health_status === 'healthy').length;
  const problemCount = unhealthyCount + startingCount;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'unhealthy':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'starting':
        return <Clock className="w-5 h-5 text-yellow-400 animate-pulse" />;
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500/20 border-green-500/30 text-green-400';
      case 'unhealthy':
        return 'bg-red-500/20 border-red-500/30 text-red-400';
      case 'starting':
        return 'bg-yellow-500/20 border-yellow-500/30 text-yellow-400';
      default:
        return 'bg-gray-500/20 border-gray-500/30 text-gray-400';
    }
  };

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, string> = {
      healthy: 'Healthy',
      unhealthy: 'Unhealthy',
      starting: 'Starting',
      none: 'No Healthcheck'
    };
    return statusMap[status] || status;
  };

  const HealthcheckCard = ({ hc, compact = false }: { hc: ContainerHealthcheck; compact?: boolean }) => (
    <div
      className={`p-4 rounded-lg border ${getStatusColor(hc.health_status)} ${compact ? 'p-3' : ''}`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-3 flex-1">
          {getStatusIcon(hc.health_status)}
          <div className="flex-1">
            <h3 className="font-medium text-sm">{hc.name}</h3>
            {!compact && (
              <p className="text-xs text-gray-400 mt-1 font-mono">
                ID: {hc.id.substring(0, 12)}...
              </p>
            )}
          </div>
        </div>
        <div className="text-right">
          <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(hc.health_status)}`}>
            {getStatusBadge(hc.health_status)}
          </span>
          {hc.failing_streak > 0 && (
            <p className="text-xs text-red-400 mt-1">
              {hc.failing_streak} {hc.failing_streak === 1 ? 'failure' : 'failures'}
            </p>
          )}
        </div>
      </div>

      {!compact && hc.health_test && (
        <div className="mt-2 pt-2 border-t border-white/10">
          <p className="text-xs text-gray-400 mb-1">Healthcheck Command:</p>
          <p className="text-xs font-mono text-gray-300 break-all">{hc.health_test}</p>
        </div>
      )}

      {!compact && hc.last_log && (
        <div className="mt-2 pt-2 border-t border-white/10">
          <p className="text-xs text-gray-400 mb-1">Last Check Output:</p>
          <p className="text-xs font-mono text-gray-300 break-all whitespace-pre-wrap">
            {hc.last_log.substring(0, 200)}
            {hc.last_log.length > 200 ? '...' : ''}
          </p>
        </div>
      )}
    </div>
  );

  if (loading && healthchecks.length === 0) {
    return (
      <div className="glass-card rounded-xl p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          Container Healthchecks
        </h2>
        <div className="text-center text-gray-400 py-8">Loading healthcheck status...</div>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          Container Healthchecks
          <span className="text-sm font-normal text-gray-400 ml-2">
            ({filteredHealthchecks.length}{showProblemsOnly ? ' problems' : ''} of {healthchecks.length})
          </span>
          {problemCount > 0 && (
            <span className="ml-2 px-2 py-0.5 bg-red-500/20 border border-red-500/30 text-red-400 rounded text-xs font-medium">
              {unhealthyCount > 0 && `${unhealthyCount} unhealthy`}
              {unhealthyCount > 0 && startingCount > 0 && ', '}
              {startingCount > 0 && `${startingCount} starting`}
            </span>
          )}
        </h2>
        <div className="flex items-center gap-3">
          {/* Filter Toggle */}
          <button
            onClick={() => setShowProblemsOnly(!showProblemsOnly)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              showProblemsOnly
                ? 'bg-red-500/20 border border-red-500/30 text-red-400'
                : 'bg-white/5 border border-white/10 text-gray-400 hover:bg-white/10'
            }`}
          >
            <Filter className="w-3.5 h-3.5" />
            {showProblemsOnly ? 'Showing Problems' : 'Show All'}
          </button>
          <div className="text-xs text-gray-400">
            Updated: {lastUpdated.toLocaleTimeString()}
          </div>
        </div>
      </div>

      {/* Status Summary Bar */}
      <div className="flex gap-3 mb-4">
        <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-green-500/10 border border-green-500/20">
          <CheckCircle className="w-3.5 h-3.5 text-green-400" />
          <span className="text-xs text-green-400">{healthyCount} healthy</span>
        </div>
        {unhealthyCount > 0 && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-red-500/10 border border-red-500/20">
            <XCircle className="w-3.5 h-3.5 text-red-400" />
            <span className="text-xs text-red-400">{unhealthyCount} unhealthy</span>
          </div>
        )}
        {startingCount > 0 && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-yellow-500/10 border border-yellow-500/20">
            <Clock className="w-3.5 h-3.5 text-yellow-400" />
            <span className="text-xs text-yellow-400">{startingCount} starting</span>
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 rounded-lg border border-red-500/20 text-red-400 mb-4">
          <AlertCircle className="w-4 h-4 inline mr-2" />
          {error}
        </div>
      )}

      {healthchecks.length === 0 && !loading ? (
        <div className="p-4 glass-panel rounded-lg text-center text-gray-400">
          No containers with healthchecks configured found.
        </div>
      ) : (
        <>
          {/* Top 3 Visible Healthchecks */}
          <div className="space-y-3">
            {visibleHealthchecks.map((hc) => (
              <HealthcheckCard key={hc.id} hc={hc} />
            ))}
          </div>

          {/* Other Healthchecks - Expandable Scrollable */}
          {otherHealthchecks.length > 0 && (
            <div className="mt-4">
              <button
                onClick={() => setShowAll(!showAll)}
                className="w-full flex items-center justify-between px-4 py-3 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 transition-colors"
              >
                <span className="text-sm text-gray-400">
                  {showAll ? 'Hide' : 'Show'} {otherHealthchecks.length} more healthcheck{otherHealthchecks.length > 1 ? 's' : ''}
                </span>
                {showAll ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </button>
              
              {showAll && (
                <div className="mt-3 max-h-60 overflow-y-auto rounded-lg border border-white/10">
                  <div className="space-y-2 p-3">
                    {otherHealthchecks.map((hc) => (
                      <div 
                        key={hc.id}
                        className={`flex items-center gap-3 p-3 rounded-lg border ${getStatusColor(hc.health_status)}`}
                      >
                        {getStatusIcon(hc.health_status)}
                        <div className="flex-1 min-w-0">
                          <span className="font-medium text-sm truncate block">{hc.name}</span>
                          <span className="text-xs text-gray-500">{hc.id.substring(0, 12)}...</span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(hc.health_status)}`}>
                          {getStatusBadge(hc.health_status)}
                        </span>
                        {hc.failing_streak > 0 && (
                          <span className="text-xs text-red-400">
                            {hc.failing_streak}x
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
