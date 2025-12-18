"""
AI Chat API - Enhanced Version
Provides intelligent natural language interface for querying system status and analysis.
Uses real AI engine with context-aware data gathering from ClickHouse.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import logging
import os

from storage.clickhouse_client import get_clickhouse_client
from ai.engine import AIEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/ai")

# Initialize AI Engine
_ai_engine = None

def get_ai_engine() -> AIEngine:
    """Get or create AI engine singleton"""
    global _ai_engine
    if _ai_engine is None:
        provider = os.getenv("AI_PROVIDER", "google")
        model = os.getenv("AI_MODEL", None)
        try:
            _ai_engine = AIEngine(provider=provider, model=model)
        except Exception as e:
            logger.error(f"Failed to initialize AI engine: {e}")
            raise
    return _ai_engine


# Conversation memory (in-memory, persists until restart)
# In production, this should be stored in ClickHouse or Redis
_conversation_history: Dict[str, List[Dict]] = {}


class ChatMessage(BaseModel):
    role: str  # user, assistant
    content: str
    timestamp: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    hostname: Optional[str] = None  # Optional server filter


class ChatResponse(BaseModel):
    message: str
    related_metrics: Optional[Dict] = None
    suggested_actions: List[str] = []
    data_context: Optional[Dict] = None  # What data was used to answer


class QueryExecutionRequest(BaseModel):
    natural_query: str
    session_id: Optional[str] = "default"


class QueryExecutionResponse(BaseModel):
    sql: str
    results: List[Dict]
    explanation: str
    row_count: int


async def gather_system_context(query: str, hostname: Optional[str] = None) -> Dict[str, Any]:
    """Intelligently gather relevant system context based on query keywords"""
    context = {}
    ch = get_clickhouse_client()
    query_lower = query.lower()
    
    try:
        # Always get basic system info
        servers = await ch.get_active_servers(hours=24)
        context["active_servers"] = servers
        context["server_count"] = len(servers)
        
        # CPU-related queries
        if any(word in query_lower for word in ['cpu', 'load', 'process', 'slow', 'performance']):
            cpu_data = await ch.query(f"""
                SELECT 
                    hostname,
                    avg(value) as avg_cpu,
                    max(value) as max_cpu,
                    min(value) as min_cpu
                FROM metrics 
                WHERE metric_name = 'cpu_usage_percent'
                AND timestamp >= now() - INTERVAL 1 HOUR
                {f"AND hostname = '{hostname}'" if hostname else ""}
                GROUP BY hostname
            """)
            context["cpu_metrics"] = [
                {"hostname": row[0], "avg": round(row[1], 2), "max": round(row[2], 2), "min": round(row[3], 2)}
                for row in cpu_data
            ]
            
            # Get top processes by CPU
            top_procs = await ch.query(f"""
                SELECT 
                    hostname,
                    -- Use argMax to get process name with max CPU
                    topK(5)(process_name) as top_processes
                FROM process_metrics
                WHERE timestamp >= now() - INTERVAL 10 MINUTE
                {f"AND hostname = '{hostname}'" if hostname else ""}
                GROUP BY hostname
            """)
            if top_procs:
                context["top_cpu_processes"] = top_procs
        
        # Memory-related queries
        if any(word in query_lower for word in ['memory', 'ram', 'oom', 'swap']):
            memory_data = await ch.query(f"""
                SELECT 
                    hostname,
                    avg(value) as avg_memory,
                    max(value) as max_memory
                FROM metrics 
                WHERE metric_name = 'memory_usage_percent'
                AND timestamp >= now() - INTERVAL 1 HOUR
                {f"AND hostname = '{hostname}'" if hostname else ""}
                GROUP BY hostname
            """)
            context["memory_metrics"] = [
                {"hostname": row[0], "avg": round(row[1], 2), "max": round(row[2], 2)}
                for row in memory_data
            ]
        
        # Disk-related queries
        if any(word in query_lower for word in ['disk', 'storage', 'space', 'io', 'read', 'write']):
            disk_data = await ch.query(f"""
                SELECT 
                    hostname,
                    avg(value) as avg_io,
                    max(value) as max_io
                FROM metrics 
                WHERE metric_name IN ('disk_read_bytes', 'disk_write_bytes')
                AND timestamp >= now() - INTERVAL 1 HOUR
                {f"AND hostname = '{hostname}'" if hostname else ""}
                GROUP BY hostname
            """)
            context["disk_metrics"] = [
                {"hostname": row[0], "avg_io_bytes": round(row[1], 2), "max_io_bytes": round(row[2], 2)}
                for row in disk_data
            ]
        
        # Network-related queries
        if any(word in query_lower for word in ['network', 'latency', 'connection', 'traffic', 'bandwidth', 'packet']):
            network_data = await ch.query(f"""
                SELECT 
                    hostname,
                    sum(CASE WHEN metric_name = 'network_bytes_sent' THEN value ELSE 0 END) as bytes_sent,
                    sum(CASE WHEN metric_name = 'network_bytes_received' THEN value ELSE 0 END) as bytes_received,
                    sum(CASE WHEN metric_name = 'network_drops' THEN value ELSE 0 END) as drops
                FROM metrics 
                WHERE metric_name IN ('network_bytes_sent', 'network_bytes_received', 'network_drops')
                AND timestamp >= now() - INTERVAL 1 HOUR
                {f"AND hostname = '{hostname}'" if hostname else ""}
                GROUP BY hostname
            """)
            context["network_metrics"] = [
                {"hostname": row[0], "bytes_sent": row[1], "bytes_received": row[2], "drops": row[3]}
                for row in network_data
            ]
        
        # Container-related queries
        if any(word in query_lower for word in ['container', 'docker', 'pod', 'service']):
            container_data = await ch.query(f"""
                SELECT 
                    container_name,
                    status,
                    avg(cpu_percent) as avg_cpu,
                    avg(memory_percent) as avg_memory,
                    max(restart_count) as restarts
                FROM docker_containers 
                WHERE timestamp >= now() - INTERVAL 1 HOUR
                GROUP BY container_name, status
                ORDER BY avg_cpu DESC
                LIMIT 20
            """)
            context["containers"] = [
                {"name": row[0], "status": row[1], "cpu": round(row[2], 2), "memory": round(row[3], 2), "restarts": row[4]}
                for row in container_data
            ]
        
        # Alert/problem-related queries
        if any(word in query_lower for word in ['alert', 'problem', 'issue', 'error', 'warning', 'critical']):
            alert_data = await ch.query("""
                SELECT 
                    alert_name,
                    severity,
                    state,
                    count(*) as occurrences
                FROM alert_history 
                WHERE timestamp >= now() - INTERVAL 24 HOUR
                GROUP BY alert_name, severity, state
                ORDER BY occurrences DESC
                LIMIT 10
            """)
            context["recent_alerts"] = [
                {"name": row[0], "severity": row[1], "state": row[2], "count": row[3]}
                for row in alert_data
            ] if alert_data else []
        
        # Security-related queries
        if any(word in query_lower for word in ['security', 'vulnerability', 'cve', 'scan']):
            try:
                security_data = await ch.query("""
                    SELECT 
                        target,
                        status,
                        score,
                        completed_at
                    FROM security_scan_results 
                    ORDER BY started_at DESC
                    LIMIT 5
                """)
                context["security_scans"] = [
                    {"target": row[0], "status": row[1], "score": row[2], "completed": row[3]}
                    for row in security_data
                ] if security_data else []
            except Exception as e:
                logger.debug(f"Security scan query failed: {e}")
                context["security_scans"] = []

    except Exception as e:
        logger.error(f"Error gathering context: {e}")
        context["error"] = str(e)
    
    return context


def build_chat_prompt(
    user_message: str, 
    context: Dict[str, Any], 
    history: List[Dict],
    hostname: Optional[str] = None
) -> str:
    """Build an intelligent prompt for the AI with full system context"""
    
    history_text = ""
    if history:
        recent_history = history[-6:]  # Last 3 exchanges
        for msg in recent_history:
            history_text += f"{msg['role'].upper()}: {msg['content']}\n"
    
    prompt = f"""You are an expert SRE AI assistant for the AncientReport monitoring platform.
