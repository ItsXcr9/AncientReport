/**
 * Hook for real-time alerts via WebSocket
 */

import { useEffect } from 'react';
import { getWebSocketManager } from '../lib/websocket-manager';
import { useAlertsStore } from '../stores/alertsStore';

export function useRealtimeAlerts() {
  const addAlert = useAlertsStore(state => state.addAlert);
  
  useEffect(() => {
    // We reuse the same WebSocket manager (single connection)
    const wsManager = getWebSocketManager();
    
    // Listen for alert messages
    const unsubscribe = wsManager.onMessage((data) => {
      if (data.type === 'alert' && data.data) {
        const alertData = data.data;
        
        addAlert({
          level: alertData.level || 'warning',
          title: alertData.title || 'System Alert',
          message: alertData.message || alertData.description || '',
          server: alertData.hostname || alertData.server || 'unknown',
          metric: alertData.metric,
          value: alertData.value,
          threshold: alertData.threshold
        });
      }
    });
    
    return unsubscribe;
  }, [addAlert]);
}

