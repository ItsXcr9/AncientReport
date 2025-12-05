import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Box, Server, Database, Radio, AlertTriangle, RefreshCw, 
  ArrowRight, X, Zap, Activity, Network, ChevronRight, Layers
} from 'lucide-react';

interface ContainerNode {
  id: string;
  name: string;
  image: string;
  status: string;
  health: string;
  networks: string[];
  ports: string[];
  cpu_percent: number;
  memory_mb: number;
}

interface ConnectionEdge {
  id: string;
  source: string;
  target: string;
  source_port: number;
  target_port: number;
  protocol: string;
  bytes_sent: number;
  bytes_received: number;
  latency_ms: number;
  status: string;
  requests_per_sec: number;
}

interface TopologyProblem {
  id: string;
  type: string;
  severity: string;
  source_container: string;
  target: string;
  message: string;
}

interface TopologyData {
  nodes: ContainerNode[];
  edges: ConnectionEdge[];
  problems: TopologyProblem[];
  last_updated: string;
}

interface NetworkGroup {
  name: string;
  containers: ContainerNode[];
  color: string;
}

const API_BASE = '';

// Network colors
const NETWORK_COLORS = [
  { bg: 'rgba(0, 243, 255, 0.1)', border: '#00f3ff', text: 'text-neon-blue' },
  { bg: 'rgba(190, 75, 219, 0.1)', border: '#be4bdb', text: 'text-neon-purple' },
  { bg: 'rgba(74, 222, 128, 0.1)', border: '#4ade80', text: 'text-neon-green' },
  { bg: 'rgba(251, 191, 36, 0.1)', border: '#fbbf24', text: 'text-yellow-400' },
  { bg: 'rgba(248, 113, 113, 0.1)', border: '#f87171', text: 'text-red-400' },
];

// Icon mapping for container types
const getContainerIcon = (name: string) => {
  const lowerName = name.toLowerCase();
  if (lowerName.includes('nginx') || lowerName.includes('ui') || lowerName.includes('frontend')) return Box;
  if (lowerName.includes('analysis') || lowerName.includes('api') || lowerName.includes('backend')) return Server;
  if (lowerName.includes('clickhouse') || lowerName.includes('postgres') || lowerName.includes('mysql') || lowerName.includes('mongo')) return Database;
  if (lowerName.includes('nats') || lowerName.includes('kafka') || lowerName.includes('redis') || lowerName.includes('rabbit')) return Radio;
  if (lowerName.includes('agent')) return Activity;
  return Box;
};

// Health color mapping
const getHealthColor = (health: string) => {
  switch (health) {
    case 'healthy': return { bg: 'bg-neon-green/20', border: 'border-neon-green/50', text: 'text-neon-green', fill: '#4ade80' };
    case 'warning': return { bg: 'bg-yellow-400/20', border: 'border-yellow-400/50', text: 'text-yellow-400', fill: '#fbbf24' };
    case 'critical': return { bg: 'bg-red-400/20', border: 'border-red-400/50', text: 'text-red-400', fill: '#f87171' };
    default: return { bg: 'bg-gray-400/20', border: 'border-gray-400/50', text: 'text-gray-400', fill: '#9ca3af' };
  }
};

