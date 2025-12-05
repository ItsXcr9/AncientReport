-- Settings table for storing application configuration
CREATE TABLE IF NOT EXISTS AncientReport.settings (
    setting_key String,
    setting_value String,
    category String,
    description String,
    is_encrypted Bool DEFAULT false,
    updated_at DateTime DEFAULT now(),
    updated_by String DEFAULT 'system'
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (category, setting_key)
SETTINGS index_granularity = 8192;

-- Insert default settings
INSERT INTO AncientReport.settings (setting_key, setting_value, category, description) VALUES
('telegram_bot_token', '', 'telegram', 'Telegram Bot API Token'),
('telegram_chat_id', '', 'telegram', 'Telegram Chat ID for notifications'),
('telegram_enabled', 'false', 'telegram', 'Enable/disable Telegram notifications'),
('gemini_api_key', '', 'ai', 'Google Gemini API Key'),
('gemini_model', 'gemini-2.0-flash-exp', 'ai', 'Gemini model name'),
('alert_cooldown_minutes', '30', 'alerts', 'Default alert cooldown period'),
('max_alerts_history', '100', 'alerts', 'Maximum alerts to keep in history');