You have access to real-time system metrics and should provide helpful, specific, and actionable responses.

CONVERSATION CONTEXT:
{history_text if history_text else "No previous conversation."}

CURRENT SYSTEM STATE:
- Active Servers: {', '.join(context.get('active_servers', ['unknown'])) or 'None detected'}
- Monitoring Scope: {'All servers' if not hostname else f'Server: {hostname}'}

{f'''CPU METRICS (Last Hour):
{json.dumps(context.get('cpu_metrics', []), indent=2)}''' if context.get('cpu_metrics') else ''}

{f'''MEMORY METRICS (Last Hour):
{json.dumps(context.get('memory_metrics', []), indent=2)}''' if context.get('memory_metrics') else ''}

{f'''DISK I/O (Last Hour):
{json.dumps(context.get('disk_metrics', []), indent=2)}''' if context.get('disk_metrics') else ''}

{f'''NETWORK METRICS (Last Hour):
{json.dumps(context.get('network_metrics', []), indent=2)}''' if context.get('network_metrics') else ''}

{f'''CONTAINERS:
{json.dumps(context.get('containers', []), indent=2)}''' if context.get('containers') else ''}

{f'''RECENT ALERTS:
{json.dumps(context.get('recent_alerts', []), indent=2)}''' if context.get('recent_alerts') else ''}

