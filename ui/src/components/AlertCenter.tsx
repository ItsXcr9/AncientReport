/**
 * Alert Center - Real-time alert notifications
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Info, XCircle, Bell, BellOff, X, Clock, CheckCircle } from 'lucide-react';
import { useAlertsStore, Alert } from '../stores/alertsStore';
import { formatDistanceToNow } from 'date-fns';

export function AlertCenter() {
  const [isOpen, setIsOpen] = useState(false);
  const alerts = useAlertsStore(state => state.alerts);
  const unreadCount = useAlertsStore(state => state.unreadCount);
  const acknowledgeAlert = useAlertsStore(state => state.acknowledgeAlert);
  const snoozeAlert = useAlertsStore(state => state.snoozeAlert);
  const dismissAlert = useAlertsStore(state => state.dismissAlert);
  const clearAll = useAlertsStore(state => state.clearAll);
  const soundEnabled = useAlertsStore(state => state.soundEnabled);
  const setSoundEnabled = useAlertsStore(state => state.setSoundEnabled);
  
  const activeAlerts = useAlertsStore(state => state.getActiveAlerts());
  
  const getAlertIcon = (level: Alert['level']) => {
    switch (level) {
      case 'critical':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      case 'info':
        return <Info className="w-5 h-5 text-blue-400" />;
    }
  };
  
  const getAlertColor = (level: Alert['level']) => {
    switch (level) {
      case 'critical':
        return 'border-red-500/30 bg-red-500/5';
      case 'warning':
        return 'border-yellow-500/30 bg-yellow-500/5';
      case 'info':
        return 'border-blue-500/30 bg-blue-500/5';
    }
  };

  return (
    <>
      {/* Alert Bell Button */}
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg hover:bg-white/10 transition-colors"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        {soundEnabled ? (
          <Bell className="w-5 h-5 text-gray-400" />
        ) : (
          <BellOff className="w-5 h-5 text-gray-500" />
        )}
        
        {unreadCount > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </motion.span>
        )}
      </motion.button>
      
      {/* Alert Panel */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 z-40"
              onClick={() => setIsOpen(false)}
            />
            
            {/* Panel */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25 }}
              className="fixed right-0 top-0 h-full w-full sm:w-96 bg-slate-900 border-l border-white/10 shadow-2xl z-50 flex flex-col"
            >
              {/* Header */}
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bell className="w-5 h-5 text-blue-400" />
                  <h2 className="text-lg font-semibold">Alerts</h2>
                  {activeAlerts.length > 0 && (
                    <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded-full">
                      {activeAlerts.length}
                    </span>
                  )}
                </div>
                
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSoundEnabled(!soundEnabled)}
                    className="p-1 hover:bg-white/10 rounded transition-colors"
                    title={soundEnabled ? 'Mute sounds' : 'Enable sounds'}
                  >
                    {soundEnabled ? (
                      <Bell className="w-4 h-4 text-gray-400" />
                    ) : (
                      <BellOff className="w-4 h-4 text-gray-500" />
                    )}
                  </button>
                  
                  <button
                    onClick={() => setIsOpen(false)}
                    className="p-1 hover:bg-white/10 rounded transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-400" />
                  </button>
                </div>
              </div>
              
              {/* Actions */}
              {alerts.length > 0 && (
                <div className="p-2 border-b border-white/10 flex gap-2">
                  <button
                    onClick={clearAll}
                    className="flex-1 px-3 py-1.5 text-xs bg-white/5 hover:bg-white/10 rounded transition-colors"
                  >
                    Clear All
                  </button>
                </div>
              )}
              
              {/* Alerts List */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                <AnimatePresence mode="popLayout">
                  {alerts.length === 0 ? (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="text-center text-gray-500 py-12"
                    >
                      <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-500/30" />
                      <p>No alerts</p>
                      <p className="text-xs mt-1">All systems operational</p>
                    </motion.div>
                  ) : (
                    alerts.map(alert => (
                      <motion.div
                        key={alert.id}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        layout
                        className={`p-4 rounded-lg border ${getAlertColor(alert.level)} ${
                          alert.acknowledged ? 'opacity-50' : ''
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          {getAlertIcon(alert.level)}
                          
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-2">
                              <h4 className="font-medium text-sm text-white">
                                {alert.title}
                              </h4>
                              <button
                                onClick={() => dismissAlert(alert.id)}
                                className="p-1 hover:bg-white/10 rounded transition-colors"
                              >
                                <X className="w-3 h-3 text-gray-400" />
                              </button>
                            </div>
                            
                            <p className="text-xs text-gray-400 mt-1">
                              {alert.message}
                            </p>
                            
                            <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
                              <span>{alert.server}</span>
                              <span>•</span>
                              <span>{formatDistanceToNow(alert.timestamp, { addSuffix: true })}</span>
                            </div>
                            
                            {!alert.acknowledged && (
                              <div className="flex gap-2 mt-3">
                                <button
                                  onClick={() => acknowledgeAlert(alert.id)}
                                  className="flex-1 px-3 py-1.5 text-xs bg-blue-500 hover:bg-blue-600 rounded transition-colors"
                                >
                                  Acknowledge
                                </button>
                                <button
                                  onClick={() => snoozeAlert(alert.id, 60)}
                                  className="px-3 py-1.5 text-xs bg-white/5 hover:bg-white/10 rounded transition-colors flex items-center gap-1"
                                  title="Snooze for 1 hour"
                                >
                                  <Clock className="w-3 h-3" />
                                  1h
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </motion.div>
                    ))
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

