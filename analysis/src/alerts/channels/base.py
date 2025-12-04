"""
Base Alert Channel for AncientReport V3
Abstract base class for all notification channels
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..rules_engine import Alert


@dataclass
class ChannelConfig:
    """Configuration for an alert channel"""
    channel_type: str
    enabled: bool = True
    config: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}


class AlertChannel(ABC):
    """Abstract base class for alert notification channels"""
    
    def __init__(self, config: ChannelConfig):
        self.config = config
        self.enabled = config.enabled
    
    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """
        Send an alert notification.
        Returns True if successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate that the channel configuration is correct"""
        pass
    
    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return the channel identifier"""
        pass
    
    def format_message(self, alert: Alert) -> str:
        """Default message formatting"""
        severity_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🚨',
        }
        
        emoji = severity_emoji.get(alert.severity, '📢')
        
        message = f"{emoji} **{alert.rule_name}**\n"
        message += f"Host: `{alert.hostname}`\n"
        message += f"Severity: {alert.severity.upper()}\n"
        message += f"\n{alert.message}\n"
        
        if alert.triggered_values:
            message += "\n**Triggered Values:**\n"
            for key, value in alert.triggered_values.items():
                message += f"  • {key}: {value:.2f}\n"
        
        return message