{f'''SECURITY SCANS:
{json.dumps(context.get('security_scans', []), indent=2)}''' if context.get('security_scans') else ''}

USER QUESTION: {user_message}

INSTRUCTIONS:
1. Answer the user's question directly using the provided system data
2. If data is available, cite specific numbers and timestamps
3. If you see concerning patterns, proactively mention them
4. Suggest 2-3 actionable next steps when appropriate
5. Be conversational but technical
6. If you don't have enough data for a complete answer, say so clearly

Respond naturally without JSON formatting. Use markdown for formatting (bold, lists, etc).
"""
    return prompt


def extract_suggested_actions(ai_response: str) -> List[str]:
    """Extract suggested actions from AI response"""
    actions = []
    response_lower = ai_response.lower()
    
    # Look for common action patterns
    action_keywords = [
        "should", "recommend", "suggest", "consider", "try",
        "run", "check", "monitor", "review", "update", "restart"
    ]
    
    lines = ai_response.split('\n')
    for line in lines:
        line_lower = line.lower().strip()
        # Look for bullet points or numbered lists with action words
        if (line_lower.startswith('-') or line_lower.startswith('•') or 
            (len(line_lower) > 2 and line_lower[0].isdigit() and line_lower[1] == '.')):
            for keyword in action_keywords:
                if keyword in line_lower:
                    # Clean up the action
                    action = line.strip().lstrip('-•').strip()
                    if action and len(action) > 10:
                        actions.append(action[:200])  # Limit length
                        break
    
    # If no actions found in list format, try to extract from text
    if not actions:
        for keyword in ['recommend', 'suggest', 'should']:
            if keyword in response_lower:
                actions.append("Review the AI's detailed recommendations above")
                break
    
    return actions[:5]  # Max 5 actions


@router.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a natural language query about the system using real AI."""
    global _conversation_history
    
    try:
        # Get or create session history
        session_id = request.session_id or "default"
        if session_id not in _conversation_history:
            _conversation_history[session_id] = []
        
        history = _conversation_history[session_id]
        
        # Gather relevant context based on query
        context = await gather_system_context(request.message, request.hostname)
        
        # Build prompt with context and history
        prompt = build_chat_prompt(request.message, context, history, request.hostname)
        
        # Get AI response
        ai_engine = get_ai_engine()
        ai_response = await ai_engine.generate_insights(prompt, temperature=0.5)
        
        # Update conversation history
        history.append({"role": "user", "content": request.message, "timestamp": datetime.now().isoformat()})
        history.append({"role": "assistant", "content": ai_response, "timestamp": datetime.now().isoformat()})
        
        # Keep only last 20 messages
        _conversation_history[session_id] = history[-20:]
        
        # Extract suggested actions
        suggested_actions = extract_suggested_actions(ai_response)
        
        # Build related metrics summary
        related_metrics = {}
        if context.get('cpu_metrics'):
            related_metrics['cpu'] = context['cpu_metrics']
        if context.get('memory_metrics'):
            related_metrics['memory'] = context['memory_metrics']
        if context.get('containers'):
            related_metrics['containers'] = len(context['containers'])
        
        return ChatResponse(
            message=ai_response,
            related_metrics=related_metrics if related_metrics else None,
            suggested_actions=suggested_actions,
            data_context={
                "servers_analyzed": context.get('active_servers', []),
                "time_range": "last 1 hour",
                "context_keys": list(context.keys())
            }
        )
        
    except Exception as e:
        logger.error(f"AI Chat error: {e}", exc_info=True)
        # Fallback response if AI fails
        return ChatResponse(
            message=f"I apologize, but I encountered an error while processing your request: {str(e)}. Please try again or check the AI configuration.",
            suggested_actions=["Check AI_PROVIDER environment variable", "Verify API key is set", "Check analysis service logs"]
        )


