import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Box, Server, Database, Radio, AlertTriangle, RefreshCw, 
  ArrowRight, X, Zap, Activity, Network, ChevronRight
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

const API_BASE = '';

// Icon mapping for container types
const getContainerIcon = (name: string) => {
  if (name.includes('nginx') || name.includes('ui')) return Box;
  if (name.includes('analysis') || name.includes('api')) return Server;
  if (name.includes('clickhouse') || name.includes('postgres') || name.includes('mysql')) return Database;
  if (name.includes('nats') || name.includes('kafka') || name.includes('redis')) return Radio;
  return Box;
};

// Health color mapping
const getHealthColor = (health: string) => {
  switch (health) {
    case 'healthy': return { bg: 'bg-neon-green/20', border: 'border-neon-green/50', text: 'text-neon-green' };
    case 'warning': return { bg: 'bg-yellow-400/20', border: 'border-yellow-400/50', text: 'text-yellow-400' };
    case 'critical': return { bg: 'bg-red-400/20', border: 'border-red-400/50', text: 'text-red-400' };
    default: return { bg: 'bg-gray-400/20', border: 'border-gray-400/50', text: 'text-gray-400' };
  }
};

// Format bytes to human readable
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

  // Calculate node positions in a circular layout
  const nodePositions = useMemo(() => {
    if (!topology?.nodes) return {};
    const positions: Record<string, { x: number; y: number }> = {};
    const centerX = 300;
    const centerY = 200;
    const radius = 150;
    
    topology.nodes.forEach((node, index) => {
      const angle = (2 * Math.PI * index) / topology.nodes.length - Math.PI / 2;
      positions[node.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      };
    });
    return positions;
  }, [topology?.nodes]);

  // Get edge path between two nodes
  const getEdgePath = useCallback((sourceId: string, targetId: string) => {
    const source = nodePositions[sourceId];
    const target = nodePositions[targetId];
    if (!source || !target) return '';
    
    // Calculate control point for curved line
    const midX = (source.x + target.x) / 2;
    const midY = (source.y + target.y) / 2;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    const curvature = 30;
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
              {topology.nodes.length} containers • {topology.edges.length} connections
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
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

      {/* Topology Graph */}
      <div className="relative bg-white/5 rounded-lg border border-white/10 overflow-hidden" style={{ height: '400px' }}>
        <svg width="100%" height="100%" viewBox="0 0 600 400" className="overflow-visible">
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
                  {/* Arrow marker */}
                  <circle
                    cx={nodePositions[edge.target]?.x}
                    cy={nodePositions[edge.target]?.y}
                    r="4"
                    fill={strokeColor}
                    opacity={isHovered ? 1 : 0.5}
                  />
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
                  {/* Outer ring for problems */}
                  {hasProblem && (
                    <circle
                      r="40"
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
                      r="38"
                      fill="none"
                      stroke="#00f3ff"
                      strokeWidth="2"
                    />
                  )}
                  
                  {/* Node circle */}
                  <circle
                    r="32"
                    className={`${colors.bg} ${colors.border} transition-all duration-300`}
                    fill="currentColor"
                    stroke="currentColor"
                    strokeWidth="2"
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
                    {node.name.replace('ancientreport-', '')}
                  </text>
                  
                  {/* Status indicator */}
                  <circle
                    cx="20"
                    cy="-20"
                    r="6"
                    className={`${node.health === 'healthy' ? 'fill-neon-green' : 
                      node.health === 'warning' ? 'fill-yellow-400' : 'fill-red-400'}`}
                  />
                </g>
              );
            })}
          </g>
        </svg>

        {/* Edge tooltip */}
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

            {/* Connections list */}
            <div className="space-y-2">
              {selectedNodeDetails.outgoing_connections?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1">Outgoing Connections</div>
                  {selectedNodeDetails.outgoing_connections.map((conn: ConnectionEdge) => (
                    <div key={conn.id} className="flex items-center gap-2 text-xs text-gray-300 py-1">
                      <ChevronRight className="w-3 h-3 text-neon-blue" />
                      <span>{conn.target}</span>
                      <span className="text-gray-500">:{conn.target_port}</span>
                      <span className="ml-auto text-gray-400">{conn.latency_ms.toFixed(1)}ms</span>
                    </div>
                  ))}
                </div>
              )}
              {selectedNodeDetails.incoming_connections?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1">Incoming Connections</div>
                  {selectedNodeDetails.incoming_connections.map((conn: ConnectionEdge) => (
                    <div key={conn.id} className="flex items-center gap-2 text-xs text-gray-300 py-1">
                      <ChevronRight className="w-3 h-3 text-neon-green rotate-180" />
                      <span>{conn.source}</span>
                      <span className="text-gray-500">→ :{conn.target_port}</span>
                      <span className="ml-auto text-gray-400">{conn.requests_per_sec.toFixed(0)}/s</span>
                    </div>
                  ))}
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
          <div className="space-y-1">
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