const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export const ContainerTopology = () => {
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedNodeDetails, setSelectedNodeDetails] = useState<any>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'groups'>('graph');

  const fetchTopology = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v3/topology/map`);
      if (res.ok) {
        const data = await res.json();
        setTopology(data);
      }
    } catch (error) {
      console.error('Failed to fetch topology:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchNodeDetails = useCallback(async (nodeId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v3/topology/container/${nodeId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedNodeDetails(data);
      }
    } catch (error) {
      console.error('Failed to fetch node details:', error);
    }
  }, []);

  useEffect(() => {
    fetchTopology();
    const interval = setInterval(fetchTopology, 30000);
    return () => clearInterval(interval);
  }, [fetchTopology]);

  useEffect(() => {
    if (selectedNode) {
      fetchNodeDetails(selectedNode);
    } else {
      setSelectedNodeDetails(null);
    }
  }, [selectedNode, fetchNodeDetails]);

  // Group containers by network
  const networkGroups = useMemo(() => {
    if (!topology?.nodes) return [];
    
    const groups: Record<string, ContainerNode[]> = {};
    
    topology.nodes.forEach(node => {
      const networks = node.networks && node.networks.length > 0 ? node.networks : ['default'];
      networks.forEach(network => {
        if (!groups[network]) {
          groups[network] = [];
        }
        if (!groups[network].find(n => n.id === node.id)) {
          groups[network].push(node);
        }
      });
    });

    return Object.entries(groups).map(([name, containers], index) => ({
      name,
      containers,
      color: NETWORK_COLORS[index % NETWORK_COLORS.length]
    }));
  }, [topology?.nodes]);

  // Calculate node positions - group by network
  const nodePositions = useMemo(() => {
    if (!topology?.nodes) return {};
    const positions: Record<string, { x: number; y: number; network: string }> = {};
    const centerX = 350;
    const centerY = 200;
    
    if (networkGroups.length === 1) {
      // Single network: circular layout
      const radius = 150;
      topology.nodes.forEach((node, index) => {
        const angle = (2 * Math.PI * index) / topology.nodes.length - Math.PI / 2;
        positions[node.id] = {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
          network: node.networks?.[0] || 'default'
        };
      });
    } else {
      // Multiple networks: group layout
      const groupRadius = 100;
      const groupSpacing = 200;
      
      networkGroups.forEach((group, groupIndex) => {
        const groupAngle = (2 * Math.PI * groupIndex) / networkGroups.length - Math.PI / 2;
        const groupCenterX = centerX + (networkGroups.length > 2 ? groupRadius * 1.5 : 0) * Math.cos(groupAngle);
        const groupCenterY = centerY + (networkGroups.length > 2 ? groupRadius * 1.5 : 0) * Math.sin(groupAngle);
        
        group.containers.forEach((node, nodeIndex) => {
          if (!positions[node.id]) {
            const nodeAngle = (2 * Math.PI * nodeIndex) / group.containers.length - Math.PI / 2;
            const nodeRadius = Math.min(60, 80 - group.containers.length * 5);
            positions[node.id] = {
              x: groupCenterX + nodeRadius * Math.cos(nodeAngle),
              y: groupCenterY + nodeRadius * Math.sin(nodeAngle),
              network: group.name
            };
          }
        });
      });
    }
    
    return positions;
  }, [topology?.nodes, networkGroups]);

  // Get edge path with curve
  const getEdgePath = useCallback((sourceId: string, targetId: string) => {
    const source = nodePositions[sourceId];
    const target = nodePositions[targetId];
    if (!source || !target) return '';
    
    const midX = (source.x + target.x) / 2;
    const midY = (source.y + target.y) / 2;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const curvature = 20;
    const nx = -dy / len * curvature;
    const ny = dx / len * curvature;
    
    return `M ${source.x} ${source.y} Q ${midX + nx} ${midY + ny} ${target.x} ${target.y}`;
  }, [nodePositions]);

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-neon-blue/10 rounded-lg">
            <Network className="w-5 h-5 text-neon-blue" />
          </div>
          <h3 className="text-lg font-semibold text-white">Container Topology</h3>
        </div>
        <div className="flex items-center justify-center py-16">
          <RefreshCw className="w-8 h-8 text-neon-blue animate-spin" />
        </div>
      </div>
    );
  }

  if (!topology) {
    return (
      <div className="glass-card p-6 rounded-xl text-center py-12">
        <Network className="w-12 h-12 text-gray-600 mx-auto mb-4" />
        <p className="text-gray-400">Failed to load topology</p>
      </div>
    );
  }

  const problemCount = topology.problems.length;
  const criticalCount = topology.problems.filter(p => p.severity === 'critical').length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-6 rounded-xl"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-neon-blue/10 rounded-lg">
            <Network className="w-5 h-5 text-neon-blue" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">Container Topology</h3>
            <p className="text-xs text-gray-500">
              {topology.nodes.length} containers • {topology.edges.length} connections • {networkGroups.length} network{networkGroups.length > 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* View Toggle */}
          <div className="flex items-center bg-white/5 rounded-lg p-1">
            <button
              onClick={() => setViewMode('graph')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                viewMode === 'graph' ? 'bg-neon-blue/20 text-neon-blue' : 'text-gray-400 hover:bg-white/5'
              }`}
            >
              Graph
            </button>
            <button
              onClick={() => setViewMode('groups')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                viewMode === 'groups' ? 'bg-neon-purple/20 text-neon-purple' : 'text-gray-400 hover:bg-white/5'
              }`}
            >
              <Layers className="w-3 h-3" />
              Groups
            </button>
          </div>
          
          {problemCount > 0 && (
            <div className={`px-3 py-1 rounded-lg text-xs font-medium flex items-center gap-1 ${
              criticalCount > 0 ? 'bg-red-400/10 text-red-400' : 'bg-yellow-400/10 text-yellow-400'
            }`}>
              <AlertTriangle className="w-3 h-3" />
              {problemCount} issue{problemCount > 1 ? 's' : ''}
            </div>
          )}
          <button
            onClick={fetchTopology}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {viewMode === 'graph' ? (
        /* Graph View */
        <div className="relative bg-white/5 rounded-lg border border-white/10 overflow-hidden" style={{ height: '400px' }}>
          <svg width="100%" height="100%" viewBox="0 0 700 400" className="overflow-visible">
            {/* Network Group Backgrounds */}
            {networkGroups.length > 1 && networkGroups.map((group, idx) => {
              const groupNodes = group.containers.map(c => nodePositions[c.id]).filter(Boolean);
              if (groupNodes.length === 0) return null;
              
              const minX = Math.min(...groupNodes.map(n => n.x)) - 50;
              const maxX = Math.max(...groupNodes.map(n => n.x)) + 50;
              const minY = Math.min(...groupNodes.map(n => n.y)) - 50;
              const maxY = Math.max(...groupNodes.map(n => n.y)) + 50;
              
              return (
                <g key={group.name}>
                  <rect
                    x={minX}
                    y={minY}
                    width={maxX - minX}
                    height={maxY - minY}
                    rx="12"
                    fill={group.color.bg}
                    stroke={group.color.border}
                    strokeWidth="1"
                    strokeDasharray="4,4"
                    opacity="0.5"
                  />
                  <text
                    x={minX + 8}
                    y={minY + 16}
                    className="fill-gray-400 text-xs"
                  >
                    {group.name}
                  </text>
                </g>
              );
            })}
            
            {/* Connection Edges */}
            <g className="edges">
              {topology.edges.map((edge) => {
                const isHovered = hoveredEdge === edge.id;
                const hasProblem = topology.problems.some(p => 
                  p.source_container === edge.source && p.target === edge.target
                );
                const strokeColor = hasProblem ? '#f87171' : 
                  edge.status === 'active' ? '#00f3ff' : '#6b7280';
                const strokeWidth = isHovered ? 3 : Math.min(2, 1 + edge.requests_per_sec / 100);
                
                return (
                  <g key={edge.id}>
                    <path
                      d={getEdgePath(edge.source, edge.target)}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                      strokeOpacity={isHovered ? 1 : 0.5}
                      strokeDasharray={edge.status !== 'active' ? '5,5' : undefined}
                      className="transition-all duration-300 cursor-pointer"
                      onMouseEnter={() => setHoveredEdge(edge.id)}
                      onMouseLeave={() => setHoveredEdge(null)}
                    />
                    {/* Animated flow indicator */}
                    {edge.status === 'active' && (
                      <circle r="3" fill={strokeColor}>
                        <animateMotion
                          dur="2s"
                          repeatCount="indefinite"
                          path={getEdgePath(edge.source, edge.target)}
                        />
                      </circle>
                    )}
                  </g>
                );
              })}
            </g>

            {/* Container Nodes */}
            <g className="nodes">
              {topology.nodes.map((node) => {
                const pos = nodePositions[node.id];
                if (!pos) return null;
                
                const colors = getHealthColor(node.health);
                const isSelected = selectedNode === node.id;
                const Icon = getContainerIcon(node.name);
                const hasProblem = topology.problems.some(p => p.source_container === node.id);
                
                return (
                  <g
                    key={node.id}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    onClick={() => setSelectedNode(isSelected ? null : node.id)}
                    className="cursor-pointer"
                  >
                    {/* Problem indicator ring */}
                    {hasProblem && (
                      <circle
                        r="42"
                        fill="none"
                        stroke="#f87171"
                        strokeWidth="2"
                        strokeDasharray="4,4"
                        className="animate-pulse"
                      />
                    )}
                    
                    {/* Selection ring */}
                    {isSelected && (
                      <circle
                        r="40"
                        fill="none"
                        stroke="#00f3ff"
                        strokeWidth="2"
                      />
                    )}
                    
                    {/* Node circle */}
                    <circle
                      r="32"
                      fill={colors.fill}
                      fillOpacity="0.2"
                      stroke={colors.fill}
                      strokeWidth="2"
                      className="transition-all duration-300"
                    />
                    
                    {/* Icon */}
                    <foreignObject x="-12" y="-12" width="24" height="24">
                      <div className={`w-6 h-6 ${colors.text}`}>
                        <Icon className="w-6 h-6" />
                      </div>
                    </foreignObject>
                    
                    {/* Label */}
                    <text
                      y="50"
                      textAnchor="middle"
                      className="fill-white text-xs font-medium"
                    >
                      {node.name.replace(/ancientreport-/i, '').replace(/^\//, '')}
                    </text>
                    
                    {/* Status indicator */}
                    <circle
                      cx="22"
                      cy="-22"
                      r="6"
                      fill={colors.fill}
                    />
                  </g>
                );
              })}
            </g>
          </svg>

          {/* Edge Tooltip */}
          <AnimatePresence>
            {hoveredEdge && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-gray-900/95 border border-white/20 rounded-lg p-3 text-xs shadow-xl"
              >
                {(() => {
                  const edge = topology.edges.find(e => e.id === hoveredEdge);
                  if (!edge) return null;
                  return (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-white font-medium">
                        <span>{edge.source}</span>
                        <ArrowRight className="w-3 h-3 text-neon-blue" />
                        <span>{edge.target}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-3 text-gray-400">
                        <div>
                          <Zap className="w-3 h-3 inline mr-1" />
                          {edge.latency_ms.toFixed(1)}ms
                        </div>
                        <div>
                          <Activity className="w-3 h-3 inline mr-1" />
                          {edge.requests_per_sec.toFixed(0)}/s
                        </div>
                        <div>
                          {formatBytes(edge.bytes_sent + edge.bytes_received)}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ) : (
        /* Groups View */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {networkGroups.map((group, idx) => (
            <div
              key={group.name}
              className="p-4 rounded-lg border"
              style={{ 
                backgroundColor: group.color.bg,
                borderColor: group.color.border
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <Network className="w-4 h-4" style={{ color: group.color.border }} />
                <h4 className="font-medium text-white">{group.name}</h4>
                <span className="text-xs text-gray-400 ml-auto">
                  {group.containers.length} container{group.containers.length > 1 ? 's' : ''}
                </span>
              </div>
              <div className="space-y-2">
                {group.containers.map(container => {
                  const colors = getHealthColor(container.health);
                  const Icon = getContainerIcon(container.name);
                  
                  return (
                    <div 
                      key={container.id}
                      onClick={() => setSelectedNode(selectedNode === container.id ? null : container.id)}
                      className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ${
                        selectedNode === container.id ? 'bg-white/20' : 'bg-white/5 hover:bg-white/10'
                      }`}
                    >
                      <div className={`p-1.5 rounded ${colors.bg}`}>
                        <Icon className={`w-4 h-4 ${colors.text}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">
                          {container.name.replace(/ancientreport-/i, '').replace(/^\//, '')}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-gray-400">
                          <span>{container.cpu_percent.toFixed(1)}% CPU</span>
                          <span>{container.memory_mb.toFixed(0)} MB</span>
                        </div>
                      </div>
                      <div className={`w-2 h-2 rounded-full`} style={{ backgroundColor: colors.fill }} />
                    </div>
                  );
                })}
              </div>
              
              {/* Network Connections */}
              {topology.edges.filter(e => 
                group.containers.some(c => c.id === e.source) &&
                group.containers.some(c => c.id === e.target)
              ).length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  <p className="text-xs text-gray-400 mb-2">Internal Connections</p>
                  {topology.edges.filter(e => 
                    group.containers.some(c => c.id === e.source) &&
                    group.containers.some(c => c.id === e.target)
                  ).map(edge => (
                    <div key={edge.id} className="flex items-center gap-1 text-xs text-gray-300">
                      <span>{edge.source.replace(/ancientreport-/i, '')}</span>
                      <ChevronRight className="w-3 h-3 text-neon-blue" />
                      <span>{edge.target.replace(/ancientreport-/i, '')}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Node Details Panel */}
      <AnimatePresence>
        {selectedNode && selectedNodeDetails && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 p-4 bg-white/5 rounded-lg border border-white/10"
          >
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-semibold text-white flex items-center gap-2">
                {(() => {
                  const Icon = getContainerIcon(selectedNodeDetails.container.name);
                  return <Icon className="w-4 h-4 text-neon-blue" />;
                })()}
                {selectedNodeDetails.container.name}
              </h4>
              <button
                onClick={() => setSelectedNode(null)}
                className="p-1 hover:bg-white/10 rounded"
              >
                <X className="w-4 h-4 text-gray-400" />
              </button>
            </div>
            
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
              <div className="p-2 bg-white/5 rounded">
                <div className="text-xs text-gray-400">CPU</div>
                <div className="text-sm font-medium text-white">
                  {selectedNodeDetails.container.cpu_percent.toFixed(1)}%
                </div>
              </div>
              <div className="p-2 bg-white/5 rounded">
                <div className="text-xs text-gray-400">Memory</div>
                <div className="text-sm font-medium text-white">
                  {selectedNodeDetails.container.memory_mb.toFixed(0)} MB
                </div>
              </div>
              <div className="p-2 bg-white/5 rounded">
                <div className="text-xs text-gray-400">In</div>
                <div className="text-sm font-medium text-neon-green">
                  {formatBytes(selectedNodeDetails.total_bytes_in)}
                </div>
              </div>
              <div className="p-2 bg-white/5 rounded">
                <div className="text-xs text-gray-400">Out</div>
                <div className="text-sm font-medium text-neon-blue">
                  {formatBytes(selectedNodeDetails.total_bytes_out)}
                </div>
              </div>
            </div>

            {/* Connections */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {selectedNodeDetails.outgoing_connections?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1">Outgoing</div>
                  <div className="space-y-1">
                    {selectedNodeDetails.outgoing_connections.map((conn: ConnectionEdge) => (
                      <div key={conn.id} className="flex items-center gap-2 text-xs text-gray-300 py-1">
                        <ChevronRight className="w-3 h-3 text-neon-blue" />
                        <span>{conn.target}</span>
                        <span className="text-gray-500">:{conn.target_port}</span>
                        <span className="ml-auto text-gray-400">{conn.latency_ms.toFixed(1)}ms</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selectedNodeDetails.incoming_connections?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1">Incoming</div>
                  <div className="space-y-1">
                    {selectedNodeDetails.incoming_connections.map((conn: ConnectionEdge) => (
                      <div key={conn.id} className="flex items-center gap-2 text-xs text-gray-300 py-1">
                        <ChevronRight className="w-3 h-3 text-neon-green rotate-180" />
                        <span>{conn.source}</span>
                        <span className="text-gray-500">→ :{conn.target_port}</span>
                        <span className="ml-auto text-gray-400">{conn.requests_per_sec.toFixed(0)}/s</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Problems List */}
      {topology.problems.length > 0 && (
        <div className="mt-4 p-3 bg-red-400/5 border border-red-400/20 rounded-lg">
          <div className="flex items-center gap-2 text-red-400 text-sm font-medium mb-2">
            <AlertTriangle className="w-4 h-4" />
            Active Problems
          </div>
          <div className="space-y-1 max-h-24 overflow-y-auto">
            {topology.problems.map((problem) => (
              <div key={problem.id} className="text-xs text-gray-300 flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${
                  problem.severity === 'critical' ? 'bg-red-400' : 'bg-yellow-400'
                }`} />
                <span>{problem.message}</span>
                <span className="text-gray-500">({problem.source_container})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default ContainerTopology;
