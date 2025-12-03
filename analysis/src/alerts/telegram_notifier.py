"""
Telegram Bot Integration for Alert Notifications
"""
import os
import asyncio
import logging
import aiohttp
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send alerts to Telegram"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram notifier
        
        Args:
            bot_token: Telegram bot token (or use TELEGRAM_BOT_TOKEN env var)
            chat_id: Telegram chat ID (or use TELEGRAM_CHAT_ID env var)
        """
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram notifications disabled: BOT_TOKEN or CHAT_ID not configured")
        else:
            logger.info(f"Telegram notifications enabled for chat ID: {self.chat_id}")
    
    def _get_emoji(self, level: str) -> str:
        """Get emoji for alert level"""
        emoji_map = {
            'critical': '🚨',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅'
        }
        return emoji_map.get(level.lower(), '📢')
    
    def _format_message(self, alert: dict) -> str:
        """Format alert as Telegram message"""
        emoji = self._get_emoji(alert.get('level', 'info'))
        level = alert.get('level', 'INFO').upper()
        title = alert.get('title', 'System Alert')
        message = alert.get('message', 'No details provided')
        server = alert.get('hostname', alert.get('server', 'Unknown'))
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Build message
        text = f"{emoji} *{level} ALERT*\n\n"
        text += f"*{title}*\n"
        text += f"{message}\n\n"
        text += f"🖥️ Server: `{server}`\n"
        
        # Add metric details if available
        if alert.get('metric'):
            text += f"📊 Metric: `{alert['metric']}`\n"
        if alert.get('value') is not None:
            text += f"📈 Value: `{alert['value']}`\n"
        if alert.get('threshold') is not None:
            text += f"⚖️ Threshold: `{alert['threshold']}`\n"
        
        text += f"\n🕐 {timestamp}"
        
        return text
    
    async def send_alert(self, alert: dict) -> bool:
        """
        Send alert to Telegram
        
        Args:
            alert: Alert dictionary with keys: level, title, message, server, etc.
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Telegram not configured, skipping notification")
            return False
        
        try:
            message = self._format_message(alert)
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"✅ Telegram alert sent: {alert.get('title')}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Telegram API error ({response.status}): {error_text}")
                        return False
                        
        except asyncio.TimeoutError:
            logger.error("⏱️ Telegram API timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram alert: {e}")
            return False
    
    async def send_system_status(self, status: dict) -> bool:
        """
        Send system status update to Telegram
        
        Args:
            status: Dictionary with system health information
        """
        if not self.enabled:
            return False
        
        try:
            emoji = '✅' if status.get('healthy', True) else '🚨'
            text = f"{emoji} *System Status Update*\n\n"
            
            for key, value in status.items():
                if key != 'healthy':
                    text += f"• {key}: `{value}`\n"
            
            text += f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    return response.status == 200
                    
        except Exception as e:
            logger.error(f"Failed to send system status: {e}")
            return False


# Global notifier instance
_telegram_notifier: Optional[TelegramNotifier] = None


def get_telegram_notifier() -> TelegramNotifier:
    """Get or create global Telegram notifier instance"""
    global _telegram_notifier
    if _telegram_notifier is None:
        _telegram_notifier = TelegramNotifier()
    return _telegram_notifier


async def send_telegram_alert(alert: dict) -> bool:
    """
    Convenience function to send alert via Telegram
    
    Usage:
        await send_telegram_alert({
            'level': 'critical',
            'title': 'High CPU Usage',
            'message': 'CPU usage exceeded 90%',
            'server': 'xcr9',
            'metric': 'cpu_usage_percent',
            'value': 95.5,
            'threshold': 90
        })
    """
    notifier = get_telegram_notifier()
    return await notifier.send_alert(alert)

