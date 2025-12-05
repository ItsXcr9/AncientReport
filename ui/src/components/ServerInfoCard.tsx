import React, { useEffect, useState } from 'react';
import { Server, Cpu, HardDrive, MemoryStick, Activity, Database } from 'lucide-react';

interface ServerInfo {
  hostname: string;
  cpu_cores: number;
  memory_total_gb: number;
  disk_total_gb: number;
  disk_free_gb: number;
}

interface ServerInfoCardProps {
  selectedServer: string | null;
}

export function ServerInfoCard({ selectedServer }: ServerInfoCardProps) {
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (selectedServer) {
      fetchServerInfo(selectedServer);
      // Refresh every hour
      const interval = setInterval(() => fetchServerInfo(selectedServer), 3600000);
      return () => clearInterval(interval);
    } else {
      setServerInfo(null);
    }
  }, [selectedServer]);

  const fetchServerInfo = async (hostname: string) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/servers/info/${hostname}`);
      if (res.ok) {
        const data = await res.json();
        setServerInfo(data);
      }
    } catch (error) {
      console.error('Failed to fetch server info:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!selectedServer) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <div className="flex items-center gap-3 mb-4">
          <Server className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold">Server Information</h3>
        </div>
        <p className="text-gray-400 text-sm">Select a server to view hardware details</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 backdrop-blur-sm">
        <div className="flex items-center justify-center py-8">
          <Activity className="w-6 h-6 animate-spin text-blue-400" />
        </div>
      </div>
    );
  }

  if (!serverInfo) {
    return null;
  }

  const usedDisk = serverInfo.disk_total_gb - serverInfo.disk_free_gb;
  const diskUsagePercent = serverInfo.disk_total_gb > 0 
    ? Math.round((usedDisk / serverInfo.disk_total_gb) * 100) 
    : 0;

  return (
    <div className="bg-gradient-to-br from-white/10 to-white/5 rounded-xl border border-white/20 p-6 backdrop-blur-sm">
      <div className="flex items-center gap-3 mb-4">
        <Server className="w-5 h-5 text-blue-400" />
        <h3 className="text-lg font-semibold">{serverInfo.hostname}</h3>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {/* CPU Cores */}
        <div className="bg-white/5 rounded-lg p-4 border border-white/10">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-gray-400">CPU Cores</span>
          </div>
          <div className="text-2xl font-bold text-purple-300">
            {serverInfo.cpu_cores}
          </div>
          <div className="text-xs text-gray-500 mt-1">cores</div>
        </div>

        {/* Memory */}
        <div className="bg-white/5 rounded-lg p-4 border border-white/10">
          <div className="flex items-center gap-2 mb-2">
            <MemoryStick className="w-4 h-4 text-green-400" />
            <span className="text-xs text-gray-400">Memory</span>
          </div>
          <div className="text-2xl font-bold text-green-300">
            {serverInfo.memory_total_gb}
          </div>
          <div className="text-xs text-gray-500 mt-1">GB RAM</div>
        </div>

        {/* Storage Total */}
        <div className="bg-white/5 rounded-lg p-4 border border-white/10">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-gray-400">Storage</span>
          </div>
          <div className="text-2xl font-bold text-blue-300">
            {serverInfo.disk_total_gb}
          </div>
          <div className="text-xs text-gray-500 mt-1">GB Total</div>
        </div>

        {/* Free Storage */}
        <div className="bg-white/5 rounded-lg p-4 border border-white/10">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-4 h-4 text-cyan-400" />
            <span className="text-xs text-gray-400">Free Space</span>
          </div>
          <div className="text-2xl font-bold text-cyan-300">
            {serverInfo.disk_free_gb}
          </div>
          <div className="text-xs text-gray-500 mt-1">GB Free ({100 - diskUsagePercent}%)</div>
          {/* Usage bar */}
          <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div 
              className={`h-full rounded-full transition-all ${
                diskUsagePercent > 90 ? 'bg-red-500' : 
                diskUsagePercent > 75 ? 'bg-orange-500' : 'bg-cyan-500'
              }`}
              style={{ width: `${diskUsagePercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
