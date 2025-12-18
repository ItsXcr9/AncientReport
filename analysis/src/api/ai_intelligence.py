"""
AI Intelligence API
Provides endpoints for AI memory, alert correlation, and predictive analytics.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from ai.memory import AIMemory, AlertCorrelator, PredictiveAnalytics, IncidentKnowledge
from storage.clickhouse_client import get_clickhouse_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/ai/intelligence")


# ==================== Request/Response Models ====================

class LearnIncidentRequest(BaseModel):
    incident_type: str
    symptoms: List[str]
    root_cause: str
    resolution: str
    hostname: str
    context: Optional[Dict[str, Any]] = {}
    outcome: str = "success"


class FindSimilarRequest(BaseModel):
    incident_type: str
    hostname: Optional[str] = None
    symptoms: Optional[List[str]] = None


class CorrelateAlertsRequest(BaseModel):
    alerts: List[Dict[str, Any]]
    time_window_seconds: int = 300


class PredictionRequest(BaseModel):
    metric: str
    hostname: str
    threshold: Optional[float] = 90.0
    forecast_days: Optional[int] = 30


# ==================== Endpoints ====================

@router.post("/learn")
async def learn_from_incident(request: LearnIncidentRequest):
    """
    Store knowledge from a resolved incident for future reference.
    This helps the AI provide better recommendations in the future.
    """
    knowledge = IncidentKnowledge(
        incident_type=request.incident_type,
        symptoms=request.symptoms,
        root_cause=request.root_cause,
        resolution=request.resolution,
        context=request.context,
        outcome=request.outcome,
        hostname=request.hostname,
        learned_at=datetime.now()
    )
    
    success = await AIMemory.learn_from_incident(knowledge)
    
    if success:
        return {
            "status": "learned",
            "message": f"Stored resolution for {request.incident_type} on {request.hostname}"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to store incident knowledge")


@router.post("/similar")
async def find_similar_incidents(request: FindSimilarRequest):
    """
    Find similar past incidents and their resolutions.
    Useful for getting suggestions when facing a new incident.
    """
    incidents = await AIMemory.find_similar_incidents(
        incident_type=request.incident_type,
        hostname=request.hostname,
        symptoms=request.symptoms
    )
    
    return {
        "count": len(incidents),
        "incidents": [
            {
                "incident_type": i.incident_type,
                "hostname": i.hostname,
                "root_cause": i.root_cause,
                "resolution": i.resolution,
                "confidence": i.confidence,
                "learned_at": i.learned_at.isoformat() if i.learned_at else None
            }
            for i in incidents
        ]
    }


@router.post("/suggestions")
async def get_resolution_suggestions(request: FindSimilarRequest):
    """
    Get AI-informed resolution suggestions for an incident type.
    """
    suggestions = await AIMemory.get_resolution_suggestions(
        incident_type=request.incident_type
    )
    
    return {
        "incident_type": request.incident_type,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions)
    }


@router.post("/correlate")
async def correlate_alerts(request: CorrelateAlertsRequest):
    """
    Correlate related alerts into incidents.
    Reduces alert noise by grouping related alerts and identifying root causes.
    
    Example input:
    {
        "alerts": [
            {"name": "high_cpu", "hostname": "web-1", "timestamp": "2024-12-18T10:00:00Z"},
            {"name": "service_slow", "hostname": "web-1", "timestamp": "2024-12-18T10:01:00Z"}
        ],
        "time_window_seconds": 300
    }
    """
    incidents = await AlertCorrelator.correlate_alerts(
        alerts=request.alerts,
        time_window_seconds=request.time_window_seconds
    )
    
    return {
        "original_alert_count": len(request.alerts),
        "incident_count": len(incidents),
        "reduction_percent": round((1 - len(incidents) / max(1, len(request.alerts))) * 100, 1),
        "incidents": incidents
    }


@router.get("/correlate/recent")
async def correlate_recent_alerts(hours: int = 24, time_window: int = 300):
    """
    Fetch recent alerts and correlate them into incidents.
    """
    ch = get_clickhouse_client()
    
    try:
        # Fetch recent alerts from ClickHouse
        result = await ch.query(f"""
            SELECT 
                rule_name,
                hostname,
                toString(severity),
                if(resolved, 'resolved', 'firing'),
                toString(timestamp)
            FROM alert_history
            WHERE timestamp >= now() - INTERVAL {hours} HOUR
            ORDER BY timestamp
            LIMIT 500
        """)
        
        alerts = [
            {"name": row[0], "hostname": row[1], "severity": row[2], 
             "state": row[3], "timestamp": row[4]}
            for row in result
        ]
        
        incidents = await AlertCorrelator.correlate_alerts(alerts, time_window)
        
        return {
            "hours_analyzed": hours,
            "total_alerts": len(alerts),
            "incidents": incidents,
            "incident_count": len(incidents)
        }
    except Exception as e:
        logger.error(f"Failed to correlate recent alerts: {e}")
        return {
            "hours_analyzed": hours,
            "total_alerts": 0,
            "incidents": [],
            "error": str(e)
        }


@router.post("/predict")
async def predict_resource_exhaustion(request: PredictionRequest):
    """
    Predict when a resource will hit critical threshold.
    Uses historical data to forecast future values.
    """
    prediction = await PredictiveAnalytics.predict_resource_exhaustion(
        metric=request.metric,
        hostname=request.hostname,
        threshold=request.threshold,
        forecast_days=request.forecast_days
    )
    
    if prediction:
        return {
            "metric": prediction.metric,
            "hostname": prediction.hostname,
            "current_value": round(prediction.current_value, 2),
            "predicted_value": round(prediction.predicted_value, 2),
            "predicted_date": prediction.predicted_date.isoformat(),
            "confidence": prediction.confidence,
            "trend": prediction.trend,
            "recommendation": prediction.recommendation
        }
    else:
        return {
            "metric": request.metric,
            "hostname": request.hostname,
            "error": "Insufficient data for prediction",
            "minimum_required": "7 days of historical data"
        }


@router.get("/predict/{hostname}")
async def predict_all_resources_for_host(hostname: str):
    """
    Get predictions for all key resources on a host.
    """
    predictions = await PredictiveAnalytics.predict_all_resources(hostname)
    
    return {
        "hostname": hostname,
        "predictions": predictions,
        "prediction_count": len(predictions)
    }


@router.get("/anomaly/{hostname}/{metric}")
async def detect_anomaly(hostname: str, metric: str, lookback_hours: int = 24):
    """
    Check if current metric value is anomalous compared to historical patterns.
    """
    result = await PredictiveAnalytics.detect_anomaly_pattern(
        metric=metric,
        hostname=hostname,
        lookback_hours=lookback_hours
    )
    
    return {
        "hostname": hostname,
        "metric": metric,
        **result
    }


@router.get("/anomaly/{hostname}")
async def detect_all_anomalies(hostname: str):
    """
    Check all key metrics for anomalies on a host.
    """
    metrics = ["cpu_usage_percent", "memory_usage_percent", "disk_usage_percent"]
    
    anomalies = []
    for metric in metrics:
        result = await PredictiveAnalytics.detect_anomaly_pattern(metric, hostname)
        if result.get("is_anomaly"):
            anomalies.append({
                "metric": metric,
                **result
            })
    
    return {
        "hostname": hostname,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "all_metrics_checked": metrics
    }


@router.get("/validate-predictions")
async def validate_predictions():
    """
    Validate past predictions against actual values.
    Returns accuracy metrics for the prediction system.
    """
    result = await AIMemory.validate_predictions()
    return {
        "validation_result": result,
        "message": f"Validated {result['validated']} predictions with {result['accuracy_percent']}% accuracy"
    }


@router.get("/status")
async def get_intelligence_status():
    """
    Get status of the AI Intelligence system.
    """
    ch = get_clickhouse_client()
    
    stats = {
        "incident_knowledge_count": 0,
        "prediction_count": 0,
        "tables_exist": False
    }
    
    try:
        # Check if tables exist and get counts
        result = await ch.query("""
            SELECT 
                (SELECT count() FROM ai_incident_knowledge) as incidents,
                (SELECT count() FROM ai_predictions) as predictions
        """)
        if result:
            stats["incident_knowledge_count"] = result[0][0]
            stats["prediction_count"] = result[0][1]
            stats["tables_exist"] = True
    except Exception as e:
        # Tables might not exist yet
        stats["error"] = str(e)
        stats["tables_exist"] = False
    
    return {
        "status": "operational" if stats["tables_exist"] else "tables_not_initialized",
        "statistics": stats,
        "features": [
            "incident_learning",
            "alert_correlation",
            "resource_prediction",
            "anomaly_detection"
        ]
    }


@router.post("/initialize")
async def initialize_tables():
    """
    Initialize the AI memory tables in ClickHouse.
    Call this once to set up the necessary database tables.
    """
    try:
        await AIMemory.initialize_tables()
        return {"status": "initialized", "message": "AI Memory tables created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize tables: {e}")


# ==================== Advanced ML Predictions ====================

@router.get("/ml/predict/{hostname}")
async def advanced_ml_prediction(hostname: str):
    """
    Get advanced ML-powered predictions using Prophet and IsolationForest.
    Falls back to statistical methods if ML libraries unavailable.
    """
    try:
        from ai.predictor import get_predictor
        predictor = get_predictor()
        
        result = await predictor.get_all_predictions(hostname)
        return result
    except Exception as e:
        logger.error(f"Advanced ML prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ml/predict/resource")
async def ml_resource_prediction(request: PredictionRequest):
    """
    ML-powered resource exhaustion prediction.
    Uses Prophet for sophisticated time-series forecasting.
    """
    try:
        from ai.predictor import get_predictor
        predictor = get_predictor()
        
        prediction = await predictor.predict_resource_exhaustion(
            metric=request.metric,
            hostname=request.hostname,
            threshold=request.threshold or 90.0,
            forecast_days=request.forecast_days or 30
        )
        
        if prediction:
            from dataclasses import asdict
            result = asdict(prediction)
            result["predicted_date"] = prediction.predicted_date.isoformat()
            return result
        else:
            return {
                "metric": request.metric,
                "hostname": request.hostname,
                "error": "Insufficient data for ML prediction",
                "minimum_required": "7 days of historical data"
            }
    except Exception as e:
        logger.error(f"ML resource prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/anomaly/{hostname}/{metric}")
async def ml_anomaly_prediction(hostname: str, metric: str):
    """
    ML-powered anomaly prediction using IsolationForest.
    Returns probability of current value being an anomaly.
    """
    try:
        from ai.predictor import get_predictor
        predictor = get_predictor()
        
        result = await predictor.predict_anomaly(
            metric=metric,
            hostname=hostname
        )
        
        if result:
            from dataclasses import asdict
            return asdict(result)
        else:
            return {
                "metric": metric,
                "hostname": hostname,
                "error": "Insufficient data for anomaly detection"
            }
    except Exception as e:
        logger.error(f"ML anomaly prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/status")
async def get_ml_status():
    """
    Get status of ML capabilities (Prophet, sklearn availability).
    """
    try:
        from ai.predictor import PROPHET_AVAILABLE, SKLEARN_AVAILABLE, PANDAS_AVAILABLE
        
        return {
            "status": "operational",
            "capabilities": {
                "prophet_forecasting": PROPHET_AVAILABLE,
                "isolation_forest_anomaly": SKLEARN_AVAILABLE,
                "pandas_dataframes": PANDAS_AVAILABLE
            },
            "fallback_methods": {
                "linear_regression": True,
                "z_score_anomaly": True
            },
            "endpoints": [
                "/ml/predict/{hostname}",
                "/ml/predict/resource",
                "/ml/anomaly/{hostname}/{metric}",
                "/ml/status"
            ]
        }
    except ImportError as e:
        return {
            "status": "limited",
            "error": str(e),
            "capabilities": {
                "prophet_forecasting": False,
                "isolation_forest_anomaly": False
            }
        }

