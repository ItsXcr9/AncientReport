"""
Alert State Persistence - Survive restarts and implement flapping protection

Persists alert state to ClickHouse so alerts are not lost on container restart.
"""
import logging
import json
from datetime import datetime
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AlertState(Enum):
    """Alert states matching Prometheus alertmanager"""
    INACTIVE = "inactive"  # Alert not firing
    PENDING = "pending"    # Threshold exceeded but waiting for duration
    FIRING = "firing"      # Alert is active
    RESOLVED = "resolved"  # Alert was firing but resolved


class AlertStateEntry:
    """Represents the state of a single alert rule"""
    def __init__(
        self,
        rule_id: str,
        state: AlertState = AlertState.INACTIVE,
        pending_count: int = 0,
        started_at: Optional[datetime] = None,
        last_value: float = 0.0,
        last_evaluated: Optional[datetime] = None,
        annotations: Optional[Dict] = None
    ):
        self.rule_id = rule_id
        self.state = state
        self.pending_count = pending_count
        self.started_at = started_at
        self.last_value = last_value
        self.last_evaluated = last_evaluated or datetime.now()
        self.annotations = annotations or {}


class AlertStateManager:
    """
    Manage alert state persistence and transitions.
    
    Features:
    - Persistence to ClickHouse (survive restarts)
    - Flapping protection (require N consecutive violations)
    - State transitions with timestamps
    - Resolve detection
    """
    
    def __init__(self, clickhouse_client, pending_threshold: int = 3):
        self.client = clickhouse_client
        self.pending_threshold = pending_threshold  # Evaluations before firing
        self.states: Dict[str, AlertStateEntry] = {}
        self._loaded = False
    
    async def load_state(self):
        """Load alert states from ClickHouse on startup"""
        if self._loaded:
            return
        
        try:
            query = """
                SELECT rule_id, state, pending_count, started_at, last_value, 
                       last_evaluated, annotations
                FROM alert_state FINAL
            """
            result = self.client.client.execute(query)
            
            for row in result:
                rule_id, state, pending_count, started_at, last_value, last_evaluated, annotations = row
                
                self.states[str(rule_id)] = AlertStateEntry(
                    rule_id=str(rule_id),
                    state=AlertState(state) if state else AlertState.INACTIVE,
                    pending_count=pending_count or 0,
                    started_at=started_at,
                    last_value=last_value or 0.0,
                    last_evaluated=last_evaluated,
                    annotations=json.loads(annotations) if annotations else {}
                )
            
            self._loaded = True
            logger.info(f"✓ Loaded {len(self.states)} alert states from persistence")
            
        except Exception as e:
            logger.warning(f"Could not load alert state: {e}")
            self._loaded = True  # Don't retry on error
    
    async def save_state(self, entry: AlertStateEntry):
        """Persist a state change to ClickHouse"""
        try:
            # Use INSERT which will be merged by ReplacingMergeTree
            query = f"""
                INSERT INTO alert_state 
                    (rule_id, state, pending_count, started_at, last_value, 
                     last_evaluated, annotations, updated_at)
                VALUES (
                    toUUID('{entry.rule_id}'),
                    '{entry.state.value}',
                    {entry.pending_count},
                    {f"'{entry.started_at.strftime('%Y-%m-%d %H:%M:%S')}'" if entry.started_at else "NULL"},
                    {entry.last_value},
                    '{entry.last_evaluated.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{json.dumps(entry.annotations)}',
                    now()
                )
            """
            self.client.client.execute(query)
            logger.debug(f"Saved alert state for {entry.rule_id}: {entry.state.value}")
            
        except Exception as e:
            logger.error(f"Failed to save alert state: {e}")
    
    def get_state(self, rule_id: str) -> Optional[AlertStateEntry]:
        """Get current state for a rule"""
        return self.states.get(rule_id)
    
    async def evaluate(
        self,
        rule_id: str,
        is_violation: bool,
        current_value: float,
        annotations: Optional[Dict] = None
    ) -> tuple[AlertState, bool]:
        """
        Evaluate an alert and update state with flapping protection.
        
        Args:
            rule_id: Unique identifier for the alert rule
            is_violation: True if threshold is currently exceeded
            current_value: Current metric value
            annotations: Optional alert annotations
        
        Returns:
            Tuple of (new_state, state_changed)
        """
        await self.load_state()
        
        # Get or create state entry
        entry = self.states.get(rule_id)
        if not entry:
            entry = AlertStateEntry(rule_id=rule_id)
            self.states[rule_id] = entry
        
        old_state = entry.state
        entry.last_value = current_value
        entry.last_evaluated = datetime.now()
        if annotations:
            entry.annotations.update(annotations)
        
        state_changed = False
        
        if is_violation:
            # Threshold exceeded
            if entry.state == AlertState.INACTIVE or entry.state == AlertState.RESOLVED:
                # Start pending
                entry.state = AlertState.PENDING
                entry.pending_count = 1
                state_changed = True
                logger.debug(f"Alert {rule_id}: INACTIVE -> PENDING (1/{self.pending_threshold})")
                
            elif entry.state == AlertState.PENDING:
                # Increment pending count
                entry.pending_count += 1
                
                if entry.pending_count >= self.pending_threshold:
                    # Enough consecutive violations - fire!
                    entry.state = AlertState.FIRING
                    entry.started_at = datetime.now()
                    state_changed = True
                    logger.warning(f"🔔 Alert {rule_id}: PENDING -> FIRING (value={current_value})")
                else:
                    logger.debug(f"Alert {rule_id}: PENDING ({entry.pending_count}/{self.pending_threshold})")
                    
            elif entry.state == AlertState.FIRING:
                # Still firing, no change
                pass
                
        else:
            # No violation
            if entry.state == AlertState.PENDING:
                # Reset pending count
                entry.pending_count = 0
                entry.state = AlertState.INACTIVE
                state_changed = True
                logger.debug(f"Alert {rule_id}: PENDING -> INACTIVE (condition no longer met)")
                
            elif entry.state == AlertState.FIRING:
                # Resolve the alert
                entry.state = AlertState.RESOLVED
                state_changed = True
                logger.info(f"✓ Alert {rule_id}: FIRING -> RESOLVED (value={current_value})")
                
            elif entry.state == AlertState.RESOLVED:
                # Already resolved, move to inactive after one more cycle
                entry.state = AlertState.INACTIVE
                entry.started_at = None
                state_changed = True
        
        # Persist if state changed
        if state_changed:
            await self.save_state(entry)
        
        return entry.state, state_changed
    
    async def get_active_alerts(self) -> list[AlertStateEntry]:
        """Get all currently active (PENDING or FIRING) alerts"""
        await self.load_state()
        return [
            entry for entry in self.states.values()
            if entry.state in (AlertState.PENDING, AlertState.FIRING)
        ]
    
    async def get_all_states(self) -> Dict[str, dict]:
        """Get all states as serializable dict"""
        await self.load_state()
        return {
            rule_id: {
                'state': entry.state.value,
                'pending_count': entry.pending_count,
                'started_at': entry.started_at.isoformat() if entry.started_at else None,
                'last_value': entry.last_value,
                'last_evaluated': entry.last_evaluated.isoformat() if entry.last_evaluated else None,
            }
            for rule_id, entry in self.states.items()
        }


# Global instance
_alert_state_manager: Optional[AlertStateManager] = None


def get_alert_state_manager(client=None) -> AlertStateManager:
    """Get or create the global alert state manager"""
    global _alert_state_manager
    if _alert_state_manager is None and client is not None:
        _alert_state_manager = AlertStateManager(client)
    return _alert_state_manager


def set_alert_state_manager(manager: AlertStateManager):
    """Set the global alert state manager"""
    global _alert_state_manager
    _alert_state_manager = manager
