
import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { NetworkMetricsPanel } from '../components/NetworkMetricsPanel';
import { DockerContainers } from '../components/DockerContainers';
import { ContainerTopology } from '../components/ContainerTopology';
import { MonitorResultsWidget } from '../components/MonitorResultsWidget';
import { ContainerHealthchecks } from '../components/ContainerHealthchecks';
import { CPUChart } from '../components/CPUChart';
import { MemoryChart } from '../components/MemoryChart';
import { DiskIOChart } from '../components/DiskIOChart';
import { NetworkChart } from '../components/NetworkChart';
import { Server } from 'lucide-react';

interface InfrastructureProps {
    selectedServer: string | null;
    config: any;
    servers: string[];
}

export default function Infrastructure() {
  const { selectedServer, config, servers } = useOutletContext<InfrastructureProps>();
  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d'>('24h');

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white font-display tracking-tight mb-2">Infrastructure</h1>
        <p className="text-gray-400 text-sm">Containers, Topology, and Network Metrics</p>
      </div>

      {/* Network Metrics Panel */}
      <div className="rounded-xl overflow-hidden glass-card">
        <NetworkMetricsPanel selectedNode={selectedServer} />
      </div>

      {/* Docker Containers Section */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Containers</h2>
        <DockerContainers selectedServer={selectedServer} />
      </div>

       {/* Container Topology */}
       {config.features.containerTopology.enabled && (
        <div className="glass-card rounded-xl p-6">
           <h2 className="text-lg font-semibold text-white mb-4">Topology</h2>
          <ContainerTopology selectedServer={selectedServer} />
        </div>
        )}

      {/* Custom Monitors & Healthchecks Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Custom Monitors Widget */}
        <div className="lg:col-span-1">
          <MonitorResultsWidget selectedServer={selectedServer} />
        </div>
        
        {/* Container Healthchecks */}
        <div className="lg:col-span-2">
          <ContainerHealthchecks selectedServer={selectedServer} />
        </div>
      </div>

      {/* Metrics History Charts - Now always visible with time range selector */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-semibold">Metrics History</h2>
          
          {/* Time Range Selector */}
          <div className="bg-white/5 backdrop-blur-sm rounded-lg p-1 border border-white/10 flex">
            {(['1h', '6h', '24h', '7d'] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1 text-sm font-medium rounded-md transition-all ${
                  timeRange === range 
                    ? 'bg-blue-500/80 text-white shadow-sm' 
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        </div>
        
        {selectedServer ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CPUChart timeRange={timeRange} hostname={selectedServer} />
            <MemoryChart timeRange={timeRange} hostname={selectedServer} />
            <DiskIOChart timeRange={timeRange} hostname={selectedServer} />
            <NetworkChart timeRange={timeRange} hostname={selectedServer} />
          </div>
        ) : (
          <div className="space-y-12">
            {servers.map(server => (
              <div key={server} className="glass-card rounded-xl p-6">
                <h3 className="text-xl font-medium mb-4 flex items-center gap-2 text-blue-300">
                  <Server className="w-5 h-5" />
                  {server}
                </h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <CPUChart timeRange={timeRange} hostname={server} />
                  <MemoryChart timeRange={timeRange} hostname={server} />
                  <DiskIOChart timeRange={timeRange} hostname={server} />
                  <NetworkChart timeRange={timeRange} hostname={server} />
                </div>
              </div>
            ))}
            {servers.length === 0 && (
              <div className="text-center text-gray-400 py-8">
                No active servers found.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
