/**
 * Hook for real-time metrics via WebSocket
 * 
 * Connects to the shared WebSocket manager and subscribes to metric updates
 */

import { useEffect, useState } from 'react';
import { getWebSocketManager } from '../lib/websocket-manager';
import { useMetricsStore } from '../stores/metricsStore';

interface RealtimeMetricsOptions {
  enabled?: boolean;
  server?: string | null;
}

export function useRealtimeMetrics(options: RealtimeMetricsOptions = {}) {
  const { enabled = true, server } = options;
  const [isConnected, setIsConnected] = useState(false);
  const addMetric = useMetricsStore(state => state.addMetric);
  const setConnected = useMetricsStore(state => state.setConnected);
  
  useEffect(() => {
    if (!enabled) return;
    
    const wsManager = getWebSocketManager();
    
    // Handle incoming metrics
    const unsubMessage = wsManager.onMessage((data) => {
      if (data.type === 'metric' && data.data) {
        const metric = data.data;
        
        // Filter by server if specified
        if (server && metric.hostname !== server) {
          return;
        }
        
        // Add to store
        addMetric(
          metric.hostname,
          metric.metric_name,
          {
            timestamp: metric.timestamp || new Date().toISOString(),
            value: metric.value
          }
        );
      }
    });
    
    // Handle connection state
    const unsubConnect = wsManager.onConnect(() => {
      console.log('[Realtime] WebSocket connected');
      setIsConnected(true);
      setConnected(true);
    });
    
    const unsubDisconnect = wsManager.onDisconnect(() => {
      console.log('[Realtime] WebSocket disconnected');
      setIsConnected(false);
      setConnected(false);
    });
    
    // Connect
    wsManager.connect();
    
    // Cleanup
    return () => {
      unsubMessage();
      unsubConnect();
      unsubDisconnect();
    };
  }, [enabled, server, addMetric, setConnected]);
  
  return { isConnected };
}

