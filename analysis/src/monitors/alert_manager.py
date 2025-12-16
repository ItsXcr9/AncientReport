"""
Comprehensive Alert Manager - Store alerts in DB and send to Telegram

All alerts are:
1. Stored in ClickHouse for dashboard display
2. Sent to Telegram if configured
3. Deduplicated to prevent spam
"""
import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

# In-memory deduplication cache (alert_id -> last_sent_time)
_sent_alerts: Dict[str, datetime] = {}
ALERT_COOLDOWN_MINUTES = 5  # Don't resend same alert within 5 minutes


async def store_alert_to_db(client, alert: Dict) -> bool:
    """Store alert in ClickHouse for dashboard display"""
    try:
        rule_name = alert.get("message", "Unknown Alert")[:200].replace("'", "''")
        value = float(alert.get("value", 0)) if isinstance(alert.get("value"), (int, float)) else 0
        threshold = float(alert.get("threshold", 0)) if isinstance(alert.get("threshold"), (int, float)) else 0
        
        query = f"""
            INSERT INTO metric_alert_history (
                id, rule_id, rule_name, triggered_at, value, threshold, status, notified
            ) VALUES (
                generateUUIDv4(),
                generateUUIDv4(),
                '{rule_name}',
                now(),
                {value},
                {threshold},
                'firing',
                0
            )
        """
        
        client.client.execute(query)
        logger.debug(f"Stored alert in DB: {alert.get('message', '')[:50]}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store alert in DB: {e}")
        return False


async def send_alert_telegram(alert: Dict) -> bool:
    """Send alert to Telegram"""
    try:
        from alerts.telegram_notifier import send_telegram_alert, get_telegram_notifier
        
        notifier = get_telegram_notifier()
        if not notifier or not notifier.enabled:
            logger.debug("Telegram not configured, skipping")
            return False
        
        return await send_telegram_alert(alert)
        
    except ImportError:
        logger.debug("Telegram notifier not available")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


def should_send_alert(alert_id: str) -> bool:
    """Check if we should send this alert (deduplication)"""
    global _sent_alerts
    
    now = datetime.now()
    
    # Clean old entries
    cutoff = now - timedelta(minutes=ALERT_COOLDOWN_MINUTES * 2)
    _sent_alerts = {k: v for k, v in _sent_alerts.items() if v > cutoff}
    
    # Check if already sent recently
    last_sent = _sent_alerts.get(alert_id)
    if last_sent and (now - last_sent) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
        return False
    
    _sent_alerts[alert_id] = now
    return True


async def trigger_alert(client, alert: Dict) -> bool:
    """
    Main alert trigger function - stores in DB and sends to Telegram.
    
    Args:
        client: ClickHouse client
        alert: Alert dict with keys: id, severity, hostname, metric_name, message, value, threshold
    
    Returns:
        True if alert was processed (may have been deduplicated)
    """
    alert_id = alert.get('id', str(hash(json.dumps(alert, default=str))))
    
    # Deduplication check
    if not should_send_alert(alert_id):
        logger.debug(f"Alert deduplicated: {alert_id}")
        return True
    
    # Store in database for dashboard
    await store_alert_to_db(client, alert)
    
    # Send to Telegram
    await send_alert_telegram(alert)
    
    logger.info(f"🔔 Alert triggered: {alert.get('message', 'Unknown')[:100]}")
    return True


async def trigger_alerts_batch(client, alerts: list) -> int:
    """Trigger multiple alerts efficiently"""
    count = 0
    for alert in alerts:
        if await trigger_alert(client, alert):
            count += 1
    return count
