"""
Alert Dispatcher for AncientReport V3
Routes alerts to appropriate channels
"""

import asyncio
import logging
from typing import Dict, List, Optional
from .base import AlertChannel, ChannelConfig
from .telegram import TelegramChannel
from .slack import SlackChannel
from .email import EmailChannel
from .webhook import WebhookChannel
from ..rules_engine import Alert

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Manages alert channels and dispatches alerts to the correct destinations.
    """
    
    CHANNEL_TYPES = {
        'telegram': TelegramChannel,
        'slack': SlackChannel,
        'email': EmailChannel,
        'webhook': WebhookChannel,
    }
    
    def __init__(self):
        self.channels: Dict[str, AlertChannel] = {}
    
    def register_channel(self, name: str, config: ChannelConfig):
        """Register a notification channel"""
        channel_class = self.CHANNEL_TYPES.get(config.channel_type)
        
        if not channel_class:
            logger.error(f"Unknown channel type: {config.channel_type}")
            return
        
        channel = channel_class(config)
        
        if channel.validate_config():
            self.channels[name] = channel
            logger.info(f"Registered channel: {name} ({config.channel_type})")
        else:
            logger.error(f"Invalid config for channel: {name}")
    
    def unregister_channel(self, name: str):
        """Unregister a notification channel"""
        if name in self.channels:
            del self.channels[name]
            logger.info(f"Unregistered channel: {name}")
    
    async def dispatch(self, alert: Alert) -> Dict[str, bool]:
        """
        Dispatch alert to all specified channels.
        Returns dict mapping channel name to success status.
        """
        results = {}
        
        # Find channels to notify
        channels_to_notify = []
        for channel_name in alert.channels:
            if channel_name == 'all':
                channels_to_notify.extend(self.channels.keys())
            elif channel_name in self.channels:
                channels_to_notify.append(channel_name)
            else:
                logger.warning(f"Unknown channel in alert: {channel_name}")
        
        # Remove duplicates while preserving order
        seen = set()
        channels_to_notify = [x for x in channels_to_notify if not (x in seen or seen.add(x))]
        
        # Send to all channels concurrently
        if channels_to_notify:
            tasks = []
            for channel_name in channels_to_notify:
                channel = self.channels[channel_name]
                task = self._send_with_tracking(channel_name, channel, alert)
                tasks.append(task)
            
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for channel_name, result in zip(channels_to_notify, task_results):
                if isinstance(result, Exception):
                    logger.error(f"Error sending to {channel_name}: {result}")
                    results[channel_name] = False
                else:
                    results[channel_name] = result
        
        return results
    
    async def _send_with_tracking(
        self, 
        channel_name: str, 
        channel: AlertChannel, 
        alert: Alert
    ) -> bool:
        """Send alert and track result"""
        try:
            return await channel.send(alert)
        except Exception as e:
            logger.error(f"Channel {channel_name} error: {e}")
            return False
    
    def get_channel_status(self) -> Dict[str, Dict]:
        """Get status of all registered channels"""
        status = {}
        for name, channel in self.channels.items():
            status[name] = {
                "type": channel.channel_name,
                "enabled": channel.enabled,
                "valid": channel.validate_config(),
            }
        return status
    
    def list_available_channels(self) -> List[str]:
        """List available channel types"""
        return list(self.CHANNEL_TYPES.keys())


# Global dispatcher instance
_dispatcher: Optional[AlertDispatcher] = None


def get_dispatcher() -> AlertDispatcher:
    """Get or create the global alert dispatcher"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AlertDispatcher()
    return _dispatcher


def init_dispatcher_from_settings(settings: dict):
    """Initialize dispatcher from settings dictionary"""
    dispatcher = get_dispatcher()
    
    # Configure Telegram
    if settings.get('telegram_bot_token') and settings.get('telegram_chat_id'):
        dispatcher.register_channel('telegram', ChannelConfig(
            channel_type='telegram',
            enabled=settings.get('telegram_enabled', True),
            config={
                'bot_token': settings['telegram_bot_token'],
                'chat_id': settings['telegram_chat_id'],
            }
        ))
    
    # Configure Slack
    if settings.get('slack_webhook_url'):
        dispatcher.register_channel('slack', ChannelConfig(
            channel_type='slack',
            enabled=settings.get('slack_enabled', True),
            config={
                'webhook_url': settings['slack_webhook_url'],
            }
        ))
    
    # Configure Email
    if settings.get('email_smtp_host') and settings.get('email_to'):
        dispatcher.register_channel('email', ChannelConfig(
            channel_type='email',
            enabled=settings.get('email_enabled', True),
            config={
                'smtp_host': settings['email_smtp_host'],
                'smtp_port': settings.get('email_smtp_port', 587),
                'smtp_user': settings.get('email_smtp_user', ''),
                'smtp_password': settings.get('email_smtp_password', ''),
                'from_email': settings.get('email_from', ''),
                'to_emails': settings['email_to'].split(','),
            }
        ))
    
    # Configure custom webhooks
    for i in range(1, 4):  # Support up to 3 custom webhooks
        key = f'webhook_{i}_url'
        if settings.get(key):
            dispatcher.register_channel(f'webhook_{i}', ChannelConfig(
                channel_type='webhook',
                enabled=settings.get(f'webhook_{i}_enabled', True),
                config={
                    'url': settings[key],
                    'headers': settings.get(f'webhook_{i}_headers', {}),
                }
            ))
    
    return dispatcher
