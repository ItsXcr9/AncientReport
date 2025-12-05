import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Box, Server, Database, Radio, AlertTriangle, RefreshCw, 
  ArrowRight, X, Zap, Activity, Network, ChevronRight, Layers,
  ZoomIn, ZoomOut, Eye, EyeOff, Maximize2
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
  detected_at: string;
}

interface TopologyData {
  nodes: ContainerNode[];
  edges: ConnectionEdge[];
  problems: TopologyProblem[];
  last_updated: string;
}

interface SimulationNode extends ContainerNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
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

// Icon mapping
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

// Hierarchical layout - arranges nodes in rows by type
const calculateHierarchicalLayout = (nodes: ContainerNode[], width: number, height: number): SimulationNode[] => {
  // Categorize containers
  const categories: Record<string, ContainerNode[]> = {
    ui: [],
    api: [],
    db: [],
    mq: [],
    agent: [],
    other: []
  };

  nodes.forEach(node => {
    const name = node.name.toLowerCase();
    if (name.includes('ui') || name.includes('nginx') || name.includes('frontend') || name.includes('web') || name.includes('caddy')) {
      categories.ui.push(node);
    } else if (name.includes('analysis') || name.includes('api') || name.includes('backend') || name.includes('server') || name.includes('app')) {
      categories.api.push(node);
    } else if (name.includes('clickhouse') || name.includes('postgres') || name.includes('mysql') || name.includes('mongo') || name.includes('redis') || name.includes('elasticsearch')) {
      categories.db.push(node);
    } else if (name.includes('nats') || name.includes('kafka') || name.includes('rabbit') || name.includes('mq')) {
      categories.mq.push(node);
    } else if (name.includes('agent')) {
      categories.agent.push(node);
    } else {
      categories.other.push(node);
    }
  });

  // Define row positions (top to bottom: UI -> API -> DB/MQ -> Agent -> Other)
  const rows = [
    { key: 'ui', y: 80, label: 'UI/Frontend' },
    { key: 'api', y: 200, label: 'API/Backend' },
    { key: 'db', y: 320, label: 'Database' },
    { key: 'mq', y: 440, label: 'Message Queue' },
    { key: 'agent', y: 560, label: 'Agents' },
    { key: 'other', y: 680, label: 'Other' },
  ];

  const result: SimulationNode[] = [];
  const minSpacing = 120; // Minimum horizontal spacing between nodes

  rows.forEach(row => {
    const rowNodes = categories[row.key];
    if (rowNodes.length === 0) return;

    // Calculate horizontal positions
    const totalWidth = (rowNodes.length - 1) * minSpacing;
    const startX = (width - totalWidth) / 2;

    rowNodes.forEach((node, idx) => {
      result.push({
        ...node,
        x: startX + idx * minSpacing,
        y: row.y,
        vx: 0,
        vy: 0
      });
    });
  });

  return result;
};

interface ContainerTopologyProps {
  selectedServer: string | null;
}