@router.get("/history")
async def get_chat_history(session_id: str = "default", limit: int = 50) -> List[ChatMessage]:
    """Get recent chat history for a session."""
    global _conversation_history
    
    history = _conversation_history.get(session_id, [])
    messages = [
        ChatMessage(
            role=msg.get("role", "unknown"),
            content=msg.get("content", ""),
            timestamp=msg.get("timestamp", datetime.now().isoformat())
        )
        for msg in history[-limit:]
    ]
    return messages


@router.delete("/history")
async def clear_chat_history(session_id: str = "default"):
    """Clear chat history for a session."""
    global _conversation_history
    
    if session_id in _conversation_history:
        _conversation_history[session_id] = []
    
    return {"status": "cleared", "session_id": session_id}


@router.post("/query")
async def execute_natural_language_query(request: QueryExecutionRequest) -> QueryExecutionResponse:
    """Convert natural language to SQL and execute against ClickHouse.
    
    This is a powerful feature that allows users to ask questions like:
    - "Show me containers with memory usage over 80%"
    - "What's the average CPU for each server today?"
    - "List top 10 processes by memory"
    """
    try:
        ch = get_clickhouse_client()
        ai_engine = get_ai_engine()
        
        # Get table schemas for context
        tables_info = """
        Available tables:
        - metrics: timestamp, hostname, metric_name, value (CPU, memory, disk, network metrics)
        - docker_containers: timestamp, container_name, status, cpu_percent, memory_percent, restart_count
        - process_metrics: timestamp, hostname, process_name, cpu_percent, memory_mb
        - alert_history: timestamp, alert_name, severity, state
        - security_scan_results: target, status, score, vulnerabilities
        """
        
        # Generate SQL from natural language
        sql_prompt = f"""Convert this natural language query to a ClickHouse SQL query.

{tables_info}

User query: "{request.natural_query}"

IMPORTANT RULES:
1. Return ONLY the SQL query, no explanation
2. Always include LIMIT (max 100 rows)
3. Only SELECT queries allowed (no INSERT, UPDATE, DELETE)
4. Use reasonable time filters (e.g., last 24 hours)
5. Group and aggregate when appropriate

SQL:"""
        
        generated_sql = await ai_engine.generate_insights(sql_prompt, temperature=0.1)
        generated_sql = generated_sql.strip()
        
        # Basic safety check
        sql_lower = generated_sql.lower()
        if any(danger in sql_lower for danger in ['insert', 'update', 'delete', 'drop', 'truncate', 'alter']):
            raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")
        
        # Ensure LIMIT exists
        if 'limit' not in sql_lower:
            generated_sql = generated_sql.rstrip(';') + ' LIMIT 100;'
        
        # Execute query
        try:
            result = ch.execute(generated_sql)
        except Exception as e:
            return QueryExecutionResponse(
                sql=generated_sql,
                results=[],
                explanation=f"Query failed: {str(e)}. The generated SQL may have syntax errors.",
                row_count=0
            )
        
        # Convert to list of dicts (assuming simple queries)
        results = []
        for row in result[:100]:  # Safety limit
            if isinstance(row, tuple):
                # Try to create a meaningful dict
                results.append({f"col_{i}": val for i, val in enumerate(row)})
            else:
                results.append({"value": row})
        
        # Generate explanation
        explanation_prompt = f"""Explain these query results in 2-3 sentences:

Query: {request.natural_query}
SQL: {generated_sql}
Row count: {len(results)}
Sample data: {json.dumps(results[:3], default=str)}

Brief explanation:"""
        
        explanation = await ai_engine.generate_insights(explanation_prompt, temperature=0.3)
        
        return QueryExecutionResponse(
            sql=generated_sql,
            results=results,
            explanation=explanation.strip(),
            row_count=len(results)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/resource-usage")
async def predict_resource_usage(
    metric: str = "cpu_usage_percent",
    hostname: Optional[str] = None,
    days: int = 7
) -> Dict[str, Any]:
    """Predict resource usage for the next N days using AI analysis.
    
    This uses historical data patterns to make predictions.
    """
    try:
        ch = get_clickhouse_client()
        ai_engine = get_ai_engine()
        
        # Get historical data (last 30 days)
        hostname_filter = f"AND hostname = '{hostname}'" if hostname else ""
        history_data = await ch.query(f"""
            SELECT 
                toDate(timestamp) as day,
                avg(value) as avg_value,
                max(value) as max_value,
                min(value) as min_value
            FROM metrics
            WHERE metric_name = '{metric}'
            AND timestamp >= now() - INTERVAL 30 DAY
            {hostname_filter}
            GROUP BY day
            ORDER BY day
        """)
        
        if not history_data:
            return {
                "metric": metric,
                "hostname": hostname,
                "prediction": [],
                "trend": "unknown",
                "message": "Insufficient historical data for prediction"
            }
        
        # Format history for AI
        history_text = "\n".join([
            f"  {row[0]}: avg={round(row[1], 2)}, max={round(row[2], 2)}, min={round(row[3], 2)}"
            for row in history_data
        ])
        
        # Ask AI to predict
        prediction_prompt = f"""Analyze this historical {metric} data and predict the next {days} days.

Historical data (last 30 days):
{history_text}

Based on patterns (weekly cycles, trends, etc.), predict the next {days} days.

Return JSON format:
{{
  "predictions": [
    {{"day": 1, "predicted_avg": X, "predicted_max": Y, "confidence": "high/medium/low"}},
    ...
  ],
  "trend": "increasing/decreasing/stable",
  "analysis": "Brief explanation of patterns observed"
}}

JSON only:"""
        
        ai_response = await ai_engine.generate_insights(prediction_prompt, temperature=0.2)
        
        # Try to parse JSON from response
        try:
            # Clean up response (remove markdown if present)
            json_text = ai_response.strip()
            if json_text.startswith('```'):
                json_text = json_text.split('```')[1]
                if json_text.startswith('json'):
                    json_text = json_text[4:]
            prediction_result = json.loads(json_text)
        except json.JSONDecodeError:
            # Fallback if AI returns invalid JSON
            prediction_result = {
                "predictions": [
                    {"day": i, "predicted_avg": row[1] if i <= len(history_data) else history_data[-1][1]}
                    for i in range(1, days + 1)
                ],
                "trend": "stable",
                "analysis": ai_response[:500]  # Include AI response as analysis
            }
        
        return {
            "metric": metric,
            "hostname": hostname or "all",
            "days_predicted": days,
            "history_days": len(history_data),
            **prediction_result
        }
        
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        return {
            "metric": metric,
            "hostname": hostname,
            "prediction": [],
            "trend": "error",
            "message": str(e)
        }


@router.get("/status")
async def get_ai_status() -> Dict[str, Any]:
    """Get AI Chat status and configuration."""
    try:
        ai_engine = get_ai_engine()
        ch = get_clickhouse_client()
        servers = await ch.get_active_servers(hours=24)
        
        return {
            "status": "operational",
            "ai_provider": ai_engine.provider,
            "ai_model": ai_engine.model,
            "active_sessions": len(_conversation_history),
            "active_servers": servers,
            "features": [
                "context_aware_chat",
                "conversation_memory",
                "natural_language_queries",
                "resource_prediction"
            ]
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "ai_provider": os.getenv("AI_PROVIDER", "google"),
            "active_sessions": len(_conversation_history)
        }
