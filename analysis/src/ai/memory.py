"""
AI Memory Module
Stores and retrieves incident knowledge for intelligent recommendations.
Enables the AI to learn from past incidents and provide better suggestions.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)


class IncidentType(str, Enum):
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    OOM_KILL = "oom_kill"
    DISK_FULL = "disk_full"
    NETWORK_LATENCY = "network_latency"
    SERVICE_DOWN = "service_down"
    CONTAINER_CRASH = "container_crash"
    HIGH_LOAD = "high_load"
    PACKET_LOSS = "packet_loss"
    UNKNOWN = "unknown"


@dataclass
class IncidentKnowledge:
    """Represents learned knowledge from a resolved incident."""
    incident_type: str
    symptoms: List[str]
    root_cause: str
    resolution: str
    context: Dict[str, Any]
    outcome: str  # "success", "partial", "failed"
    hostname: str
    learned_at: datetime
    confidence: float = 0.8


@dataclass
class Prediction:
    """Represents a prediction about future system state."""
    metric: str
    hostname: str
    predicted_value: float
    predicted_date: datetime
    confidence: float
    current_value: float
    trend: str  # "increasing", "decreasing", "stable"
    recommendation: str


class AIMemory:
    """
    AI Memory system for incident learning and pattern recognition.
    Stores successful resolutions and uses them for future recommendations.
    """
    
    # In-memory cache of recent incidents for fast lookup
    _incident_cache: Dict[str, List[IncidentKnowledge]] = {}
    _prediction_cache: Dict[str, Prediction] = {}
    
    @classmethod
    async def initialize_tables(cls):
        """Create the necessary ClickHouse tables for AI memory."""
        ch = get_clickhouse_client()
        
        try:
            # Incident knowledge table
            await ch.query("""
                CREATE TABLE IF NOT EXISTS ai_incident_knowledge (
                    id UUID DEFAULT generateUUIDv4(),
                    incident_type String,
                    symptoms Array(String),
                    root_cause String,
                    resolution String,
                    context String,
                    outcome String,
                    hostname String,
                    learned_at DateTime DEFAULT now(),
                    confidence Float32 DEFAULT 0.8
                ) ENGINE = MergeTree()
                ORDER BY (incident_type, hostname, learned_at)
            """)
            
            # Prediction history table
            await ch.query("""
                CREATE TABLE IF NOT EXISTS ai_predictions (
                    id UUID DEFAULT generateUUIDv4(),
                    metric String,
                    hostname String,
                    predicted_value Float64,
                    predicted_at DateTime DEFAULT now(),
                    prediction_for DateTime,
                    actual_value Nullable(Float64),
                    confidence Float32,
                    trend String,
                    was_accurate Nullable(UInt8)
                ) ENGINE = MergeTree()
                ORDER BY (metric, hostname, predicted_at)
            """)
            
            logger.info("✓ AI Memory tables initialized")
        except Exception as e:
            logger.warning(f"Could not create AI memory tables: {e}")
    
    @classmethod
    async def learn_from_incident(cls, knowledge: IncidentKnowledge) -> bool:
        """Store learned knowledge from a resolved incident."""
        ch = get_clickhouse_client()
        
        try:
            await ch.query(f"""
                INSERT INTO ai_incident_knowledge 
                (incident_type, symptoms, root_cause, resolution, context, outcome, hostname, confidence)
                VALUES (
                    '{knowledge.incident_type}',
                    {json.dumps(knowledge.symptoms)},
                    '{knowledge.root_cause.replace("'", "''")}',
                    '{knowledge.resolution.replace("'", "''")}',
                    '{json.dumps(knowledge.context).replace("'", "''")}',
                    '{knowledge.outcome}',
                    '{knowledge.hostname}',
                    {knowledge.confidence}
                )
            """)
            
            # Update cache
            cache_key = knowledge.incident_type
            if cache_key not in cls._incident_cache:
                cls._incident_cache[cache_key] = []
            cls._incident_cache[cache_key].append(knowledge)
            
            logger.info(f"✓ Learned from incident: {knowledge.incident_type} on {knowledge.hostname}")
            return True
        except Exception as e:
            logger.error(f"Failed to store incident knowledge: {e}")
            return False
    
    @classmethod
    async def find_similar_incidents(
        cls, 
        incident_type: str, 
        symptoms: List[str] = None,
        hostname: str = None,
        limit: int = 5
    ) -> List[IncidentKnowledge]:
        """Find similar past incidents for reference."""
        ch = get_clickhouse_client()
        
        try:
            where_clauses = [f"incident_type = '{incident_type}'"]
            if hostname:
                where_clauses.append(f"hostname = '{hostname}'")
            
            # Only get successful resolutions
            where_clauses.append("outcome = 'success'")
            
            where_sql = " AND ".join(where_clauses)
            
            result = await ch.query(f"""
                SELECT 
                    incident_type, symptoms, root_cause, resolution, 
                    context, outcome, hostname, learned_at, confidence
                FROM ai_incident_knowledge
                WHERE {where_sql}
                ORDER BY learned_at DESC, confidence DESC
                LIMIT {limit}
            """)
            
            incidents = []
            for row in result:
                incidents.append(IncidentKnowledge(
                    incident_type=row[0],
                    symptoms=row[1] if isinstance(row[1], list) else [],
                    root_cause=row[2],
                    resolution=row[3],
                    context=json.loads(row[4]) if row[4] else {},
                    outcome=row[5],
                    hostname=row[6],
                    learned_at=row[7],
                    confidence=row[8]
                ))
            
            return incidents
        except Exception as e:
            logger.error(f"Failed to find similar incidents: {e}")
            return []
    
    @classmethod
    async def get_resolution_suggestions(
        cls, 
        incident_type: str,
        current_metrics: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Get AI-informed suggestions based on past resolutions."""
        similar = await cls.find_similar_incidents(incident_type, limit=3)
        
        suggestions = []
        for incident in similar:
            suggestions.append({
                "based_on": f"Similar incident on {incident.hostname}",
                "root_cause": incident.root_cause,
                "suggested_resolution": incident.resolution,
                "confidence": incident.confidence,
                "context": incident.context
            })
        
        return suggestions
    
    @classmethod
    async def store_prediction(cls, prediction: Prediction) -> bool:
        """Store a prediction for later validation."""
        ch = get_clickhouse_client()
        
        try:
            await ch.query(f"""
                INSERT INTO ai_predictions 
                (metric, hostname, predicted_value, prediction_for, confidence, trend)
                VALUES (
                    '{prediction.metric}',
                    '{prediction.hostname}',
                    {prediction.predicted_value},
                    toDateTime('{prediction.predicted_date.strftime("%Y-%m-%d %H:%M:%S")}'),
                    {prediction.confidence},
                    '{prediction.trend}'
                )
            """)
            
            # Cache for quick access
            cache_key = f"{prediction.metric}:{prediction.hostname}"
            cls._prediction_cache[cache_key] = prediction
            
            return True
        except Exception as e:
            logger.error(f"Failed to store prediction: {e}")
            return False
    
    @classmethod
    async def validate_predictions(cls) -> Dict[str, Any]:
        """Validate past predictions against actual values."""
        ch = get_clickhouse_client()
        
        try:
            # Find predictions that should have come true by now
            result = await ch.query("""
                SELECT 
                    p.id,
                    p.metric,
                    p.hostname,
                    p.predicted_value,
                    p.prediction_for,
                    m.value as actual_value,
                    abs(p.predicted_value - m.value) as error
                FROM ai_predictions p
                LEFT JOIN metrics m ON 
                    m.metric_name = p.metric 
                    AND m.hostname = p.hostname
                    AND m.timestamp >= p.prediction_for - INTERVAL 5 MINUTE
                    AND m.timestamp <= p.prediction_for + INTERVAL 5 MINUTE
                WHERE p.prediction_for <= now()
                AND p.was_accurate IS NULL
                LIMIT 100
            """)
            
            validated = 0
            accurate = 0
            
            for row in result:
                pred_id, metric, hostname, predicted, pred_for, actual, error = row
                if actual is not None:
                    # Consider accurate if within 20% of prediction
                    is_accurate = (error / predicted) < 0.2 if predicted > 0 else error < 5
                    
                    await ch.query(f"""
                        ALTER TABLE ai_predictions 
                        UPDATE 
                            actual_value = {actual},
                            was_accurate = {1 if is_accurate else 0}
                        WHERE id = '{pred_id}'
                    """)
                    
                    validated += 1
                    if is_accurate:
                        accurate += 1
            
            accuracy = (accurate / validated * 100) if validated > 0 else 0
            
            return {
                "validated": validated,
                "accurate": accurate,
                "accuracy_percent": round(accuracy, 2)
            }
        except Exception as e:
            logger.error(f"Failed to validate predictions: {e}")
            return {"validated": 0, "accurate": 0, "accuracy_percent": 0}


