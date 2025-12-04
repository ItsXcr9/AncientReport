"""
Slack Channel for AncientReport V3
Send alerts via Slack webhooks
"""

import aiohttp
import logging
from typing import Optional
from .base import AlertChannel, ChannelConfig
from ..rules_engine import Alert

logger = logging.getLogger(__name__)


class SlackChannel(AlertChannel):
    """Slack notification channel via webhooks"""
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.webhook_url = config.config.get('webhook_url', '')
        self.channel = config.config.get('channel', '')  # Optional override
        self.username = config.config.get('username', 'AncientReport')
        self.icon_emoji = config.config.get('icon_emoji', ':shield:')
    
    @property
    def channel_name(self) -> str:
        return "slack"
    
    def validate_config(self) -> bool:
        """Validate Slack configuration"""
        if not self.webhook_url:
            logger.error("Slack webhook_url is required")
            return False
        if not self.webhook_url.startswith('https://hooks.slack.com/'):
            logger.error("Invalid Slack webhook URL")
            return False
        return True
    
    async def send(self, alert: Alert) -> bool:
        """Send alert via Slack webhook"""
        if not self.enabled:
            return False
        
        if not self.validate_config():
            return False
        
        try:
            payload = self._build_payload(alert)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Slack alert sent: {alert.rule_name}")
                        return True
                    else:
                        logger.error(f"Slack API error: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False
    
    def _build_payload(self, alert: Alert) -> dict:
        """Build Slack message payload with blocks"""
        color = self._get_color(alert.severity)
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 {alert.rule_name}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Host:*\n{alert.hostname}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{alert.severity.upper()}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Message:*\n{alert.message}"
                }
            }
        ]
        
        if alert.triggered_values:
            fields_text = "\n".join([
                f"• {k}: `{v:.2f}`" 
                for k, v in alert.triggered_values.items()
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Triggered Values:*\n{fields_text}"
                }
            })
        
        payload = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [{
                "color": color,
                "blocks": blocks
            }]
        }
        
        if self.channel:
            payload["channel"] = self.channel
        
        return payload
    
    def _get_color(self, severity: str) -> str:
        """Get Slack attachment color based on severity"""
        colors = {
            'info': '#3498db',
            'warning': '#f39c12',
            'critical': '#e74c3c',
        }
        return colors.get(severity, '#95a5a6')
