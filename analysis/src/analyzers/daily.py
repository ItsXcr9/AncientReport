from datetime import date, datetime, timedelta
from typing import Dict, List
import logging

from storage.bucket_manager import BucketManager

logger = logging.getLogger(__name__)


class DailyAnalyzer:
    """
    Performs daily analysis of system metrics with long-term trends
    """
    
    def __init__(self, clickhouse_client, ai_engine):
        self.ch = clickhouse_client
        self.ai = ai_engine
        self.bucket_manager = BucketManager()
        logger.info("DailyAnalyzer initialized with BucketManager")
    
    async def run_analysis(self, target_date: date, hostname: str = None) -> Dict:
        """Run complete daily analysis using data from buckets"""
        logger.info(f"Starting daily analysis for {target_date}{f' (hostname={hostname})' if hostname else ''}")
        
        try:
            # Load hourly summaries from buckets instead of querying ClickHouse
            hourly_summaries = self.bucket_manager.get_daily_processed(
                datetime.combine(target_date, datetime.min.time()),
                hostname=hostname
            )
            
            if not hourly_summaries:
                logger.warning(f"No hourly summaries found in buckets for {target_date}")
                return self._empty_report(target_date, hostname)
            
            logger.info(f"Loaded {len(hourly_summaries)} hourly summaries from buckets")
            
            # Aggregate metrics from hourly summaries
            aggregated_metrics = self._aggregate_hourly_summaries(hourly_summaries)
            
            # Extract top processes across the day
            top_processes_daily = self._aggregate_top_processes(hourly_summaries)
            
            # Identify trends
            trends = self._identify_trends(hourly_summaries)
            
            # Build AI context
            context = self._build_daily_context(aggregated_metrics, trends, top_processes_daily, target_date, hostname)
            
            # Generate AI insights
            ai_insights = await self._generate_daily_insights(context)
            
            # Build report
            report = {
                "report_id": f"{target_date.isoformat()}_daily",
                "date": target_date.isoformat(),
                "hostname": hostname or "all",
                "hours_analyzed": len(hourly_summaries),
                "metrics": aggregated_metrics,
                "top_processes": top_processes_daily,
                "trends": trends,
                "ai_insights": ai_insights
            }
            
            logger.info(f"Daily analysis complete for {target_date}: {len(hourly_summaries)} hours analyzed")
            return report
            
        except Exception as e:
            logger.error(f"Daily analysis failed for {target_date}: {e}", exc_info=True)
            return self._empty_report(target_date, hostname)

    def _empty_report(self, target_date: date, hostname: str = None) -> Dict:
        """Returns an empty report structure for failed or no-data analysis."""
        return {
            "report_id": f"{target_date.isoformat()}_daily_empty",
            "date": target_date.isoformat(),
            "hostname": hostname or "all",
            "hours_analyzed": 0,
            "metrics": {},
            "top_processes": [],
            "trends": {},
            "ai_insights": "No data or analysis failed."
        }
    
    def _aggregate_hourly_summaries(self, summaries: List[Dict]) -> Dict:
        """Aggregate metrics from hourly summaries"""
        # Placeholder - extract and average resource usage from all summaries
        cpu_values = []
        memory_values = []
        
        for summary in summaries:
            if "summary" in summary and "resource_usage" in summary["summary"]:
                ru = summary["summary"]["resource_usage"]
                if "cpu" in ru and "average" in ru["cpu"]:
                    cpu_values.append(ru["cpu"]["average"])
                if "memory" in ru and "average" in ru["memory"]:
                    memory_values.append(ru["memory"]["average"])
        
        return {
            "cpu_average": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
            "memory_average": sum(memory_values) / len(memory_values) if memory_values else 0
        }
    
    def _aggregate_top_processes(self, summaries: List[Dict]) -> Dict:
        """Extract top processes across all hourly summaries"""
        return {}  # Placeholder
    
    def _identify_trends(self, summaries: List[Dict]) -> Dict:
        """Identify daily trends"""
        return {}  # Placeholder
    
    def _build_daily_context(self, metrics: Dict, trends: Dict, processes: Dict, target_date: date, hostname: str) -> Dict:
        """Build context for AI"""
        return {
            "date": target_date.isoformat(),
            "hostname": hostname or "all",
            "metrics": metrics
        }
    
    async def _generate_daily_insights(self, context: Dict) -> str:
        """Generate AI insights for daily summary"""
        return "Daily AI insights not yet implemented"