class AlertCorrelator:
    """
    Correlates related alerts to reduce noise and identify root causes.
    Groups alerts by time proximity, topology, and causal relationships.
    """
    
    # Known causal relationships between metrics
    CAUSAL_GRAPH = {
        "high_cpu": ["high_load", "service_slow", "container_restart"],
        "high_memory": ["oom_kill", "swap_usage", "container_crash"],
        "disk_full": ["write_errors", "service_down", "backup_failed"],
        "network_latency": ["connection_timeout", "service_slow", "packet_loss"],
        "container_crash": ["service_down", "restart_loop"],
    }
    
    @classmethod
    async def correlate_alerts(
        cls, 
        alerts: List[Dict[str, Any]],
        time_window_seconds: int = 300
    ) -> List[Dict[str, Any]]:
        """
        Group related alerts into incidents.
        Returns list of correlated incident groups.
        """
        if not alerts:
            return []
        
        # Sort by timestamp
        sorted_alerts = sorted(alerts, key=lambda x: x.get('timestamp', ''))
        
        incidents = []
        current_incident = None
        
        for alert in sorted_alerts:
            if current_incident is None:
                current_incident = {
                    "id": f"incident_{datetime.now().timestamp()}",
                    "alerts": [alert],
                    "root_cause_candidates": [],
                    "affected_hosts": {alert.get('hostname', 'unknown')},
                    "start_time": alert.get('timestamp'),
                    "severity": alert.get('severity', 'warning')
                }
            else:
                # Check if this alert belongs to current incident
                time_diff = cls._time_difference(
                    current_incident['alerts'][-1].get('timestamp'),
                    alert.get('timestamp')
                )
                
                if time_diff <= time_window_seconds:
                    # Check for causal relationship
                    is_related = cls._is_causally_related(
                        current_incident['alerts'],
                        alert
                    )
                    
                    if is_related or cls._is_same_host(current_incident, alert):
                        current_incident['alerts'].append(alert)
                        current_incident['affected_hosts'].add(alert.get('hostname', 'unknown'))
                        
                        # Update severity to max
                        if cls._severity_rank(alert.get('severity')) > cls._severity_rank(current_incident['severity']):
                            current_incident['severity'] = alert.get('severity')
                    else:
                        # Start new incident
                        incidents.append(cls._finalize_incident(current_incident))
                        current_incident = {
                            "id": f"incident_{datetime.now().timestamp()}",
                            "alerts": [alert],
                            "root_cause_candidates": [],
                            "affected_hosts": {alert.get('hostname', 'unknown')},
                            "start_time": alert.get('timestamp'),
                            "severity": alert.get('severity', 'warning')
                        }
                else:
                    incidents.append(cls._finalize_incident(current_incident))
                    current_incident = {
                        "id": f"incident_{datetime.now().timestamp()}",
                        "alerts": [alert],
                        "root_cause_candidates": [],
                        "affected_hosts": {alert.get('hostname', 'unknown')},
                        "start_time": alert.get('timestamp'),
                        "severity": alert.get('severity', 'warning')
                    }
        
        if current_incident:
            incidents.append(cls._finalize_incident(current_incident))
        
        return incidents
    
    @classmethod
    def _finalize_incident(cls, incident: Dict) -> Dict:
        """Finalize an incident with root cause analysis."""
        incident['affected_hosts'] = list(incident['affected_hosts'])
        incident['alert_count'] = len(incident['alerts'])
        incident['end_time'] = incident['alerts'][-1].get('timestamp')
        
        # Identify potential root causes
        incident['root_cause_candidates'] = cls._find_root_causes(incident['alerts'])
        
        return incident
    
    @classmethod
    def _find_root_causes(cls, alerts: List[Dict]) -> List[str]:
        """Identify the most likely root causes based on causal graph."""
        alert_types = [a.get('alert_type', a.get('name', '')).lower() for a in alerts]
        
        root_causes = []
        for cause, effects in cls.CAUSAL_GRAPH.items():
            if cause in ' '.join(alert_types):
                # Check if any effects are also present
                effects_present = sum(1 for e in effects if e in ' '.join(alert_types))
                if effects_present > 0:
                    root_causes.append({
                        "cause": cause,
                        "confidence": min(0.9, 0.5 + (effects_present * 0.15)),
                        "affected_alerts": effects_present
                    })
        
        # Sort by confidence
        root_causes.sort(key=lambda x: x['confidence'], reverse=True)
        
        return root_causes[:3]  # Top 3 candidates
    
    @classmethod
    def _is_causally_related(cls, existing_alerts: List[Dict], new_alert: Dict) -> bool:
        """Check if new alert is causally related to existing ones."""
        new_type = new_alert.get('alert_type', new_alert.get('name', '')).lower()
        
        for alert in existing_alerts:
            alert_type = alert.get('alert_type', alert.get('name', '')).lower()
            
            # Check if new is caused by existing
            for cause, effects in cls.CAUSAL_GRAPH.items():
                if cause in alert_type and any(e in new_type for e in effects):
                    return True
                if cause in new_type and any(e in alert_type for e in effects):
                    return True
        
        return False
    
    @classmethod
    def _is_same_host(cls, incident: Dict, alert: Dict) -> bool:
        """Check if alert is from same host as incident."""
        return alert.get('hostname', 'unknown') in incident['affected_hosts']
    
    @classmethod
    def _time_difference(cls, time1: str, time2: str) -> int:
        """Calculate time difference in seconds between two ISO timestamps."""
        try:
            t1 = datetime.fromisoformat(time1.replace('Z', '+00:00'))
            t2 = datetime.fromisoformat(time2.replace('Z', '+00:00'))
            return abs((t2 - t1).total_seconds())
        except:
            return 9999  # Assume not related if can't parse
    
    @classmethod
    def _severity_rank(cls, severity: str) -> int:
        """Convert severity to numeric rank."""
        ranks = {'critical': 3, 'warning': 2, 'info': 1}
        return ranks.get(severity.lower() if severity else 'info', 1)


