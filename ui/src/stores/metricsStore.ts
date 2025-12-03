/**
 * Zustand Store for Real-Time Metrics
 * 
 * Central state management for all metric data with efficient storage
 */

import { create } from 'zustand';
import { RingBuffer, DataPoint } from '../lib/ring-buffer';

interface MetricData {
  [server: string]: {
    [metricName: string]: RingBuffer<DataPoint>;
  };
}

interface MetricsState {
  // Data storage
  metrics: MetricData;
  
  // Connection state
  isConnected: boolean;
  lastUpdate: Date | null;
  
  // Actions
  addMetric: (server: string, metricName: string, dataPoint: DataPoint) => void;
  addMetrics: (server: string, metricName: string, dataPoints: DataPoint[]) => void;
  getMetrics: (server: string, metricName: string, limit?: number) => DataPoint[];
  clearMetrics: (server?: string) => void;
  setConnected: (connected: boolean) => void;
}

// Buffer capacity per metric (keep last 500 points = ~8 minutes at 1s interval)
const BUFFER_CAPACITY = 500;

export const useMetricsStore = create<MetricsState>((set, get) => ({
  metrics: {},
  isConnected: false,
  lastUpdate: null,
  
  addMetric: (server, metricName, dataPoint) => {
    set(state => {
      const newMetrics = { ...state.metrics };
      
      // Initialize server if not exists
      if (!newMetrics[server]) {
        newMetrics[server] = {};
      }
      
      // Initialize metric if not exists
      if (!newMetrics[server][metricName]) {
        newMetrics[server][metricName] = new RingBuffer<DataPoint>(BUFFER_CAPACITY);
      }
      
      // Add data point
      newMetrics[server][metricName].push(dataPoint);
      
      return {
        metrics: newMetrics,
        lastUpdate: new Date()
      };
    });
  },
  
  addMetrics: (server, metricName, dataPoints) => {
    set(state => {
      const newMetrics = { ...state.metrics };
      
      // Initialize server if not exists
      if (!newMetrics[server]) {
        newMetrics[server] = {};
      }
      
      // Initialize metric if not exists
      if (!newMetrics[server][metricName]) {
        newMetrics[server][metricName] = new RingBuffer<DataPoint>(BUFFER_CAPACITY);
      }
      
      // Add data points
      newMetrics[server][metricName].pushMany(dataPoints);
      
      return {
        metrics: newMetrics,
        lastUpdate: new Date()
      };
    });
  },
  
  getMetrics: (server, metricName, limit) => {
    const state = get();
    const buffer = state.metrics[server]?.[metricName];
    
    if (!buffer) {
      return [];
    }
    
    return limit ? buffer.getLast(limit) : buffer.getAll();
  },
  
  clearMetrics: (server) => {
    set(state => {
      if (server) {
        // Clear specific server
        const newMetrics = { ...state.metrics };
        delete newMetrics[server];
        return { metrics: newMetrics };
      } else {
        // Clear all
        return { metrics: {} };
      }
    });
  },
  
  setConnected: (connected) => {
    set({ isConnected: connected });
  }
}));

