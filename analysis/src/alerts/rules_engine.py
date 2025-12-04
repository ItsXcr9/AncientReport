"""
Alert Rules Engine for AncientReport V3
Parse and evaluate alert conditions against metrics
"""

import re
import operator
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """A configurable alert rule"""
    id: str
    name: str
    condition: str
    severity: Severity
    channels: List[str]
    cooldown_minutes: int = 15
    enabled: bool = True


@dataclass
class Alert:
    """A triggered alert"""
    rule_id: str
    rule_name: str
    hostname: str
    severity: Severity
    message: str
    triggered_values: Dict[str, float]
    channels: List[str]


class ConditionParser:
    """
    Parse simple DSL conditions like:
    - "cpu_usage > 90"
    - "memory_usage > 80 AND disk_free < 10"
    - "network_errors > 100"
    """
    
    OPERATORS = {
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '==': operator.eq,
        '!=': operator.ne,
    }
    
    PATTERN = re.compile(
        r'(\w+)\s*(>=|<=|>|<|==|!=)\s*(\d+\.?\d*%?)'
    )
    
    @classmethod
    def parse(cls, condition: str) -> List[dict]:
        """Parse condition string into list of checks"""
        checks = []
        
        # Split by AND/OR
        parts = re.split(r'\s+(?:AND|OR)\s+', condition, flags=re.IGNORECASE)
        
        for part in parts:
            match = cls.PATTERN.match(part.strip())
            if match:
                metric_name = match.group(1)
                op_str = match.group(2)
                value_str = match.group(3)
                
                # Handle percentage
                if value_str.endswith('%'):
                    value = float(value_str[:-1])
                else:
                    value = float(value_str)
                
                checks.append({
                    'metric': metric_name,
                    'operator': cls.OPERATORS[op_str],
                    'operator_str': op_str,
                    'value': value,
                })
        
        return checks
    
    @classmethod
    def evaluate(cls, condition: str, metrics: Dict[str, float]) -> tuple[bool, Dict[str, float]]:
        """
        Evaluate condition against metrics.
        Returns (result, triggered_values)
        """
        checks = cls.parse(condition)
        
        if not checks:
            return False, {}
        
        triggered_values = {}
        is_and = ' AND ' in condition.upper()
        
        results = []
        for check in checks:
            metric_name = check['metric']
            if metric_name not in metrics:
                results.append(False)
                continue
            
            actual_value = metrics[metric_name]
            expected_value = check['value']
            op_func = check['operator']
            
            result = op_func(actual_value, expected_value)
            results.append(result)
            
            if result:
                triggered_values[metric_name] = actual_value
        
        if is_and:
            final_result = all(results)
        else:
            final_result = any(results)
        
        return final_result, triggered_values


class AlertRulesEngine:
    """Engine to evaluate alert rules against metrics"""
    
    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.cooldowns: Dict[str, float] = {}  # rule_id -> last_triggered_timestamp
        self.parser = ConditionParser()
    
    def add_rule(self, rule: AlertRule):
        """Add or update an alert rule"""
        self.rules[rule.id] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_id: str):
        """Remove an alert rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            logger.info(f"Removed alert rule: {rule_id}")
    
    def evaluate(self, hostname: str, metrics: Dict[str, float]) -> List[Alert]:
        """
        Evaluate all rules against provided metrics.
        Returns list of triggered alerts.
        """
        import time
        current_time = time.time()
        alerts = []
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Check cooldown
            cooldown_key = f"{rule.id}:{hostname}"
            last_triggered = self.cooldowns.get(cooldown_key, 0)
            if current_time - last_triggered < rule.cooldown_minutes * 60:
                continue
            
            # Evaluate condition
            try:
                triggered, values = self.parser.evaluate(rule.condition, metrics)
                
                if triggered:
                    # Create alert
                    alert = Alert(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        hostname=hostname,
                        severity=rule.severity,
                        message=self._format_message(rule, values),
                        triggered_values=values,
                        channels=rule.channels,
                    )
                    alerts.append(alert)
                    
                    # Update cooldown
                    self.cooldowns[cooldown_key] = current_time
                    
                    logger.warning(f"Alert triggered: {rule.name} on {hostname}")
                    
            except Exception as e:
                logger.error(f"Error evaluating rule {rule.name}: {e}")
        
        return alerts
    
    def _format_message(self, rule: AlertRule, values: Dict[str, float]) -> str:
        """Format alert message with triggered values"""
        value_strs = [f"{k}={v:.2f}" for k, v in values.items()]
        return f"[{rule.severity.upper()}] {rule.name}: {', '.join(value_strs)}"
    
    def get_all_rules(self) -> List[AlertRule]:
        """Get all configured rules"""
        return list(self.rules.values())


# Default rules
DEFAULT_RULES = [
    AlertRule(
        id="high_cpu",
        name="High CPU Usage",
        condition="cpu_usage > 90",
        severity=Severity.CRITICAL,
        channels=["telegram"],
        cooldown_minutes=15,
    ),
    AlertRule(
        id="high_memory",
        name="High Memory Usage",
        condition="memory_usage > 85",
        severity=Severity.WARNING,
        channels=["telegram"],
        cooldown_minutes=15,
    ),
    AlertRule(
        id="low_disk",
        name="Low Disk Space",
        condition="disk_free_percent < 10",
        severity=Severity.CRITICAL,
        channels=["telegram"],
        cooldown_minutes=60,
    ),
    AlertRule(
        id="high_load",
        name="High System Load",
        condition="load_average > 10",
        severity=Severity.WARNING,
        channels=["telegram"],
        cooldown_minutes=30,
    ),
]


def create_default_engine() -> AlertRulesEngine:
    """Create an engine with default rules"""
    engine = AlertRulesEngine()
    for rule in DEFAULT_RULES:
        engine.add_rule(rule)
    return engine
