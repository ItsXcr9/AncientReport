/**
 * Zustand Store for Real-Time Alerts
 */

import { create } from 'zustand';

export interface Alert {
  id: string;
  timestamp: Date;
  level: 'critical' | 'warning' | 'info';
  title: string;
  message: string;
  server: string;
  metric?: string;
  value?: number;
  threshold?: number;
  acknowledged: boolean;
  snoozedUntil?: Date;
}

interface AlertsState {
  alerts: Alert[];
  unreadCount: number;
  soundEnabled: boolean;
  
  // Actions
  addAlert: (alert: Omit<Alert, 'id' | 'timestamp' | 'acknowledged'>) => void;
  acknowledgeAlert: (id: string) => void;
  snoozeAlert: (id: string, minutes: number) => void;
  dismissAlert: (id: string) => void;
  clearAll: () => void;
  setSoundEnabled: (enabled: boolean) => void;
  getActiveAlerts: () => Alert[];
}

// Alert sound effects
const playAlertSound = (level: Alert['level']) => {
  if (!('AudioContext' in window)) return;
  
  const ctx = new AudioContext();
  const oscillator = ctx.createOscillator();
  const gainNode = ctx.createGain();
  
  oscillator.connect(gainNode);
  gainNode.connect(ctx.destination);
  
  // Different frequencies for different levels
  const frequency = {
    critical: 800,
    warning: 600,
    info: 400
  }[level];
  
  oscillator.frequency.value = frequency;
  oscillator.type = 'sine';
  
  gainNode.gain.setValueAtTime(0.3, ctx.currentTime);
  gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
  
  oscillator.start(ctx.currentTime);
  oscillator.stop(ctx.currentTime + 0.5);
};

export const useAlertsStore = create<AlertsState>((set, get) => ({
  alerts: [],
  unreadCount: 0,
  soundEnabled: true,
  
  addAlert: (alertData) => {
    const alert: Alert = {
      ...alertData,
      id: `alert-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(),
      acknowledged: false
    };
    
    set(state => ({
      alerts: [alert, ...state.alerts].slice(0, 100), // Keep last 100
      unreadCount: state.unreadCount + 1
    }));
    
    // Play sound if enabled
    if (get().soundEnabled && alert.level !== 'info') {
      playAlertSound(alert.level);
    }
    
    // Browser notification
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(`${alert.level.toUpperCase()}: ${alert.title}`, {
        body: alert.message,
        icon: '/favicon.ico',
        tag: alert.id
      });
    }
  },
  
  acknowledgeAlert: (id) => {
    set(state => ({
      alerts: state.alerts.map(alert =>
        alert.id === id ? { ...alert, acknowledged: true } : alert
      ),
      unreadCount: Math.max(0, state.unreadCount - 1)
    }));
  },
  
  snoozeAlert: (id, minutes) => {
    const snoozedUntil = new Date();
    snoozedUntil.setMinutes(snoozedUntil.getMinutes() + minutes);
    
    set(state => ({
      alerts: state.alerts.map(alert =>
        alert.id === id ? { ...alert, snoozedUntil, acknowledged: true } : alert
      )
    }));
  },
  
  dismissAlert: (id) => {
    set(state => ({
      alerts: state.alerts.filter(alert => alert.id !== id)
    }));
  },
  
  clearAll: () => {
    set({ alerts: [], unreadCount: 0 });
  },
  
  setSoundEnabled: (enabled) => {
    set({ soundEnabled: enabled });
  },
  
  getActiveAlerts: () => {
    const now = new Date();
    return get().alerts.filter(alert => 
      !alert.acknowledged && 
      (!alert.snoozedUntil || alert.snoozedUntil < now)
    );
  }
}));

// Request notification permission on load
if ('Notification' in window && Notification.permission === 'default') {
  Notification.requestPermission();
}