class PredictiveAnalytics:
    """
    Predictive analytics engine for forecasting system issues.
    Uses historical patterns and AI to predict future problems.
    """
    
    @classmethod
    async def predict_resource_exhaustion(
        cls,
        metric: str,
        hostname: str,
        threshold: float = 90.0,
        forecast_days: int = 30
    ) -> Optional[Prediction]:
        """Predict when a resource will hit critical threshold."""
        ch = get_clickhouse_client()
        
        try:
            # Get 30 days of historical data
            history = await ch.query(f"""
                SELECT 
                    toDate(timestamp) as day,
                    avg(value) as avg_value,
                    max(value) as max_value
                FROM metrics
                WHERE metric_name = '{metric}'
                AND hostname = '{hostname}'
                AND timestamp >= now() - INTERVAL 30 DAY
                GROUP BY day
                ORDER BY day
            """)
            
            if len(history) < 7:
                return None  # Not enough data
            
            # Simple linear regression for trend
            values = [float(row[1]) for row in history]
            n = len(values)
            
            # Calculate slope using least squares
            x_mean = (n - 1) / 2
            y_mean = sum(values) / n
            
            numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            
            slope = numerator / denominator if denominator != 0 else 0
            intercept = y_mean - slope * x_mean
            
            # Determine trend
            if slope > 0.5:
                trend = "increasing"
            elif slope < -0.5:
                trend = "decreasing"
            else:
                trend = "stable"
            
            # Current value and prediction
            current = values[-1]
            
            if slope <= 0:
                # Not increasing, won't hit threshold
                return Prediction(
                    metric=metric,
                    hostname=hostname,
                    predicted_value=current,
                    predicted_date=datetime.now() + timedelta(days=forecast_days),
                    confidence=0.7,
                    current_value=current,
                    trend=trend,
                    recommendation=f"{metric} is {trend}, no immediate concern"
                )
            
            # Calculate days until threshold
            days_until = (threshold - current) / slope if slope > 0 else 999
            
            if days_until > forecast_days:
                days_until = forecast_days
            
            predicted_value = min(100, current + (slope * days_until))
            predicted_date = datetime.now() + timedelta(days=days_until)
            
            # Confidence based on data quality
            confidence = min(0.9, 0.5 + (n / 60))  # Higher with more data
            
            recommendation = ""
            if days_until < 7:
                recommendation = f"CRITICAL: {metric} will exceed {threshold}% in {int(days_until)} days"
            elif days_until < 14:
                recommendation = f"WARNING: {metric} trending towards {threshold}% in ~{int(days_until)} days"
            else:
                recommendation = f"{metric} is {trend}, projected to be {predicted_value:.1f}% in {int(days_until)} days"
            
            prediction = Prediction(
                metric=metric,
                hostname=hostname,
                predicted_value=predicted_value,
                predicted_date=predicted_date,
                confidence=confidence,
                current_value=current,
                trend=trend,
                recommendation=recommendation
            )
            
            # Store for validation
            await AIMemory.store_prediction(prediction)
            
            return prediction
            
        except Exception as e:
            logger.error(f"Prediction failed for {metric}: {e}")
            return None
    
    @classmethod
    async def predict_all_resources(cls, hostname: str) -> Dict[str, Prediction]:
        """Generate predictions for all key resources."""
        metrics = [
            ("cpu_usage_percent", 80.0),
            ("memory_usage_percent", 85.0),
            ("disk_usage_percent", 90.0),
        ]
        
        predictions = {}
        for metric, threshold in metrics:
            pred = await cls.predict_resource_exhaustion(metric, hostname, threshold)
            if pred:
                predictions[metric] = asdict(pred)
                # Convert datetime to string
                predictions[metric]['predicted_date'] = pred.predicted_date.isoformat()
        
        return predictions
    
    @classmethod
    async def detect_anomaly_pattern(
        cls,
        metric: str,
        hostname: str,
        lookback_hours: int = 24
    ) -> Dict[str, Any]:
        """Detect if current values are anomalous based on historical patterns."""
        ch = get_clickhouse_client()
        
        try:
            # Get hourly pattern for the same day of week (last 4 weeks)
            current_hour = datetime.now().hour
            
            result = await ch.query(f"""
                SELECT 
                    avg(value) as mean,
                    stddevPop(value) as std,
                    min(value) as min_val,
                    max(value) as max_val
                FROM metrics
                WHERE metric_name = '{metric}'
                AND hostname = '{hostname}'
                AND toHour(timestamp) = {current_hour}
                AND toDayOfWeek(timestamp) = toDayOfWeek(now())
                AND timestamp >= now() - INTERVAL 4 WEEK
            """)
            
            if not result or not result[0][0]:
                return {"is_anomaly": False, "reason": "insufficient_data"}
            
            mean, std, min_val, max_val = result[0]
            
            # Get current value
            current = await ch.query(f"""
                SELECT avg(value)
                FROM metrics
                WHERE metric_name = '{metric}'
                AND hostname = '{hostname}'
                AND timestamp >= now() - INTERVAL 10 MINUTE
            """)
            
            if not current or not current[0][0]:
                return {"is_anomaly": False, "reason": "no_current_data"}
            
            current_val = current[0][0]
            
            # Calculate z-score
            z_score = (current_val - mean) / std if std > 0 else 0
            
            is_anomaly = abs(z_score) > 2.5  # More than 2.5 standard deviations
            
            return {
                "is_anomaly": is_anomaly,
                "current_value": round(current_val, 2),
                "expected_mean": round(mean, 2),
                "standard_deviation": round(std, 2),
                "z_score": round(z_score, 2),
                "severity": "high" if abs(z_score) > 3 else "medium" if abs(z_score) > 2.5 else "low",
                "direction": "above" if z_score > 0 else "below"
            }
            
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return {"is_anomaly": False, "error": str(e)}
