"""
Advanced Predictive Analytics Engine
Uses Prophet for time-series forecasting and IsolationForest for anomaly prediction.
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

# ML imports with fallbacks
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logging.warning("Prophet not available - using linear regression fallback")

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("sklearn not available - using z-score fallback")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)


@dataclass
class ResourcePrediction:
    """Prediction for resource exhaustion."""
    metric: str
    hostname: str
    current_value: float
    predicted_value: float
    predicted_date: datetime
    days_until_critical: int
    trend: str  # "increasing", "decreasing", "stable"
    confidence: float
    recommendation: str
    method: str  # "prophet", "linear_regression"


@dataclass
class AnomalyPrediction:
    """Prediction of anomaly probability."""
    metric: str
    hostname: str
    current_value: float
    anomaly_probability: float
    is_anomaly: bool
    severity: str  # "low", "medium", "high", "critical"
    direction: str  # "above_normal", "below_normal", "normal"
    z_score: float
    recommendation: str
    method: str  # "isolation_forest", "z_score"


class AdvancedPredictor:
    """
    Advanced predictive analytics using ML models.
    Falls back to statistical methods if ML libraries not available.
    """
    
    def __init__(self):
        self._prophet_models: Dict[str, Prophet] = {}
        self._isolation_forest_models: Dict[str, Tuple[IsolationForest, StandardScaler]] = {}
        
        logger.info(f"Advanced Predictor initialized - Prophet: {PROPHET_AVAILABLE}, sklearn: {SKLEARN_AVAILABLE}")
    
    async def predict_resource_exhaustion(
        self,
        metric: str,
        hostname: str,
        threshold: float = 90.0,
        forecast_days: int = 30
    ) -> Optional[ResourcePrediction]:
        """
        Predict when a resource will hit critical threshold.
        Uses Prophet if available, falls back to linear regression.
        """
        ch = get_clickhouse_client()
        
        try:
            # Get 30 days of historical data
            history = await ch.query(f"""
                SELECT 
                    toDate(timestamp) as day,
                    avg(value) as avg_value
                FROM metrics
                WHERE metric_name = '{metric}'
                AND hostname = '{hostname}'
                AND timestamp >= now() - INTERVAL 30 DAY
                GROUP BY day
                ORDER BY day
            """)
            
            if len(history) < 7:
                logger.warning(f"Insufficient data for {metric} prediction on {hostname}")
                return None
            
            if PROPHET_AVAILABLE and PANDAS_AVAILABLE:
                return await self._predict_with_prophet(
                    history, metric, hostname, threshold, forecast_days
                )
            else:
                return await self._predict_with_linear_regression(
                    history, metric, hostname, threshold, forecast_days
                )
                
        except Exception as e:
            logger.error(f"Prediction failed for {metric}: {e}")
            return None
    
    async def _predict_with_prophet(
        self,
        history: List[tuple],
        metric: str,
        hostname: str,
        threshold: float,
        forecast_days: int
    ) -> ResourcePrediction:
        """Use Prophet for sophisticated time-series forecasting."""
        import pandas as pd
        from prophet import Prophet
        
        # Prepare DataFrame for Prophet
        df = pd.DataFrame(history, columns=['ds', 'y'])
        df['ds'] = pd.to_datetime(df['ds'])
        
        # Initialize Prophet with appropriate seasonality
        model = Prophet(
            daily_seasonality=False,  # Daily data, no intra-day patterns
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05,  # Conservative: reduce overfitting
            interval_width=0.95
        )
        
        # Suppress Prophet output
        import logging
        logging.getLogger('prophet').setLevel(logging.WARNING)
        logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
        
        model.fit(df)
        
        # Generate future dates
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)
        
        # Get predictions for future only
        future_forecast = forecast[forecast['ds'] > df['ds'].max()]
        
        # Current value
        current_value = float(df['y'].iloc[-1])
        
        # Find when it crosses threshold
        critical_rows = future_forecast[future_forecast['yhat'] > threshold]
        
        if len(critical_rows) > 0:
            critical_date = critical_rows.iloc[0]['ds']
            days_until = (critical_date - datetime.now()).days
            predicted_value = float(critical_rows.iloc[0]['yhat'])
            
            if days_until <= 0:
                days_until = 1
                recommendation = f"CRITICAL: {metric} may already be exceeding {threshold}%"
            elif days_until <= 7:
                recommendation = f"URGENT: {metric} will exceed {threshold}% in {days_until} days. Take immediate action."
            elif days_until <= 14:
                recommendation = f"WARNING: {metric} trending towards {threshold}% in ~{days_until} days. Plan capacity expansion."
            else:
                recommendation = f"{metric} projected to reach {threshold}% in {days_until} days. Monitor closely."
        else:
            # Won't reach threshold in forecast period
            days_until = forecast_days
            predicted_value = float(future_forecast['yhat'].iloc[-1])
            recommendation = f"{metric} not expected to reach {threshold}% in next {forecast_days} days."
        
        # Determine trend from slope
        slope = (future_forecast['yhat'].iloc[-1] - current_value) / forecast_days
        if slope > 1:
            trend = "increasing"
        elif slope < -1:
            trend = "decreasing"
        else:
            trend = "stable"
        
        # Confidence from prediction interval width
        avg_uncertainty = (future_forecast['yhat_upper'] - future_forecast['yhat_lower']).mean()
        confidence = max(0.5, 1.0 - (avg_uncertainty / 100))
        
        return ResourcePrediction(
            metric=metric,
            hostname=hostname,
            current_value=round(current_value, 2),
            predicted_value=round(predicted_value, 2),
            predicted_date=datetime.now() + timedelta(days=days_until),
            days_until_critical=days_until,
            trend=trend,
            confidence=round(confidence, 2),
            recommendation=recommendation,
            method="prophet"
        )
    
    async def _predict_with_linear_regression(
        self,
        history: List[tuple],
        metric: str,
        hostname: str,
        threshold: float,
        forecast_days: int
    ) -> ResourcePrediction:
        """Fallback: Simple linear regression for trends."""
        values = [float(row[1]) for row in history]
        n = len(values)
        
        # Calculate slope using least squares
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean
        
        current_value = values[-1]
        
        # Determine trend
        if slope > 0.5:
            trend = "increasing"
        elif slope < -0.5:
            trend = "decreasing"
        else:
            trend = "stable"
        
        # Calculate days until threshold
        if slope <= 0:
            days_until = forecast_days
            predicted_value = current_value
            recommendation = f"{metric} is {trend}, no immediate concern."
        else:
            days_until = int((threshold - current_value) / slope) if slope > 0 else forecast_days
            days_until = min(days_until, forecast_days)
            days_until = max(days_until, 1)
            predicted_value = min(100, current_value + (slope * days_until))
            
            if days_until <= 7:
                recommendation = f"URGENT: {metric} will exceed {threshold}% in {days_until} days"
            elif days_until <= 14:
                recommendation = f"WARNING: {metric} trending towards {threshold}% in ~{days_until} days"
            else:
                recommendation = f"{metric} projected to be {predicted_value:.1f}% in {days_until} days"
        
        # Confidence based on R² (how well line fits)
        ss_res = sum((values[i] - (slope * i + intercept)) ** 2 for i in range(n))
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence = max(0.3, min(0.8, r_squared))
        
        return ResourcePrediction(
            metric=metric,
            hostname=hostname,
            current_value=round(current_value, 2),
            predicted_value=round(predicted_value, 2),
            predicted_date=datetime.now() + timedelta(days=days_until),
            days_until_critical=days_until,
            trend=trend,
            confidence=round(confidence, 2),
            recommendation=recommendation,
            method="linear_regression"
        )
    
    async def predict_anomaly(
        self,
        metric: str,
        hostname: str,
        lookback_hours: int = 168  # 1 week
    ) -> Optional[AnomalyPrediction]:
        """
        Predict if current value is anomalous.
        Uses IsolationForest if available, falls back to z-score.
        """
        ch = get_clickhouse_client()
        
        try:
            # Get historical data for the same hour/day pattern
            current_hour = datetime.now().hour
            current_dow = datetime.now().weekday()
            
            # Get data from same hour on same day of week (4 weeks)
            pattern_data = await ch.query(f"""
                SELECT value
                FROM metrics
                WHERE metric_name = '{metric}'
                AND hostname = '{hostname}'
                AND toHour(timestamp) = {current_hour}
                AND toDayOfWeek(timestamp) = {current_dow + 1}
                AND timestamp >= now() - INTERVAL 4 WEEK
                ORDER BY timestamp DESC
                LIMIT 100
            """)
            
            # Get current value
            current = await ch.query(f"""
                SELECT avg(value)
                FROM metrics
                WHERE metric_name = '{metric}'
                AND hostname = '{hostname}'
                AND timestamp >= now() - INTERVAL 10 MINUTE
            """)
            
            if not current or not current[0][0]:
                return None
            
            current_value = float(current[0][0])
            
            if len(pattern_data) < 10:
                # Not enough pattern data, get recent data instead
                recent_data = await ch.query(f"""
                    SELECT value
                    FROM metrics
                    WHERE metric_name = '{metric}'
                    AND hostname = '{hostname}'
                    AND timestamp >= now() - INTERVAL {lookback_hours} HOUR
                    ORDER BY timestamp DESC
                    LIMIT 500
                """)
                historical_values = [float(row[0]) for row in recent_data]
            else:
                historical_values = [float(row[0]) for row in pattern_data]
            
            if len(historical_values) < 5:
                return None
            
            if SKLEARN_AVAILABLE and len(historical_values) >= 20:
                return await self._predict_anomaly_isolation_forest(
                    historical_values, current_value, metric, hostname
                )
            else:
                return await self._predict_anomaly_zscore(
                    historical_values, current_value, metric, hostname
                )
                
        except Exception as e:
            logger.error(f"Anomaly prediction failed: {e}")
            return None
    
    async def _predict_anomaly_isolation_forest(
        self,
        historical_values: List[float],
        current_value: float,
        metric: str,
        hostname: str
    ) -> AnomalyPrediction:
        """Use IsolationForest for sophisticated anomaly detection."""
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
        
        # Prepare features (include rate of change, variance)
        values = np.array(historical_values).reshape(-1, 1)
        
        # Fit scaler and model
        scaler = StandardScaler()
        values_scaled = scaler.fit_transform(values)
        
        model = IsolationForest(
            contamination=0.1,  # Expect 10% anomalies
            n_estimators=100,
            random_state=42
        )
        model.fit(values_scaled)
        
        # Predict on current value
        current_scaled = scaler.transform([[current_value]])
        
        # Get anomaly score (-1 = anomaly, 1 = normal)
        prediction = model.predict(current_scaled)[0]
        score = model.decision_function(current_scaled)[0]
        
        # Convert score to probability (score is in [-0.5, 0.5] typically)
        # More negative = more anomalous
        probability = 1 - (score + 0.5)  # Convert to [0, 1] where higher = more anomalous
        probability = max(0, min(1, probability))
        
        # Calculate z-score for direction
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        z_score = (current_value - mean) / std if std > 0 else 0
        
        is_anomaly = bool(prediction == -1)  # Convert numpy.bool_ to Python bool
        
        # Determine severity
        if probability > 0.8:
            severity = "critical"
        elif probability > 0.6:
            severity = "high"
        elif probability > 0.4:
            severity = "medium"
        else:
            severity = "low"
        
        # Direction
        if z_score > 2:
            direction = "above_normal"
        elif z_score < -2:
            direction = "below_normal"
        else:
            direction = "normal"
        
        # Recommendation
        if is_anomaly:
            if z_score > 0:
                recommendation = f"{metric} is unusually HIGH ({current_value:.1f}% vs avg {mean:.1f}%). Investigate immediately."
            else:
                recommendation = f"{metric} is unusually LOW ({current_value:.1f}% vs avg {mean:.1f}%). May indicate system issues."
        else:
            recommendation = f"{metric} is within normal range ({current_value:.1f}%, avg: {mean:.1f}%)"
        
        return AnomalyPrediction(
            metric=metric,
            hostname=hostname,
            current_value=float(round(current_value, 2)),
            anomaly_probability=float(round(probability, 3)),
            is_anomaly=is_anomaly,
            severity=severity,
            direction=direction,
            z_score=float(round(z_score, 2)),
            recommendation=recommendation,
            method="isolation_forest"
        )
    
    async def _predict_anomaly_zscore(
        self,
        historical_values: List[float],
        current_value: float,
        metric: str,
        hostname: str
    ) -> AnomalyPrediction:
        """Fallback: Z-score based anomaly detection."""
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        
        z_score = (current_value - mean) / std if std > 0 else 0
        
        # Probability based on z-score (using 3-sigma rule)
        probability = min(1.0, abs(z_score) / 3.5)
        
        is_anomaly = bool(abs(z_score) > 2.5)  # Convert numpy.bool_ to Python bool
        
        # Severity
        if abs(z_score) > 4:
            severity = "critical"
        elif abs(z_score) > 3:
            severity = "high"
        elif abs(z_score) > 2.5:
            severity = "medium"
        else:
            severity = "low"
        
        # Direction
        if z_score > 2:
            direction = "above_normal"
        elif z_score < -2:
            direction = "below_normal"
        else:
            direction = "normal"
        
        if is_anomaly:
            recommendation = f"{metric} is {abs(z_score):.1f}σ {'above' if z_score > 0 else 'below'} normal ({current_value:.1f}% vs avg {mean:.1f}%)"
        else:
            recommendation = f"{metric} is within normal range"
        
        return AnomalyPrediction(
            metric=metric,
            hostname=hostname,
            current_value=float(round(current_value, 2)),
            anomaly_probability=float(round(probability, 3)),
            is_anomaly=is_anomaly,
            severity=severity,
            direction=direction,
            z_score=float(round(z_score, 2)),
            recommendation=recommendation,
            method="z_score"
        )
    
    async def get_all_predictions(self, hostname: str) -> Dict[str, Any]:
        """Get all predictions for a host."""
        metrics = [
            ("cpu_usage_percent", 80.0),
            ("memory_usage_percent", 85.0),
            ("disk_usage_percent", 90.0),
        ]
        
        result = {
            "hostname": hostname,
            "timestamp": datetime.now().isoformat(),
            "resource_predictions": {},
            "anomaly_predictions": {}
        }
        
        for metric, threshold in metrics:
            # Resource prediction
            pred = await self.predict_resource_exhaustion(metric, hostname, threshold)
            if pred:
                result["resource_predictions"][metric] = asdict(pred)
                # Convert datetime
                result["resource_predictions"][metric]["predicted_date"] = pred.predicted_date.isoformat()
            
            # Anomaly prediction
            anomaly = await self.predict_anomaly(metric, hostname)
            if anomaly:
                result["anomaly_predictions"][metric] = asdict(anomaly)
        
        return result


# Singleton instance
_predictor = None

def get_predictor() -> AdvancedPredictor:
    """Get the singleton predictor instance."""
    global _predictor
    if _predictor is None:
        _predictor = AdvancedPredictor()
    return _predictor
