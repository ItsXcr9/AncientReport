"""
Email Channel for AncientReport V3
Send alerts via SMTP email
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from typing import List
from .base import AlertChannel, ChannelConfig
from ..rules_engine import Alert

logger = logging.getLogger(__name__)


class EmailChannel(AlertChannel):
    """Email notification channel via SMTP"""
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.smtp_host = config.config.get('smtp_host', 'smtp.gmail.com')
        self.smtp_port = config.config.get('smtp_port', 587)
        self.smtp_user = config.config.get('smtp_user', '')
        self.smtp_password = config.config.get('smtp_password', '')
        self.from_email = config.config.get('from_email', '')
        self.to_emails: List[str] = config.config.get('to_emails', [])
        self.use_tls = config.config.get('use_tls', True)
    
    @property
    def channel_name(self) -> str:
        return "email"
    
    def validate_config(self) -> bool:
        """Validate email configuration"""
        if not self.smtp_host:
            logger.error("SMTP host is required")
            return False
        if not self.smtp_user or not self.smtp_password:
            logger.error("SMTP credentials are required")
            return False
        if not self.to_emails:
            logger.error("At least one recipient email is required")
            return False
        return True
    
    async def send(self, alert: Alert) -> bool:
        """Send alert via email"""
        if not self.enabled:
            return False
        
        if not self.validate_config():
            return False
        
        try:
            message = self._build_message(alert)
            
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=self.use_tls,
            )
            
            logger.info(f"Email alert sent: {alert.rule_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    def _build_message(self, alert: Alert) -> MIMEMultipart:
        """Build email message"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[{alert.severity.upper()}] {alert.rule_name} - {alert.hostname}"
        msg['From'] = self.from_email
        msg['To'] = ', '.join(self.to_emails)
        
        # Plain text version
        text_content = self._build_text(alert)
        msg.attach(MIMEText(text_content, 'plain'))
        
        # HTML version
        html_content = self._build_html(alert)
        msg.attach(MIMEText(html_content, 'html'))
        
        return msg
    
    def _build_text(self, alert: Alert) -> str:
        """Build plain text email body"""
        text = f"""
AncientReport Alert

Rule: {alert.rule_name}
Host: {alert.hostname}
Severity: {alert.severity.upper()}

{alert.message}

Triggered Values:
"""
        for key, value in alert.triggered_values.items():
            text += f"  - {key}: {value:.2f}\n"
        
        return text
    
    def _build_html(self, alert: Alert) -> str:
        """Build HTML email body"""
        color = self._get_color(alert.severity)
        
        values_html = "".join([
            f"<tr><td>{k}</td><td><strong>{v:.2f}</strong></td></tr>"
            for k, v in alert.triggered_values.items()
        ])
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ background: white; border-radius: 8px; padding: 20px; max-width: 600px; margin: 0 auto; }}
        .header {{ background: {color}; color: white; padding: 15px; border-radius: 8px 8px 0 0; margin: -20px -20px 20px -20px; }}
        .severity {{ display: inline-block; background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 4px; font-size: 12px; }}
        .host {{ color: #666; margin-bottom: 10px; }}
        .message {{ background: #f9f9f9; padding: 15px; border-radius: 4px; margin: 15px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px; border-bottom: 1px solid #eee; }}
        .footer {{ margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">🚨 {alert.rule_name}</h2>
            <span class="severity">{alert.severity.upper()}</span>
        </div>
        
        <div class="host">
            <strong>Host:</strong> {alert.hostname}
        </div>
        
        <div class="message">
            {alert.message}
        </div>
        
        <h4>Triggered Values</h4>
        <table>
            {values_html}
        </table>
        
        <div class="footer">
            Sent by AncientReport V3 Monitoring
        </div>
    </div>
</body>
</html>
"""
    
    def _get_color(self, severity: str) -> str:
        """Get color based on severity"""
        colors = {
            'info': '#3498db',
            'warning': '#f39c12',
            'critical': '#e74c3c',
        }
        return colors.get(severity, '#95a5a6')
