
import { useOutletContext } from 'react-router-dom';
import { SecurityDashboard } from '../components/SecurityDashboard';
import { RemediationCenter } from '../components/RemediationCenter';

interface SecurityProps {
    selectedServer: string | null;
}

export default function Security() {
  const { selectedServer } = useOutletContext<SecurityProps>();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white font-display tracking-tight mb-2">Security Center</h1>
        <p className="text-gray-400 text-sm">Threat Detection and Auto-Remediation</p>
      </div>

      {/* Security Dashboard */}
      <div>
        <SecurityDashboard selectedServer={selectedServer} />
      </div>

       {/* Auto-Remediation */}
       <div>
          <h2 className="text-lg font-semibold text-white mb-4">Auto-Remediation</h2>
          <RemediationCenter selectedServer={selectedServer} />
        </div>
    </div>
  );
}
