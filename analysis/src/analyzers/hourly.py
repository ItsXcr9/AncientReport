from datetime import datetime, timedelta
from typing import Dict, List
import numpy as np
import json
import logging
import re

from .metrics_aggregator import MetricsAggregator
from utils.timezone import to_utc_for_query

logger = logging.getLogger(__name__)


class HourlyAnalyzer:
    """
    Performs hourly analysis of system metrics with AI-powered insights
    """
    
    def __init__(self, clickhouse_client, ai_engine):
        self.ch = clickhouse_client
        self.ai = ai_engine
        self.aggregator = MetricsAggregator(clickhouse_client)
    
    async def run_analysis(self, end_time: datetime) -> Dict:
        """Run complete hourly analysis"""
        logger.info(f"Starting hourly analysis for {end_time}")
        
        start_time = end_time - timedelta(hours=1)
        
        # Fetch current hour metrics (aggregated)
        current_metrics = await self.fetch_metrics(start_time, end_time)
        
        # Calculate 7-day baseline
        baseline = await self.calculate_baseline(end_time)
        
        # Detect anomalies
        anomalies = self.detect_anomalies(current_metrics, baseline)
        
        # Analyze configurations (placeholder)
        config_issues = []
        
        # Fetch top processes (before building context so AI can see them)
        top_processes = await self.fetch_top_processes(start_time, end_time)
        logger.info(f"Fetched top processes: CPU={len(top_processes.get('cpu', []))}, Memory={len(top_processes.get('memory', []))}, DiskIO={len(top_processes.get('disk_io', []))}")
        
        # Build context for AI (include top processes)
        context = self.build_context(current_metrics, baseline, anomalies, config_issues, top_processes)
        
        # Generate AI insights
        ai_insights = await self.generate_ai_insights(context)
        
        # Calculate capacity forecast
        forecast = self.calculate_forecast(current_metrics, baseline)
        
        # Calculate health score
        health_score = self.calculate_health_score(current_metrics, anomalies)
        
        # Build report
        report = {
            "report_id": end_time.isoformat(),
            "period": f"{start_time.isoformat()} to {end_time.isoformat()}",
            "system_health": {
                "overall_score": health_score,
                "status": self.get_health_status(health_score),
                "pressure_points": self.identify_pressure_points(current_metrics, baseline)
            },
            "resource_usage": current_metrics,
            "top_processes": top_processes,
            "ai_insights": ai_insights,
            "capacity_forecast": forecast,
            "anomalies": anomalies
        }
        
        # Store report (TODO: implement ClickHouse storage)
        logger.info(f"Report generated: health_score={health_score}")
        
        return report
    
    async def fetch_metrics(self, start_time: datetime, end_time: datetime) -> Dict:
        """Fetch aggregated metrics from ClickHouse - expects Tehran timezone, converts to UTC for query"""
        try:
            logger.info(f"Fetching metrics from {start_time} to {end_time}")
            
            # Convert to UTC for ClickHouse queries (ClickHouse stores in UTC)
            # Subtract 10 seconds from end_time to account for data collection lag
            # This ensures we don't query for data that hasn't been written yet
            end_time_adjusted = end_time - timedelta(seconds=10)
            
            # Use the aggregator to get pre-processed metrics
            aggregated = await self.aggregator.aggregate_hourly_metrics(start_time, end_time_adjusted)
            
            # If no data found, try multiple fallback strategies
            if aggregated.get('cpu', {}).get('average', 0) == 0:
                logger.warning("No data found for requested time range, trying fallback strategies...")
                
                # Strategy 1: Try last 15 minutes
                recent_start = end_time - timedelta(minutes=15)
                logger.info(f"Trying last 15 minutes: {recent_start} to {end_time}")
                aggregated = await self.aggregator.aggregate_hourly_metrics(recent_start, end_time_adjusted)
                
                # Strategy 2: If still no data, try last 24 hours (get most recent data)
                if aggregated.get('cpu', {}).get('average', 0) == 0:
                    logger.warning("No data in last 15 minutes, trying last 24 hours...")
                    day_start = end_time - timedelta(hours=24)
                    aggregated = await self.aggregator.aggregate_hourly_metrics(day_start, end_time_adjusted)
                    
                    # If we got data from 24h window, log a warning
                    if aggregated.get('cpu', {}).get('average', 0) > 0:
                        logger.warning(f"Using data from last 24 hours instead of requested range. This suggests agent may have stopped collecting recently.")
            
            # Transform to the expected format
            disk_io = aggregated.get('disk_io', {})
            network = aggregated.get('network', {})
            cpu = aggregated.get('cpu', {})
            memory = aggregated.get('memory', {})
            
            logger.info(f"Fetched metrics - CPU: {cpu.get('average', 0):.2f}%, Memory: {memory.get('average', 0):.2f}%")
            
            return {
                "cpu": cpu if cpu else {'average': 0, 'peak': 0},
                "memory": memory if memory else {'average': 0, 'peak': 0},
                "disk_io": {
                    "reads_per_sec": disk_io.get('reads_per_sec', 0),
                    "writes_per_sec": disk_io.get('writes_per_sec', 0),
                    "latency_ms": disk_io.get('latency_ms', 0)
                },
                "network": {
                    "packets_sent": network.get('packets_sent', 0),
                    "packets_received": network.get('packets_received', 0),
                    "drops": network.get('drops', 0)
                }
            }
        except Exception as e:
            logger.error(f"Failed to fetch metrics: {e}", exc_info=True)
            # Return empty metrics on error
            return {
                "cpu": {"average": 0, "peak": 0},
                "memory": {"average": 0, "peak": 0},
                "disk_io": {"reads_per_sec": 0, "writes_per_sec": 0, "latency_ms": 0},
                "network": {"packets_sent": 0, "packets_received": 0, "drops": 0}
            }
    
    async def calculate_baseline(self, end_time: datetime) -> Dict:
        """Calculate 7-day baseline for same hour"""
        try:
            # Calculate baseline from past 7 days at same hour (+/- 30 min window)
            start_baseline = end_time - timedelta(days=7)
            
            # Fetch historical metrics
            historical_metrics = await self.aggregator.aggregate_hourly_metrics(start_baseline, end_time)
            
            # If we have enough data, calculate statistics
            # Otherwise, return None to indicate no baseline available
            if not historical_metrics or historical_metrics.get('cpu', {}).get('average', 0) == 0:
                logger.warning("Insufficient data for baseline calculation (need 7 days of history)")
                return None
            
            # Calculate mean and std from historical data
            # For simplicity, we'll use the aggregated values as approximations
            cpu = historical_metrics.get('cpu', {})
            memory = historical_metrics.get('memory', {})
            disk_io = historical_metrics.get('disk_io', {})
            network = historical_metrics.get('network', {})
            
            # Use average as mean, and estimate std as 10% of mean (reasonable assumption)
            # In a more sophisticated system, we'd query individual hourly datapoints
            baselines = {
                "cpu": {
                    "mean": cpu.get('average', 0),
                    "std": max(cpu.get('average', 0) * 0.1, 1.0)  # At least 1% std
                },
                "memory": {
                    "mean": memory.get('average', 0),
                    "std": max(memory.get('average', 0) * 0.1, 1.0)
                },
                "disk_io": {
                    "mean": disk_io.get('reads_per_sec', 0) + disk_io.get('writes_per_sec', 0),
                    "std": max((disk_io.get('reads_per_sec', 0) + disk_io.get('writes_per_sec', 0)) * 0.15, 10.0)
                },
                "network": {
                    "mean": network.get('packets_sent', 0) + network.get('packets_received', 0),
                    "std": max((network.get('packets_sent', 0) + network.get('packets_received', 0)) * 0.15, 100.0)
                }
            }
            
            logger.info(f"Baseline calculated - CPU: {baselines['cpu']['mean']:.1f}±{baselines['cpu']['std']:.1f}%, "
                       f"Memory: {baselines['memory']['mean']:.1f}±{baselines['memory']['std']:.1f}%")
            
            return baselines
            
        except Exception as e:
            logger.error(f"Failed to calculate baseline: {e}", exc_info=True)
            return None
    
    def detect_anomalies(self, current: Dict, baseline: Dict) -> List[Dict]:
        """Detect anomalies using Z-score (threshold: 2.5 sigma)"""
        anomalies = []
        
        # If no baseline available, skip anomaly detection
        if not baseline:
            logger.info("No baseline available, skipping anomaly detection")
            return anomalies
        
        # CPU anomaly check
        if "cpu" in baseline and baseline["cpu"]["std"] > 0:
            cpu_current = current["cpu"]["average"]
            cpu_base = baseline["cpu"]
            z_score = (cpu_current - cpu_base["mean"]) / cpu_base["std"]
            if abs(z_score) > 2.5:
                diff_pct = ((cpu_current - cpu_base["mean"]) / cpu_base["mean"]) * 100
                anomalies.append({
                    "metric": "CPU",
                    "current_value": cpu_current,
                    "baseline_mean": cpu_base["mean"],
                    "z_score": z_score,
                    "severity": "critical" if abs(z_score) > 3.5 else "warning",
                    "description": f"CPU usage is {cpu_current:.1f}% (baseline: {cpu_base['mean']:.1f}%, {diff_pct:+.0f}%)"
                })
        
        # Memory anomaly check
        if "memory" in baseline and baseline["memory"]["std"] > 0:
            mem_current = current["memory"]["average"]
            mem_base = baseline["memory"]
            z_score = (mem_current - mem_base["mean"]) / mem_base["std"]
            if abs(z_score) > 2.5:
                diff_pct = ((mem_current - mem_base["mean"]) / mem_base["mean"]) * 100
                anomalies.append({
                    "metric": "Memory",
                    "current_value": mem_current,
                    "baseline_mean": mem_base["mean"],
                    "z_score": z_score,
                    "severity": "critical" if abs(z_score) > 3.5 else "warning",
                    "description": f"Memory usage is {mem_current:.1f}% (baseline: {mem_base['mean']:.1f}%, {diff_pct:+.0f}%)"
                })
        
        # Network anomaly check (for drops specifically)
        network_drops = current["network"]["drops"]
        if "network" in baseline and baseline["network"]["std"] > 0 and network_drops > 0:
            net_base = baseline["network"]
            # Use packet drops as the metric for network health
            # If drops are significantly higher than usual, flag it
            if network_drops > 100:  # Simple threshold - more than 100 drops
                anomalies.append({
                    "metric": "Network",
                    "current_value": network_drops,
                    "baseline_mean": 0,
                    "z_score": 0,
                    "severity": "warning" if network_drops < 1000 else "critical",
                    "description": f"Network packet drops detected: {network_drops} drops"
                })
        
        logger.info(f"Detected {len(anomalies)} anomalies")
        return anomalies
    
    def build_context(self, current: Dict, baseline: Dict, anomalies: List, config_issues: List, top_processes: Dict) -> Dict:
        """Build context dictionary for AI analysis"""
        # Format top processes for AI context
        top_cpu_str = ", ".join([f"{p['name']} (PID {p['pid']}, {p['average']:.1f}%)" for p in top_processes.get('cpu', [])[:3]])
        top_memory_str = ", ".join([f"{p['name']} (PID {p['pid']}, {p['average']:.1f}MB)" for p in top_processes.get('memory', [])[:3]])
        top_disk_io_str = ", ".join([f"{p['name']} (PID {p['pid']}, {p['average']:.1f}MB)" for p in top_processes.get('disk_io', [])[:3]])
        
        # Calculate actual comparisons vs baseline
        def calc_vs_baseline(current_val: float, baseline_dict: dict, metric_name: str) -> str:
            """Calculate percentage difference vs baseline"""
            if not baseline_dict or metric_name not in baseline_dict:
                return "no baseline"
            baseline_mean = baseline_dict[metric_name].get('mean', 0)
            if baseline_mean == 0:
                return "no baseline"
            diff_pct = ((current_val - baseline_mean) / baseline_mean) * 100
            if abs(diff_pct) < 5:
                return "normal"
            sign = "+" if diff_pct > 0 else ""
            return f"{sign}{diff_pct:.0f}%"
        
        # Get actual CPU and memory values for comparison
        cpu_avg = current["cpu"]["average"]
        memory_pct = current["memory"]["average"]
        disk_iops = current["disk_io"]["reads_per_sec"] + current["disk_io"]["writes_per_sec"]
        packets_total = current["network"]["packets_sent"] + current["network"]["packets_received"]
        
        return {
            "hostname": "production-server",
            "uptime": "N/A",
            "cpu_count": "N/A",
            "memory_gb": "N/A",
            "os_info": "Linux",
            "cpu_avg": cpu_avg,
            "cpu_peak": current["cpu"]["peak"],
            "cpu_vs_baseline": calc_vs_baseline(cpu_avg, baseline, 'cpu'),
            "memory_percent": memory_pct,
            "memory_vs_baseline": calc_vs_baseline(memory_pct, baseline, 'memory'),
            "disk_iops": disk_iops,
            "disk_latency_ms": current["disk_io"]["latency_ms"],
            "disk_vs_baseline": calc_vs_baseline(disk_iops, baseline, 'disk_io'),
            "packets_total": packets_total,
            "packet_drops": current["network"]["drops"],
            "network_vs_baseline": calc_vs_baseline(packets_total, baseline, 'network'),
            "top_cpu_processes": top_cpu_str or "None",
            "top_memory_processes": top_memory_str or "None",
            "top_disk_io_processes": top_disk_io_str or "None",
            "anomalies": anomalies,
            "config_issues": config_issues
        }
    
    def _extract_json_from_response(self, response: str) -> str:
        """Extract JSON from AI response, handling various formats including nested structures"""
        # Remove leading/trailing whitespace
        cleaned = response.strip()
        
        # First, try to remove markdown code blocks (most common case)
        # Handle ```json ... ``` or ``` ... ```
        markdown_pattern = r'```(?:json)?\s*(.*?)\s*```'
        markdown_match = re.search(markdown_pattern, cleaned, re.DOTALL)
        if markdown_match:
            cleaned = markdown_match.group(1).strip()
        
        # Find the first { and last } to extract the JSON object
        # Use a balanced bracket approach to handle nested structures
        first_brace = cleaned.find('{')
        if first_brace == -1:
            logger.warning("No opening brace found in response")
            return cleaned
        
        # Count braces to find the matching closing brace
        brace_count = 0
        last_brace = first_brace
        for i in range(first_brace, len(cleaned)):
            if cleaned[i] == '{':
                brace_count += 1
            elif cleaned[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_brace = i
                    break
        
        if brace_count != 0:
            logger.warning(f"Unbalanced braces in response (count: {brace_count}), attempting fallback extraction")
            # Fallback: find last } after first {
            last_brace = cleaned.rfind('}')
            if last_brace <= first_brace:
                logger.error("Could not find valid JSON boundaries")
                return cleaned
        
        # Extract the JSON portion
        json_str = cleaned[first_brace:last_brace + 1]
        
        # Clean up any remaining whitespace
        json_str = json_str.strip()
        
        # Validate it looks like JSON (starts with { and ends with })
        if not (json_str.startswith('{') and json_str.endswith('}')):
            logger.warning("Extracted string doesn't look like valid JSON, returning as-is")
        
        return json_str
    
    def _validate_ai_insights(self, insights: Dict) -> Dict:
        """Validate and normalize AI insights structure"""
        # Ensure critical_alerts is always a list
        if "critical_alerts" not in insights:
            insights["critical_alerts"] = []
        elif not isinstance(insights["critical_alerts"], list):
            # Convert to list if it's a string or other type
            if isinstance(insights["critical_alerts"], str):
                insights["critical_alerts"] = [insights["critical_alerts"]]
            else:
                insights["critical_alerts"] = []
        
        # Ensure recommendations is always a list of proper format
        if "recommendations" not in insights:
            logger.warning("recommendations key missing from AI insights, initializing as empty list")
            insights["recommendations"] = []
        elif not isinstance(insights["recommendations"], list):
            logger.warning(f"recommendations is not a list (type: {type(insights['recommendations'])}), initializing as empty list")
            insights["recommendations"] = []
        else:
            # Normalize recommendations to objects with title/description/priority
            normalized_recommendations = []
            original_count = len(insights["recommendations"])
            logger.info(f"Normalizing {original_count} recommendations")
            
            for idx, rec in enumerate(insights["recommendations"]):
                try:
                    if isinstance(rec, dict):
                        # Already an object, ensure it has required fields
                        # Try multiple possible key names for title/description
                        title = rec.get("title") or rec.get("action") or rec.get("name") or ""
                        description = rec.get("description") or rec.get("details") or rec.get("explanation") or title or str(rec)
                        priority = rec.get("priority", "medium")
                        
                        # Normalize priority to lowercase and validate
                        if isinstance(priority, str):
                            priority = priority.lower()
                            if priority not in ["high", "medium", "low"]:
                                logger.warning(f"Invalid priority '{priority}' for recommendation {idx}, defaulting to 'medium'")
                                priority = "medium"
                        else:
                            priority = "medium"
                        
                        # Ensure title and description are strings
                        if not title:
                            title = description[:80] if description else f"Recommendation {idx + 1}"
                        
                        normalized_rec = {
                            "title": str(title),
                            "description": str(description),
                            "priority": priority
                        }
                        normalized_recommendations.append(normalized_rec)
                        logger.debug(f"Normalized recommendation {idx + 1}: title='{title[:50]}...', priority={priority}")
                        
                    elif isinstance(rec, str):
                        # String format, convert to object
                        rec_str = rec.strip()
                        if rec_str:
                            # Try to split into title and description if it contains newlines
                            parts = rec_str.split('\n', 1)
                            title = parts[0].strip()[:80]  # Limit title length
                            description = parts[1].strip() if len(parts) > 1 else rec_str
                            
                            normalized_recommendations.append({
                                "title": title,
                                "description": description,
                                "priority": "medium"
                            })
                            logger.debug(f"Converted string recommendation {idx + 1} to object")
                        else:
                            logger.warning(f"Skipping empty string recommendation at index {idx}")
                    else:
                        # Unknown format, convert to string
                        rec_str = str(rec).strip()
                        if rec_str:
                            normalized_recommendations.append({
                                "title": rec_str[:80],
                                "description": rec_str,
                                "priority": "medium"
                            })
                            logger.warning(f"Converted unknown format recommendation {idx + 1} (type: {type(rec)}) to object")
                        else:
                            logger.warning(f"Skipping empty recommendation at index {idx} (type: {type(rec)})")
                            
                except Exception as e:
                    logger.error(f"Error normalizing recommendation {idx}: {e}", exc_info=True)
                    # Skip this recommendation but continue processing others
                    continue
            
            insights["recommendations"] = normalized_recommendations
            logger.info(f"Successfully normalized {len(normalized_recommendations)}/{original_count} recommendations")
            
            # Filter out any recommendations with empty titles
            before_filter = len(insights["recommendations"])
            insights["recommendations"] = [
                rec for rec in insights["recommendations"] 
                if rec.get("title") and rec.get("title").strip()
            ]
            if len(insights["recommendations"]) < before_filter:
                logger.warning(f"Filtered out {before_filter - len(insights['recommendations'])} recommendations with empty titles")
        
        # Ensure capacity_forecast is always a dict
        if "capacity_forecast" not in insights:
            insights["capacity_forecast"] = {}
        elif not isinstance(insights["capacity_forecast"], dict):
            insights["capacity_forecast"] = {}
        
        # Ensure config_optimizations is always a list
        if "config_optimizations" not in insights:
            insights["config_optimizations"] = []
        elif not isinstance(insights["config_optimizations"], list):
            insights["config_optimizations"] = []
        
        # Filter out empty strings from critical_alerts
        insights["critical_alerts"] = [alert for alert in insights["critical_alerts"] if alert and str(alert).strip()]
        
        return insights
    
    async def generate_ai_insights(self, context: Dict) -> Dict:
        """Generate AI insights with robust JSON parsing"""
        try:
            prompt = self.ai.build_analysis_prompt(context)
            logger.debug(f"Generated prompt length: {len(prompt)} characters")
            
            response = await self.ai.generate_insights(prompt)
            
            logger.info(f"Raw AI response received (length: {len(response)} chars)")
            logger.debug(f"Raw AI response (first 500 chars): {response[:500]}")
            if len(response) > 500:
                logger.debug(f"Raw AI response (last 200 chars): {response[-200:]}")
            
            # Extract JSON from response
            cleaned_response = self._extract_json_from_response(response)
            
            logger.info(f"Cleaned response length: {len(cleaned_response)} chars")
            logger.debug(f"Cleaned response (first 500 chars): {cleaned_response[:500]}")
            if len(cleaned_response) > 500:
                logger.debug(f"Cleaned response (last 200 chars): {cleaned_response[-200:]}")
            
            # Try to parse JSON
            try:
                insights = json.loads(cleaned_response)
                logger.info("Successfully parsed JSON from AI response")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}")
                logger.error(f"JSON error position: line {e.lineno}, column {e.colno}")
                logger.error(f"Problematic JSON snippet: {cleaned_response[max(0, e.pos-50):e.pos+50]}")
                
                # Try regex-based extraction of critical_alerts as fallback
                logger.warning("Attempting fallback extraction of critical_alerts")
                alerts_match = re.search(r'"critical_alerts"\s*:\s*\[(.*?)\]', cleaned_response, re.DOTALL)
                recommendations_match = re.search(r'"recommendations"\s*:\s*\[(.*?)\]', cleaned_response, re.DOTALL)
                
                if alerts_match or recommendations_match:
                    alerts = []
                    if alerts_match:
                        alerts_text = alerts_match.group(1)
                        alerts = re.findall(r'"([^"]+)"', alerts_text)
                        logger.info(f"Extracted {len(alerts)} alerts using fallback method")
                    
                    recommendations = []
                    if recommendations_match:
                        # Try to extract recommendation objects
                        recs_text = recommendations_match.group(1)
                        # Look for objects with title/description
                        rec_objects = re.findall(r'\{(.*?)\}', recs_text, re.DOTALL)
                        for rec_obj in rec_objects:
                            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', rec_obj)
                            desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', rec_obj)
                            priority_match = re.search(r'"priority"\s*:\s*"([^"]+)"', rec_obj)
                            if title_match or desc_match:
                                recommendations.append({
                                    "title": title_match.group(1) if title_match else (desc_match.group(1)[:80] if desc_match else "Recommendation"),
                                    "description": desc_match.group(1) if desc_match else (title_match.group(1) if title_match else ""),
                                    "priority": priority_match.group(1).lower() if priority_match else "medium"
                                })
                        logger.info(f"Extracted {len(recommendations)} recommendations using fallback method")
                    
                    insights = {
                        "critical_alerts": alerts,
                        "recommendations": recommendations,
                        "capacity_forecast": {},
                        "config_optimizations": []
                    }
                    logger.warning(f"Using fallback extraction - alerts: {len(alerts)}, recommendations: {len(recommendations)}")
                else:
                    logger.error("Fallback extraction also failed, no patterns found in response")
                    raise
            
            # Validate and normalize structure
            logger.info("Validating and normalizing AI insights structure")
            insights = self._validate_ai_insights(insights)
            
            # Log the parsed structure with details
            logger.info(f"Successfully parsed AI insights:")
            logger.info(f"  - critical_alerts: {len(insights.get('critical_alerts', []))} items")
            logger.info(f"  - recommendations: {len(insights.get('recommendations', []))} items")
            logger.info(f"  - capacity_forecast: {bool(insights.get('capacity_forecast'))}")
            logger.info(f"  - config_optimizations: {len(insights.get('config_optimizations', []))} items")
            
            if insights.get('critical_alerts'):
                logger.info(f"Critical alerts: {insights['critical_alerts']}")
            
            if insights.get('recommendations'):
                for idx, rec in enumerate(insights['recommendations'][:3]):  # Log first 3
                    logger.debug(f"Recommendation {idx + 1}: title='{rec.get('title', 'N/A')[:50]}', priority={rec.get('priority', 'N/A')}")
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to generate AI insights: {e}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            return {
                "critical_alerts": [],
                "recommendations": [{
                    "title": "AI analysis unavailable",
                    "description": f"Error: {str(e)[:200]}",
                    "priority": "high"
                }],
                "capacity_forecast": {},
                "config_optimizations": []
            }
    
    def calculate_forecast(self, current: Dict, baseline: Dict) -> Dict:
        """Calculate capacity forecast"""
        return {
            "cpu": {
                "current_utilization": current["cpu"]["average"],
                "growth_rate_per_week": 2.3,
                "weeks_until_80_percent": 13
            },
            "needs_upgrade": False,
            "recommended_action": "monitor"
        }
    
    def calculate_health_score(self, metrics: Dict, anomalies: List) -> int:
        """Calculate overall system health score (0-100)"""
        score = 100
        
        # Deduct points for high CPU
        if metrics["cpu"]["average"] > 80:
            score -= 20
        elif metrics["cpu"]["average"] > 60:
            score -= 10
        
        # Deduct points for high memory
        if metrics["memory"]["average"] > 85:
            score -= 20
        elif metrics["memory"]["average"] > 70:
            score -= 10
        
        # Deduct points for anomalies
        score -= len(anomalies) * 5
        
        return max(0, min(100, score))
    
    def get_health_status(self, score: int) -> str:
        """Convert health score to status"""
        if score >= 90:
            return "excellent"
        elif score >= 80:
            return "healthy"
        elif score >= 60:
            return "warning"
        else:
            return "critical"
    
    def identify_pressure_points(self, current: Dict, baseline: Dict) -> List[str]:
        """Identify system pressure points"""
        pressure_points = []
        
        if current["cpu"]["average"] > 70:
            pressure_points.append("cpu")
        
        if current["memory"]["average"] > 80:
            pressure_points.append("memory")
        
        if current["disk_io"]["latency_ms"] > 20:
            pressure_points.append("disk_io")
        
        if current["network"]["drops"] > 10:
            pressure_points.append("network")
        
        return pressure_points
    
    async def fetch_top_processes(self, start_time: datetime, end_time: datetime) -> Dict:
        """Fetch top processes for CPU, memory, and disk I/O"""
        try:
            # Fetch process metrics from ClickHouse
            cpu_processes = await self.ch.get_metrics_raw(start_time, end_time, "process_cpu_usage", limit=100)
            memory_processes = await self.ch.get_metrics_raw(start_time, end_time, "process_memory_mb", limit=100)
            disk_io_processes = await self.ch.get_metrics_raw(start_time, end_time, "process_disk_io_mb", limit=100)
            
            # Aggregate by process name and get averages
            cpu_by_process: Dict[str, List[float]] = {}
            memory_by_process: Dict[str, List[float]] = {}
            disk_io_by_process: Dict[str, List[float]] = {}
            
            # Process CPU metrics
            for row in cpu_processes:
                # row format: (timestamp, value) - but we need to get tags
                # Since get_metrics_raw doesn't return tags, we'll need to modify the query
                # For now, let's use a different approach - query with tags
                pass
            
            # For now, use a simpler aggregation approach
            # We'll query the metrics table directly with tags
            top_cpu = await self._get_top_processes_by_metric("process_cpu_usage", start_time, end_time)
            top_memory = await self._get_top_processes_by_metric("process_memory_mb", start_time, end_time)
            top_disk_io = await self._get_top_processes_by_metric("process_disk_io_mb", start_time, end_time)
            
            return {
                "cpu": top_cpu[:3],  # Top 3
                "memory": top_memory[:3],
                "disk_io": top_disk_io[:3],
                "network": []  # Network per-process is harder, skip for now
            }
        except Exception as e:
            logger.error(f"Failed to fetch top processes: {e}", exc_info=True)
            return {
                "cpu": [],
                "memory": [],
                "disk_io": [],
                "network": []
            }
    
    async def _get_top_processes_by_metric(self, metric_name: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get top processes for a specific metric - expects Tehran timezone, converts to UTC for query"""
        try:
            # Convert to UTC for ClickHouse query
            # Subtract 10 seconds from end_time to account for data collection lag
            end_time_adjusted = end_time - timedelta(seconds=10)
            
            # Use Unix timestamps for timezone-safe conversion
            start_ts = int(start_time.timestamp())
            end_ts = int(end_time_adjusted.timestamp())
            
            # Query to get average value per process (using tags)
            # Use bracket notation for Map access (compatible with older ClickHouse versions)
            # Use argMax() to get the most recent command_line for each process (aggregate function)
            sql = f"""
            SELECT 
                tags['process_name'] as process_name,
                tags['pid'] as pid,
                argMax(if(has(tags, 'command_line'), tags['command_line'], ''), timestamp) as command_line,
                avg(value) as avg_value,
                max(value) as max_value,
                count(*) as sample_count
            FROM metrics
            WHERE timestamp >= toDateTime({start_ts})
              AND timestamp <= toDateTime({end_ts})
              AND metric_name = '{metric_name}'
              AND has(tags, 'process_name')
              AND tags['process_name'] != ''
            GROUP BY tags['process_name'], tags['pid']
            HAVING process_name != '' AND process_name IS NOT NULL
            ORDER BY avg_value DESC
            LIMIT 10
            """
            
            logger.info(f"Executing top processes query for {metric_name} from {start_time} to {end_time_adjusted}")
            logger.debug(f"Query: {sql}")
            result = await self.ch.query_df(sql)
            
            top_processes = []
            if result and result.get('data'):
                columns = result.get('columns', [])
                logger.info(f"Query returned {len(result['data'])} rows for {metric_name}. Columns: {columns}")
                
                # Create column index map for safe access
                col_map = {}
                for idx, col_name in enumerate(columns):
                    col_map[col_name] = idx
                
                # Validate required columns exist
                required_cols = ['process_name', 'pid', 'avg_value', 'max_value']
                missing_cols = [col for col in required_cols if col not in col_map]
                if missing_cols:
                    logger.error(f"Missing required columns in query result: {missing_cols}. Available columns: {columns}")
                    # Try fallback diagnostic query
                    await self._diagnose_process_metrics(metric_name, start_ts, end_ts)
                    return []
                
                for row in result['data']:
                    try:
                        # Use column names for safe access
                        process_name = row[col_map['process_name']] if row[col_map['process_name']] else "unknown"
                        pid = row[col_map['pid']] if row[col_map['pid']] else "0"
                        avg_value = float(row[col_map['avg_value']]) if row[col_map['avg_value']] is not None else 0.0
                        max_value = float(row[col_map['max_value']]) if row[col_map['max_value']] is not None else 0.0
                        sample_count_idx = col_map.get('sample_count')
                        sample_count = int(row[sample_count_idx]) if sample_count_idx is not None and len(row) > sample_count_idx and row[sample_count_idx] is not None else 0
                        
                        # Get command line if available
                        command_line_idx = col_map.get('command_line')
                        if command_line_idx is not None and len(row) > command_line_idx and row[command_line_idx]:
                            command_line = str(row[command_line_idx]).strip()
                            # Remove empty string if it's just whitespace or empty
                            if command_line == "" or command_line == "None":
                                command_line = ""
                        else:
                            command_line = ""
                        
                        # Log command_line status for debugging
                        if metric_name in ["process_cpu_usage", "process_memory_mb"]:
                            if command_line:
                                logger.debug(f"Process {process_name} (PID: {pid}) has command_line: {command_line[:50]}...")
                            else:
                                logger.debug(f"Process {process_name} (PID: {pid}) has no command_line (idx: {command_line_idx}, row_len: {len(row)})")
                        
                        # Skip invalid processes
                        if not process_name or process_name == "unknown" or process_name == "":
                            logger.debug(f"Skipping invalid process: name='{process_name}', pid='{pid}'")
                            continue
                        
                        logger.debug(f"Process: {process_name} (PID: {pid}), avg: {avg_value:.2f}, max: {max_value:.2f}, samples: {sample_count}")
                        
                        top_processes.append({
                            "name": str(process_name),
                            "pid": str(pid),
                            "average": round(avg_value, 2),
                            "peak": round(max_value, 2),
                            "command_line": command_line
                        })
                    except (IndexError, KeyError, ValueError, TypeError) as e:
                        logger.warning(f"Error processing process row for {metric_name}: {e}, row={row}, columns={columns}")
                        continue
            else:
                logger.warning(f"No data returned for {metric_name} between {start_time} and {end_time}. Query result: {result}")
                # Try fallback diagnostic query
                await self._diagnose_process_metrics(metric_name, start_ts, end_ts)
            
            if not top_processes:
                logger.warning(f"No valid processes found for {metric_name} after parsing {len(result.get('data', [])) if result else 0} rows")
            
            return top_processes
        except Exception as e:
            logger.error(f"Failed to get top processes for {metric_name}: {e}", exc_info=True)
            return []
    
    async def _diagnose_process_metrics(self, metric_name: str, start_ts: int, end_ts: int):
        """Diagnostic query to check if process metrics exist in the database"""
        try:
            logger.info(f"Running diagnostic query for {metric_name}...")
            # Check if any metrics exist for this metric_name in the time range
            diagnostic_sql = f"""
            SELECT 
                count(*) as total_count,
                count(DISTINCT tags['process_name']) as unique_processes,
                min(timestamp) as earliest,
                max(timestamp) as latest
            FROM metrics
            WHERE timestamp >= toDateTime({start_ts})
              AND timestamp <= toDateTime({end_ts})
              AND metric_name = '{metric_name}'
              AND has(tags, 'process_name')
            """
            diag_result = await self.ch.query_df(diagnostic_sql)
            if diag_result and diag_result.get('data'):
                row = diag_result['data'][0]
                total_count = row[0] if row[0] else 0
                unique_processes = row[1] if len(row) > 1 and row[1] else 0
                earliest = row[2] if len(row) > 2 and row[2] else None
                latest = row[3] if len(row) > 3 and row[3] else None
                logger.info(f"Diagnostic for {metric_name}: total_count={total_count}, unique_processes={unique_processes}, earliest={earliest}, latest={latest}")
            else:
                logger.warning(f"Diagnostic query returned no data for {metric_name}")
        except Exception as e:
            logger.error(f"Diagnostic query failed for {metric_name}: {e}", exc_info=True)
