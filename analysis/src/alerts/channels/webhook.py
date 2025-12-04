"""
Webhook Channel for AncientReport V3
Send alerts via generic HTTP webhooks
"""

import aiohttp
import logging
from typing import Dict, Any
from .base import AlertChannel, ChannelConfig
from ..rules_engine import Alert

logger = logging.getLogger(__name__)


class WebhookChannel(AlertChannel):
    """Generic webhook notification channel"""
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.url = config.config.get('url', '')
        self.method = config.config.get('method', 'POST').upper()
        self.headers = config.config.get('headers', {})
        self.auth_type = config.config.get('auth_type', None)  # 'bearer', 'basic'
        self.auth_token = config.config.get('auth_token', '')
        self.template = config.config.get('template', None)  # Custom JSON template
    
    @property
    def channel_name(self) -> str:
        return "webhook"
    
    def validate_config(self) -> bool:
        """Validate webhook configuration"""
        if not self.url:
            logger.error("Webhook URL is required")
            return False
        if not self.url.startswith(('http://', 'https://')):
            logger.error("Invalid webhook URL")
            return False
        return True
    
    async def send(self, alert: Alert) -> bool:
        """Send alert via webhook"""
        if not self.enabled:
            return False
        
        if not self.validate_config():
            return False
        
        try:
            payload = self._build_payload(alert)
            headers = self._build_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    self.method,
                    self.url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status < 400:
                        logger.info(f"Webhook alert sent: {alert.rule_name}")
                        return True
                    else:
                        body = await response.text()
                        logger.error(f"Webhook error {response.status}: {body[:200]}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False
    
    def _build_payload(self, alert: Alert) -> Dict[str, Any]:
        """Build webhook payload"""
        if self.template:
            # Use custom template with variable substitution
            import json
            template_str = json.dumps(self.template)
            template_str = template_str.replace("{{rule_name}}", alert.rule_name)
            template_str = template_str.replace("{{hostname}}", alert.hostname)
            template_str = template_str.replace("{{severity}}", alert.severity)
            template_str = template_str.replace("{{message}}", alert.message)
            return json.loads(template_str)
        
        # Default payload
        return {
            "alert": {
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "hostname": alert.hostname,
                "severity": alert.severity,
                "message": alert.message,
                "triggered_values": alert.triggered_values,
            },
            "source": "AncientReport",
            "version": "3.0.0",
        }
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AncientReport/3.0",
            **self.headers
        }
        
        if self.auth_type == 'bearer' and self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == 'basic' and self.auth_token:
            import base64
            encoded = base64.b64encode(self.auth_token.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        
        return headers
