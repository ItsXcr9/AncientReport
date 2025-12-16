"""
Auto-Remediation Actions Module

Executes remediation commands via MetalHive agent when alerts trigger.
"""
import os
import logging
import asyncio
import httpx
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# MetalHive API configuration
METALHIVE_API_URL = os.getenv("METALHIVE_API_URL", "http://metalhive-controller:8080")
METALHIVE_API_TIMEOUT = int(os.getenv("METALHIVE_API_TIMEOUT", "30"))

# Enable/disable auto-remediation globally
AUTO_REMEDIATION_ENABLED = os.getenv("AUTO_REMEDIATION_ENABLED", "false").lower() == "true"


# Remediation action definitions
# Format: alert_name -> { command, sudo, description, dangerous }
REMEDIATION_ACTIONS: Dict[str, Dict] = {
    # Memory remediation
    "High Memory": {
        "command": "sync && echo 3 > /proc/sys/vm/drop_caches",
        "sudo": True,
        "description": "Clear filesystem caches to free memory",
        "dangerous": False,
    },
    "Critical Memory": {
        "command": "sync && echo 3 > /proc/sys/vm/drop_caches",
        "sudo": True,
        "description": "Clear filesystem caches to free memory",
        "dangerous": False,
    },
    
    # Disk remediation
    "High Disk Usage": {
        "command": "journalctl --vacuum-time=3d && find /tmp -type f -mtime +7 -delete 2>/dev/null; find /var/log -name '*.gz' -mtime +7 -delete 2>/dev/null; echo 'Cleanup completed'",
        "sudo": True,
        "description": "Clean old logs and temp files",
        "dangerous": False,
    },
    "Critical Disk Usage": {
        "command": "journalctl --vacuum-time=1d && find /tmp -type f -mtime +1 -delete 2>/dev/null; docker system prune -f 2>/dev/null; echo 'Emergency cleanup completed'",
        "sudo": True,
        "description": "Emergency disk cleanup including Docker",
        "dangerous": True,
    },
    
    # Network remediation
    "High Close Wait": {
        "command": "ss -K state close-wait 2>/dev/null || echo 'ss -K not supported, manual intervention required'",
        "sudo": True,
        "description": "Kill stuck CLOSE_WAIT connections",
        "dangerous": False,
    },
    "Critical Close Wait": {
        "command": "ss -K state close-wait 2>/dev/null || echo 'ss -K not supported'",
        "sudo": True,
        "description": "Kill stuck CLOSE_WAIT connections",
        "dangerous": False,
    },
    "High Time Wait": {
        "command": "sysctl -w net.ipv4.tcp_tw_reuse=1 2>/dev/null && echo 'Enabled TIME_WAIT reuse'",
        "sudo": True,
        "description": "Enable TCP TIME_WAIT socket reuse",
        "dangerous": False,
    },
    
    # Open files remediation (diagnostic only - can't auto-fix safely)
    "High Open Files": {
        "command": "lsof 2>/dev/null | awk '{print $1}' | sort | uniq -c | sort -rn | head -10",
        "sudo": True,
        "description": "Report top processes by open files (diagnostic)",
        "dangerous": False,
    },
    "Critical Open Files": {
        "command": "lsof 2>/dev/null | awk '{print $1}' | sort | uniq -c | sort -rn | head -10",
        "sudo": True,
        "description": "Report top processes by open files (diagnostic)",
        "dangerous": False,
    },
    
    # Load average remediation (diagnostic - killing processes is dangerous)
    "High Load Average": {
        "command": "ps aux --sort=-%cpu | head -10",
        "sudo": False,
        "description": "Report top CPU consumers (diagnostic)",
        "dangerous": False,
    },
    "Critical Load Average": {
        "command": "ps aux --sort=-%cpu | head -10",
        "sudo": False,
        "description": "Report top CPU consumers (diagnostic)",
        "dangerous": False,
    },
}