export const ContainerTopology = ({ selectedServer }: ContainerTopologyProps) => {
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedNodeDetails, setSelectedNodeDetails] = useState<any>(null);
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'groups'>('graph');
  const [showLabels, setShowLabels] = useState(true);
  
  // View state
  const [zoom, setZoom] = useState(0.85);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  
  // Layout state
  const [simNodes, setSimNodes] = useState<SimulationNode[]>([]);
  
  // Canvas dimensions - much larger for 37+ containers
  const canvasWidth = 1600;
  const canvasHeight = 800;

  const fetchTopology = useCallback(async () => {
    try {
      let url = `${API_BASE}/api/v3/topology/map`;
      if (selectedServer) url += `?hostname=${selectedServer}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setTopology(data);
      }
    } catch (error) {
      console.error('Failed to fetch topology:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedServer]);

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

  // Calculate layout when topology changes
  useEffect(() => {
    if (!topology?.nodes) return;
    const layoutNodes = calculateHierarchicalLayout(topology.nodes, canvasWidth, canvasHeight);
    setSimNodes(layoutNodes);
  }, [topology]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target === svgRef.current || (e.target as Element).tagName === 'svg') {
      setIsDragging(true);
      dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const scale = e.deltaY > 0 ? 0.95 : 1.05;
    setZoom(prev => Math.min(Math.max(0.3, prev * scale), 2));
  };

  const resetView = () => {
    setZoom(0.85);
    setPan({ x: 0, y: 0 });
  };

  // Group containers by network for Groups view
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

  const getEdgePath = (sourceId: string, targetId: string) => {
    const source = simNodes.find(n => n.id === sourceId || n.name === sourceId);
    const target = simNodes.find(n => n.id === targetId || n.name === targetId);
    if (!source || !target) return null;
    
    // Calculate curved path
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    
    // Control point offset for curve
    const cpOffset = Math.min(50, dist * 0.2);
    const midX = (source.x + target.x) / 2;
    const midY = (source.y + target.y) / 2;
    
    // Perpendicular offset
    const nx = -dy / (dist || 1);
    const ny = dx / (dist || 1);
    const cpX = midX + nx * cpOffset;
    const cpY = midY + ny * cpOffset;

    // Label position on curve
    const labelX = 0.25 * source.x + 0.5 * cpX + 0.25 * target.x;
    const labelY = 0.25 * source.y + 0.5 * cpY + 0.25 * target.y;

    return {
      path: `M ${source.x} ${source.y} Q ${cpX} ${cpY} ${target.x} ${target.y}`,
      label: { x: labelX, y: labelY }
    };
  };

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
      className="glass-card p-6 rounded-xl overflow-hidden"
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
        <div className="flex items-center gap-2">
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

          {/* Graph Controls */}
          {viewMode === 'graph' && (
            <div className="flex items-center bg-white/5 rounded-lg p-1 gap-1">
              <button 
                onClick={() => setShowLabels(!showLabels)} 
                className={`p-1.5 rounded hover:bg-white/10 ${showLabels ? 'text-neon-blue' : 'text-gray-400'}`}
                title="Toggle Labels"
              >
                {showLabels ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </button>
              <div className="w-px h-4 bg-white/10" />
              <button onClick={() => setZoom(z => Math.max(0.3, z - 0.1))} className="p-1.5 hover:bg-white/10 rounded" title="Zoom Out">
                <ZoomOut className="w-4 h-4 text-gray-400" />
              </button>
              <span className="text-xs text-gray-400 w-10 text-center">{Math.round(zoom * 100)}%</span>
              <button onClick={() => setZoom(z => Math.min(2, z + 0.1))} className="p-1.5 hover:bg-white/10 rounded" title="Zoom In">
                <ZoomIn className="w-4 h-4 text-gray-400" />
              </button>
              <div className="w-px h-4 bg-white/10" />
              <button onClick={resetView} className="p-1.5 hover:bg-white/10 rounded" title="Reset View">
                <Maximize2 className="w-4 h-4 text-gray-400" />
              </button>
            </div>
          )}
          
          {problemCount > 0 && (
            <div className={`px-2 py-1 rounded-lg text-xs font-medium flex items-center gap-1 ${
              criticalCount > 0 ? 'bg-red-400/10 text-red-400' : 'bg-yellow-400/10 text-yellow-400'
            }`}>
              <AlertTriangle className="w-3 h-3" />
              {problemCount}
            </div>
          )}
          <button
            onClick={fetchTopology}
            className="p-1.5 hover:bg-white/5 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {viewMode === 'graph' ? (
        /* Graph View */
        <div 
          className="relative bg-black/40 rounded-lg border border-white/10 overflow-hidden select-none" 
          style={{ height: '700px' }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
        >
          <svg 
            ref={svgRef}
            width="100%" 
            height="100%" 
            viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
            className="cursor-grab active:cursor-grabbing"
            style={{ background: 'radial-gradient(circle at center, rgba(0,243,255,0.03) 0%, transparent 70%)' }}
          >
            <defs>
              {/* Arrow marker for connections */}
              <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
              </marker>
            </defs>
            
            <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
              {/* Row Labels */}
              <g className="row-labels" opacity="0.4">
                <text x="30" y="80" className="fill-gray-500 text-xs font-medium">UI / Frontend</text>
                <text x="30" y="200" className="fill-gray-500 text-xs font-medium">API / Backend</text>
                <text x="30" y="320" className="fill-gray-500 text-xs font-medium">Database</text>
                <text x="30" y="440" className="fill-gray-500 text-xs font-medium">Message Queue</text>
                <text x="30" y="560" className="fill-gray-500 text-xs font-medium">Agents</text>
                <text x="30" y="680" className="fill-gray-500 text-xs font-medium">Other</text>
              </g>

              {/* Connection Edges */}
              <g className="edges">
                {topology.edges.map((edge) => {
                  const isHovered = hoveredEdge === edge.id;
                  const hasProblem = topology.problems.some(p => 
                    p.source_container === edge.source && p.target === edge.target
                  );
                  
                  // Color based on latency
                  let strokeColor = '#4b5563';
                  if (hasProblem) strokeColor = '#f87171';
                  else if (edge.latency_ms < 1.0) strokeColor = '#4ade80';
                  else if (edge.latency_ms < 5.0) strokeColor = '#fbbf24';
                  else strokeColor = '#f472b6';

                  const strokeWidth = isHovered ? 3 : 1.5;
                  const opacity = isHovered ? 1 : 0.5;
                  
                  const pathData = getEdgePath(edge.source, edge.target);
                  if (!pathData) return null;

                  return (
                    <g key={edge.id}>
                      {/* Connection line */}
                      <path
                        d={pathData.path}
                        fill="none"
                        stroke={strokeColor}
                        strokeWidth={strokeWidth}
                        strokeOpacity={opacity}
                        strokeDasharray={edge.status !== 'active' ? '4,4' : undefined}
                        markerEnd="url(#arrowhead)"
                        className="transition-all duration-200 cursor-pointer"
                        onMouseEnter={() => setHoveredEdge(edge.id)}
                        onMouseLeave={() => setHoveredEdge(null)}
                      />
                      
                      {/* Latency label */}
                      {showLabels && (
                        <g transform={`translate(${pathData.label.x}, ${pathData.label.y})`}>
                          <rect 
                            x="-20" y="-8" width="40" height="16" rx="3" 
                            fill="rgba(0,0,0,0.8)"
                            stroke={strokeColor}
                            strokeWidth="0.5"
                          />
                          <text 
                            textAnchor="middle" 
                            dy="4" 
                            className="fill-white text-[9px] font-mono pointer-events-none"
                          >
                            {edge.latency_ms.toFixed(1)}ms
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </g>

              {/* Container Nodes */}
              <g className="nodes">
                {simNodes.map((node) => {
                  const colors = getHealthColor(node.health);
                  const isSelected = selectedNode === node.id;
                  const Icon = getContainerIcon(node.name);
                  const hasProblem = topology.problems.some(p => p.source_container === node.id);
                  
                  const nodeRadius = 20;
                  
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      onClick={(e) => { e.stopPropagation(); setSelectedNode(isSelected ? null : node.id); }}
                      className="cursor-pointer"
                    >
                      {/* Problem indicator */}
                      {hasProblem && (
                        <circle
                          r={nodeRadius + 6}
                          fill="none"
                          stroke="#f87171"
                          strokeWidth="2"
                          strokeDasharray="3,3"
                          className="animate-pulse"
                        />
                      )}
                      
                      {/* Selection ring */}
                      {isSelected && (
                        <circle
                          r={nodeRadius + 4}
                          fill="none"
                          stroke="#00f3ff"
                          strokeWidth="2"
                        />
                      )}
                      
                      {/* Node circle */}
                      <circle
                        r={nodeRadius}
                        fill="#0f172a"
                        stroke={colors.fill}
                        strokeWidth={2}
                      />
                      
                      {/* Icon */}
                      <foreignObject x={-10} y={-10} width={20} height={20}>
                        <div className={`w-full h-full flex items-center justify-center ${colors.text}`}>
                          <Icon className="w-4 h-4" />
                        </div>
                      </foreignObject>
                      
                      {/* Label */}
                      {showLabels && (
                        <g>
                          <rect 
                            x="-50" y={nodeRadius + 4} width="100" height="16" rx="3" 
                            fill="rgba(0,0,0,0.7)"
                          />
                          <text
                            y={nodeRadius + 15}
                            textAnchor="middle"
                            className="fill-white text-[10px] font-medium pointer-events-none"
                          >
                            {node.name.replace(/ancientreport-/i, '').replace(/^\//, '').substring(0, 15)}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </g>
            </g>
          </svg>

          {/* Edge Tooltip */}
          <AnimatePresence>
            {hoveredEdge && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-gray-900/95 border border-white/20 rounded-lg p-3 text-xs shadow-xl z-50"
              >
                {(() => {
                  const edge = topology.edges.find(e => e.id === hoveredEdge);
                  if (!edge) return null;
                  return (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-white font-medium">
                        <span className="truncate max-w-[100px]">{edge.source}</span>
                        <ArrowRight className="w-3 h-3 text-neon-blue flex-shrink-0" />
                        <span className="truncate max-w-[100px]">{edge.target}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-4 text-gray-400">
                        <div className="flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          <span>{edge.latency_ms.toFixed(1)}ms</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Activity className="w-3 h-3" />
                          <span>{edge.requests_per_sec.toFixed(0)}/s</span>
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
          
          {/* Legend */}
          <div className="absolute top-3 left-3 p-2 bg-black/60 rounded-lg border border-white/10 backdrop-blur-sm">
            <div className="text-[10px] text-gray-400 font-medium mb-1.5">Latency</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-[10px] text-gray-300">
                <div className="w-3 h-0.5 bg-green-400 rounded" /> &lt;1ms
              </div>
              <div className="flex items-center gap-2 text-[10px] text-gray-300">
                <div className="w-3 h-0.5 bg-yellow-400 rounded" /> &lt;5ms
              </div>
              <div className="flex items-center gap-2 text-[10px] text-gray-300">
                <div className="w-3 h-0.5 bg-pink-400 rounded" /> &gt;5ms
              </div>
            </div>
          </div>

          {/* Controls Hint */}
          <div className="absolute bottom-3 right-3 text-[10px] text-gray-500 bg-black/60 px-2 py-1 rounded border border-white/5">
            Scroll: zoom • Drag: pan • Click: select
          </div>
        </div>
      ) : (
        /* Groups View */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-[600px] overflow-y-auto pr-2">
          {networkGroups.map((group) => (
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
                <h4 className="font-medium text-white text-sm truncate">{group.name}</h4>
                <span className="text-xs text-gray-400 ml-auto">
                  {group.containers.length}
                </span>
              </div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {group.containers.map(container => {
                  const colors = getHealthColor(container.health);
                  const Icon = getContainerIcon(container.name);
                  
                  return (
                    <div 
                      key={container.id}
                      onClick={() => setSelectedNode(selectedNode === container.id ? null : container.id)}
                      className={`flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
                        selectedNode === container.id ? 'bg-white/20' : 'bg-white/5 hover:bg-white/10'
                      }`}
                    >
                      <div className={`p-1 rounded ${colors.bg}`}>
                        <Icon className={`w-3 h-3 ${colors.text}`} />
                      </div>
                      <span className="text-xs text-white truncate flex-1">
                        {container.name.replace(/ancientreport-/i, '').replace(/^\//, '')}
                      </span>
                      <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: colors.fill }} />
                    </div>
                  );
                })}
              </div>
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
              <h4 className="font-semibold text-white flex items-center gap-2 text-sm">
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
                <div className="text-[10px] text-gray-400">Status</div>
                <div className={`text-sm font-medium ${selectedNodeDetails.container.status === 'running' ? 'text-neon-green' : 'text-red-400'}`}>
                  {selectedNodeDetails.container.status}
                </div>
              </div>
              <div className="p-2 bg-white/5 rounded">
                <div className="text-[10px] text-gray-400">Health</div>
                <div className={`text-sm font-medium ${getHealthColor(selectedNodeDetails.container.health).text}`}>
                  {selectedNodeDetails.container.health}
                </div>
              </div>
              <div className="p-2 bg-white/5 rounded">
                <div className="text-[10px] text-gray-400">Traffic In</div>
                <div className="text-sm font-medium text-neon-green">
                  {formatBytes(selectedNodeDetails.total_bytes_in)}
                </div>
              </div>
              <div className="p-2 bg-white/5 rounded">
                <div className="text-[10px] text-gray-400">Traffic Out</div>
                <div className="text-sm font-medium text-neon-blue">
                  {formatBytes(selectedNodeDetails.total_bytes_out)}
                </div>
              </div>
            </div>

            {/* Connections */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {selectedNodeDetails.outgoing_connections?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                    <ArrowRight className="w-3 h-3" /> Outgoing ({selectedNodeDetails.outgoing_connections.length})
                  </div>
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {selectedNodeDetails.outgoing_connections.map((conn: ConnectionEdge) => (
                      <div key={conn.id} className="flex items-center gap-2 text-xs text-gray-300 p-1 bg-white/5 rounded">
                        <ChevronRight className="w-3 h-3 text-neon-blue" />
                        <span className="truncate flex-1">{conn.target}</span>
                        <span className="text-gray-500">{conn.latency_ms.toFixed(1)}ms</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selectedNodeDetails.incoming_connections?.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1 flex items-center gap-1">
                    <ArrowRight className="w-3 h-3 rotate-180" /> Incoming ({selectedNodeDetails.incoming_connections.length})
                  </div>
                  <div className="space-y-1 max-h-24 overflow-y-auto">
                    {selectedNodeDetails.incoming_connections.map((conn: ConnectionEdge) => (
                      <div key={conn.id} className="flex items-center gap-2 text-xs text-gray-300 p-1 bg-white/5 rounded">
                        <ChevronRight className="w-3 h-3 text-neon-green rotate-180" />
                        <span className="truncate flex-1">{conn.source}</span>
                        <span className="text-gray-500">{conn.requests_per_sec.toFixed(0)}/s</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ContainerTopology;
