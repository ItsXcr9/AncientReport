import { useState, useEffect, FormEvent } from 'react';
import { Settings, X, Save, Loader2, Bell, BellOff, Key } from 'lucide-react';
import { motion } from 'framer-motion';
import { useSettings } from '../hooks/useSettings';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal = ({ isOpen, onClose }: SettingsModalProps) => {
  const { settings, loading, updateSettings, updating } = useSettings();
  
  const [formData, setFormData] = useState({
    telegram_bot_token: '',
    telegram_chat_id: '',
    telegram_alerts_enabled: 'true',
    gemini_api_key: '',
  });

  const [showSuccess, setShowSuccess] = useState(false);

  // Update form data when settings are loaded
  useEffect(() => {
    if (settings) {
      setFormData({
        telegram_bot_token: settings.telegram_bot_token || '',
        telegram_chat_id: settings.telegram_chat_id || '',
        telegram_alerts_enabled: settings.telegram_alerts_enabled || 'true',
        gemini_api_key: settings.gemini_api_key || '',
      });
    }
  }, [settings]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await updateSettings(formData);
      setShowSuccess(true);
      setTimeout(() => {
        setShowSuccess(false);
        onClose();
      }, 2000);
    } catch (error) {
      console.error('Failed to save settings:', error);
    }
  };

  const toggleAlerts = () => {
    setFormData({
      ...formData,
      telegram_alerts_enabled: formData.telegram_alerts_enabled === 'true' ? 'false' : 'true',
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="relative glass-card-intense rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-neon-blue/10 rounded-lg">
              <Settings className="w-5 h-5 text-neon-blue" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-display text-white">Application Settings</h2>
              <p className="text-sm text-gray-400">Configure Telegram alerts and AI integration</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-180px)]">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-neon-blue" />
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Telegram Settings */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Bell className="w-5 h-5 text-neon-purple" />
                    Telegram Notifications
                  </h3>
                  <button
                    type="button"
                    onClick={toggleAlerts}
                    className={`px-4 py-2 rounded-lg font-medium text-sm transition-all flex items-center gap-2 ${
                      formData.telegram_alerts_enabled === 'true'
                        ? 'bg-neon-green/10 text-neon-green border border-neon-green/20'
                        : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
                    }`}
                  >
                    {formData.telegram_alerts_enabled === 'true' ? (
                      <>
                        <Bell className="w-4 h-4" />
                        Enabled
                      </>
                    ) : (
                      <>
                        <BellOff className="w-4 h-4" />
                        Disabled
                      </>
                    )}
                  </button>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Bot Token
                    </label>
                    <input
                      type="text"
                      value={formData.telegram_bot_token}
                      onChange={(e) => setFormData({ ...formData, telegram_bot_token: e.target.value })}
                      placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                      className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 focus:ring-1 focus:ring-neon-blue/50 transition-colors font-mono text-sm"
                    />
                    <p className="text-xs text-gray-500 mt-1">Get your bot token from @BotFather on Telegram</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Chat ID
                    </label>
                    <input
                      type="text"
                      value={formData.telegram_chat_id}
                      onChange={(e) => setFormData({ ...formData, telegram_chat_id: e.target.value })}
                      placeholder="123456789"
                      className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 focus:ring-1 focus:ring-neon-blue/50 transition-colors font-mono text-sm"
                    />
                    <p className="text-xs text-gray-500 mt-1">Your Telegram chat ID or channel ID</p>
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="border-t border-white/10" />

              {/* Gemini AI Settings */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Key className="w-5 h-5 text-neon-blue" />
                  Gemini AI Integration
                </h3>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    API Key
                  </label>
                  <input
                    type="password"
                    value={formData.gemini_api_key}
                    onChange={(e) => setFormData({ ...formData, gemini_api_key: e.target.value })}
                    placeholder="AIzaSy..."
                    className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-neon-blue/50 focus:ring-1 focus:ring-neon-blue/50 transition-colors font-mono text-sm"
                  />
                  <p className="text-xs text-gray-500 mt-1">Get your API key from Google AI Studio</p>
                </div>
              </div>

              {/* Success Message */}
              {showSuccess && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 bg-neon-green/10 border border-neon-green/20 rounded-lg text-neon-green flex items-center gap-2"
                >
                  <Save className="w-5 h-5" />
                  <span className="font-medium">Settings saved successfully!</span>
                </motion.div>
              )}
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-white/10">
          <button
            type="button"
            onClick={onClose}
            disabled={updating}
            className="px-4 py-2 rounded-lg text-gray-400 hover:bg-white/5 transition-colors font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={updating}
            className={`px-6 py-2 rounded-lg font-medium flex items-center gap-2 transition-all ${
              updating
                ? 'bg-white/5 text-gray-500 cursor-not-allowed'
                : 'bg-neon-blue text-white hover:bg-neon-blue/80 hover:shadow-[0_0_15px_rgba(0,243,255,0.3)]'
            }`}
          >
            {updating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Save Changes
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
};