class RemediationExecutor:
    """Executes remediation commands via MetalHive API"""
    
    def __init__(self):
        self.enabled = AUTO_REMEDIATION_ENABLED
        self.api_url = METALHIVE_API_URL
        self.timeout = METALHIVE_API_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None
        
        if self.enabled:
            logger.info(f"✓ Auto-remediation ENABLED (API: {self.api_url})")
        else:
            logger.info("Auto-remediation DISABLED (set AUTO_REMEDIATION_ENABLED=true to enable)")
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def execute_remediation(self, alert_name: str, hostname: str, alert_value: float) -> Optional[Dict]:
        """
        Execute remediation action for an alert
        
        Args:
            alert_name: Name of the triggered alert
            hostname: Target server hostname
            alert_value: Current metric value that triggered the alert
            
        Returns:
            Result dict from MetalHive API or None if no action taken
        """
        if not self.enabled:
            logger.debug(f"Auto-remediation disabled, skipping action for {alert_name}")
            return None
        
        action = REMEDIATION_ACTIONS.get(alert_name)
        if not action:
            logger.debug(f"No remediation action defined for alert: {alert_name}")
            return None
        
        # Skip dangerous actions unless explicitly enabled
        if action.get("dangerous", False):
            if os.getenv("ALLOW_DANGEROUS_REMEDIATION", "false").lower() != "true":
                logger.warning(f"⚠️ Skipping dangerous remediation for {alert_name} on {hostname}")
                return None
        
        logger.info(f"🔧 Executing remediation for '{alert_name}' on {hostname}: {action['description']}")
        
        try:
            client = await self._get_client()
            
            payload = {
                "command": action["command"],
                "nodes": [hostname],
                "sudo": action.get("sudo", False),
                "timeout_secs": self.timeout,
            }
            
            response = await client.post(
                f"{self.api_url}/api/v1/shell/run",
                json=payload,
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Remediation completed for {alert_name} on {hostname}")
                logger.debug(f"Remediation result: {result}")
                
                # Log to remediation history (could be stored in ClickHouse)
                await self._log_remediation(
                    alert_name=alert_name,
                    hostname=hostname,
                    alert_value=alert_value,
                    command=action["command"],
                    success=True,
                    result=result,
                )
                
                return result
            else:
                logger.error(f"❌ Remediation failed for {alert_name}: HTTP {response.status_code}")
                await self._log_remediation(
                    alert_name=alert_name,
                    hostname=hostname,
                    alert_value=alert_value,
                    command=action["command"],
                    success=False,
                    result={"error": f"HTTP {response.status_code}"},
                )
                return None
                
        except Exception as e:
            logger.error(f"❌ Remediation error for {alert_name} on {hostname}: {e}")
            await self._log_remediation(
                alert_name=alert_name,
                hostname=hostname,
                alert_value=alert_value,
                command=action["command"],
                success=False,
                result={"error": str(e)},
            )
            return None
    
    async def _log_remediation(
        self,
        alert_name: str,
        hostname: str,
        alert_value: float,
        command: str,
        success: bool,
        result: Dict,
    ):
        """Log remediation attempt (could be extended to store in ClickHouse)"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "alert_name": alert_name,
            "hostname": hostname,
            "alert_value": alert_value,
            "command": command,
            "success": success,
            "result": result,
        }
        
        if success:
            logger.info(f"📝 Remediation log: {log_entry}")
        else:
            logger.warning(f"📝 Remediation log (failed): {log_entry}")
    
    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Global executor instance
_executor: Optional[RemediationExecutor] = None


def get_remediation_executor() -> RemediationExecutor:
    """Get or create global remediation executor"""
    global _executor
    if _executor is None:
        _executor = RemediationExecutor()
    return _executor


async def execute_alert_remediation(alert_name: str, hostname: str, value: float) -> Optional[Dict]:
    """Convenience function to execute remediation for an alert"""
    executor = get_remediation_executor()
    return await executor.execute_remediation(alert_name, hostname, value)
