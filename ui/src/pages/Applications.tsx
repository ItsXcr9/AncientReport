import { useOutletContext } from 'react-router-dom';
import { ContainerApps } from '../components/ContainerApps';
import { Database } from 'lucide-react';

interface ApplicationsProps {
    selectedServer: string | null;
}

export default function Applications() {
  const { selectedServer } = useOutletContext<ApplicationsProps>();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white font-display tracking-tight mb-2 flex items-center gap-3">
          <Database className="w-7 h-7 text-neon-blue" />
          Applications
        </h1>
        <p className="text-gray-400 text-sm">Kafka, Redis, and PostgreSQL container monitoring</p>
      </div>

      {/* Container Applications Monitoring */}
      <ContainerApps selectedServer={selectedServer} />
    </div>
  );
}
