"""
Settings Manager for Application Configuration
"""
import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manage application settings stored in ClickHouse"""
    
    def __init__(self, clickhouse_client):
        """
        Initialize settings manager
        
        Args:
            clickhouse_client: ClickHouse client instance
        """
        self.client = clickhouse_client
        self._cache = {}
        self._load_settings()
    
    def _load_settings(self):
        """Load all settings from database into cache"""
        try:
            query = """
                SELECT setting_key, setting_value
                FROM settings
                FINAL
                ORDER BY setting_key
            """
            result = self.client.execute(query)
            self._cache = {row[0]: row[1] for row in result}
            logger.info(f"Loaded {len(self._cache)} settings from database")
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            self._cache = {}
    
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a setting value
        
        Args:
            key: Setting key
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        return self._cache.get(key, default)
    
    def set_setting(self, key: str, value: str):
        """
        Set a setting value
        
        Args:
            key: Setting key
            value: Setting value
        """
        try:
            query = """
                INSERT INTO settings (setting_key, setting_value, updated_at)
                VALUES (%(key)s, %(value)s, %(updated_at)s)
            """
            self.client.execute(query, {
                'key': key,
                'value': value,
                'updated_at': datetime.now()
            })
            self._cache[key] = value
            logger.info(f"Updated setting: {key}")
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            raise
    
    def get_all_settings(self, mask_sensitive: bool = False) -> Dict[str, str]:
        """
        Get all settings
        
        Args:
            mask_sensitive: If True, mask sensitive values
            
        Returns:
            Dictionary of all settings
        """
        if not mask_sensitive:
            return self._cache.copy()
        
        # List of sensitive keys to mask
        sensitive_keys = [
            'telegram_bot_token',
            'gemini_api_key'
        ]
        
        masked = self._cache.copy()
        for key in sensitive_keys:
            if key in masked and masked[key]:
                # Mask all but last 4 characters
                value = masked[key]
                if len(value) > 4:
                    masked[key] = '*' * (len(value) - 4) + value[-4:]
                else:
                    masked[key] = '****'
        
        return masked
    
    def update_settings(self, settings: Dict[str, str]):
        """
        Batch update multiple settings
        
        Args:
            settings: Dictionary of settings to update
        """
        for key, value in settings.items():
            self.set_setting(key, value)
    
    def delete_setting(self, key: str):
        """
        Delete a setting
        
        Args:
            key: Setting key to delete
        """
        try:
            # In ClickHouse, we mark as deleted by inserting an empty value
            # ReplacingMergeTree will eventually deduplicate
            query = """
                ALTER TABLE settings DELETE WHERE setting_key = %(key)s
            """
            self.client.execute(query, {'key': key})
            if key in self._cache:
                del self._cache[key]
            logger.info(f"Deleted setting: {key}")
        except Exception as e:
            logger.error(f"Failed to delete setting {key}: {e}")
            raise
    
    def reload(self):
        """Reload settings from database"""
        self._load_settings()


# Global settings manager instance
_settings_manager: Optional[SettingsManager] = None


def init_settings_manager(clickhouse_client) -> SettingsManager:
    """
    Initialize global settings manager
    
    Args:
        clickhouse_client: ClickHouse client instance
        
    Returns:
        SettingsManager instance
    """
    global _settings_manager
    _settings_manager = SettingsManager(clickhouse_client)
    return _settings_manager


def get_settings_manager() -> Optional[SettingsManager]:
    """Get global settings manager instance"""
    return _settings_manager
