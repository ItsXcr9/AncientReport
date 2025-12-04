"""
Telegram Channel for AncientReport V3
Refactored Telegram notification channel
"""

import aiohttp
import logging
from .base import AlertChannel, ChannelConfig
from ..rules_engine import Alert

logger = logging.getLogger(__name__)


class TelegramChannel(AlertChannel):
    """Telegram notification channel via Bot API"""
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.bot_token = config.config.get('bot_token', '')
        self.chat_id = config.config.get('chat_id', '')
        self.parse_mode = config.config.get('parse_mode', 'MarkdownV2')
    
    @property
    def channel_name(self) -> str:
        return "telegram"
    
    def validate_config(self) -> bool:
        """Validate Telegram configuration"""
        if not self.bot_token:
            logger.error("Telegram bot_token is required")
            return False
        if not self.chat_id:
            logger.error("Telegram chat_id is required")
            return False
        return True
    
    async def send(self, alert: Alert) -> bool:
        """Send alert via Telegram"""
        if not self.enabled:
            return False
        
        if not self.validate_config():
            return False
        
        try:
            message = self._format_message(alert)
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": self.parse_mode,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Telegram alert sent: {alert.rule_name}")
                        return True
                    else:
                        body = await response.json()
                        logger.error(f"Telegram API error: {body}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def _format_message(self, alert: Alert) -> str:
        """Format message for Telegram with MarkdownV2"""
        severity_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🚨',
        }
        
        emoji = severity_emoji.get(alert.severity, '📢')
        
        # Escape special characters for MarkdownV2
        def escape(text: str) -> str:
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in special_chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        message = f"{emoji} *{escape(alert.rule_name)}*\n\n"
        message += f"🖥️ Host: `{escape(alert.hostname)}`\n"
        message += f"⚡ Severity: *{escape(alert.severity.upper())}*\n\n"
        message += f"{escape(alert.message)}\n"
        
        if alert.triggered_values:
            message += "\n📊 *Triggered Values:*\n"
            for key, value in alert.triggered_values.items():
                message += f"  • {escape(key)}: `{value:.2f}`\n"
        
        return message
