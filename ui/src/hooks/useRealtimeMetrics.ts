/**
 * Hook for real-time metrics via WebSocket
 * 
 * Connects to the shared WebSocket manager and subscribes to metric updates
 * Implements batching to reduce store updates and re-renders
 */

import { useEffect, useState, useRef } from 'react';
import { getWebSocketManager } from '../lib/websocket-manager';
import { useMetricsStore } from '../stores/metricsStore';

interface RealtimeMetricsOptions {
  enabled?: boolean;
  server?: string | null;
  batchInterval?: number;
}

export function useRealtimeMetrics(options: RealtimeMetricsOptions = {}) {
  const { enabled = true, server, batchInterval = 1000 } = options;
  const [isConnected, setIsConnected] = useState(false);
  const addMetrics = useMetricsStore(state => state.addMetrics);
  const setConnected = useMetricsStore(state => state.setConnected);
  
  // Buffer for batching updates
  const bufferRef = useRef<Map<string, Map<string, any[]>>>(new Map());
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
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
        
        // Add to buffer
        if (!bufferRef.current.has(metric.hostname)) {
          bufferRef.current.set(metric.hostname, new Map());
        }
        
        const serverMetrics = bufferRef.current.get(metric.hostname)!;
        if (!serverMetrics.has(metric.metric_name)) {
          serverMetrics.set(metric.metric_name, []);
        }
        
        serverMetrics.get(metric.metric_name)!.push({
          timestamp: metric.timestamp || new Date().toISOString(),
          value: metric.value
        });
      }
    });
    
    // Process batch periodically
    const processBatch = () => {
      if (bufferRef.current.size > 0) {
        // Iterate over servers and metrics
        bufferRef.current.forEach((metricsMap, hostname) => {
          metricsMap.forEach((points, metricName) => {
            if (points.length > 0) {
              addMetrics(hostname, metricName, points);
            }
          });
        });
        
        // Clear buffer
        bufferRef.current.clear();
      }
    };
    
    batchTimerRef.current = setInterval(processBatch, batchInterval);
    
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
      if (batchTimerRef.current) {
        clearInterval(batchTimerRef.current);
      }
    };
  }, [enabled, server, addMetrics, setConnected, batchInterval]);
  
  return { isConnected };
}

