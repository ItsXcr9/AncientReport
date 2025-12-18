import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import logging
import os

from analyzers.hourly import HourlyAnalyzer
from analyzers.daily import DailyAnalyzer
from storage.clickhouse_client import ClickHouseClient
from storage.bucket_manager import BucketManager
from storage.settings_manager import init_settings_manager, get_settings_manager
from ai.engine import AIEngine
from ingestion_gateway import IngestionGateway
from api import containers
from api import healthchecks
from api import custom_monitors  # V3
from api import security as security_api  # V3
from api.custom_monitors import load_monitors_from_clickhouse as load_monitors
from utils.timezone import now, from_iso, format_for_display, format_for_chart, TEHRAN_TZ

# Configure logging - default to WARNING to reduce noise
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Data retention configuration (in days)
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "3"))

# Initialize FastAPI app
app = FastAPI(
    title="AncientReport AI Analysis Engine V3",
    description="AI-powered infrastructure analysis and reporting with custom monitoring and security scanning",
    version="3.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register V1/V2 routers
app.include_router(containers.router, prefix="/api/containers", tags=["containers"])
app.include_router(healthchecks.router, prefix="/api", tags=["healthchecks"])

# Register V3 routers
from api import alerts as alerts_api
from api import topology as topology_api
from api import ebpf_data as ebpf_api
from api import security_scanning as sec_scan_api
from api.security_scanning import load_scans_from_clickhouse as load_security_scans, start_nats_subscriber as start_security_nats_subscriber
from api import ai_chat as ai_chat_api
from api import auto_remediation as remediation_api
from api import ai_intelligence as ai_intelligence_api  # V3 AI Intelligence
app.include_router(custom_monitors.router, tags=["V3 Custom Monitors"])
app.include_router(security_api.router, tags=["V3 Security"])
app.include_router(alerts_api.router, tags=["V3 Alerts"])
app.include_router(topology_api.router, tags=["V3 Topology"])
app.include_router(ebpf_api.router, tags=["V3 eBPF Data"])
app.include_router(sec_scan_api.router, tags=["V3 Security Scanning"])
app.include_router(ai_chat_api.router, tags=["V3 AI Chat"])
app.include_router(ai_intelligence_api.router, tags=["V3 AI Intelligence"])
app.include_router(remediation_api.router, tags=["V3 Auto-Remediation"])

# Register V3 Container Application Monitoring (Kafka, Redis, PostgreSQL)
from api import container_apps as container_apps_api
app.include_router(container_apps_api.router, tags=["V3 Container Apps Monitoring"])

# Register V4 Prometheus-compatible Metrics Scraping (replaces Prometheus + Grafana)
from api import prometheus as prometheus_api
app.include_router(prometheus_api.router, prefix="/api/prometheus", tags=["V4 Metrics Scraping"])

# Register V5 Custom Dashboards & Metric Alerts
from api import dashboards as dashboards_api
from api import alerts as metric_alerts_api
app.include_router(dashboards_api.router, tags=["V5 Dashboards"])
app.include_router(metric_alerts_api.router, tags=["V5 Metric Alerts"])

# Register V6 Recording Rules (pre-aggregation)
from api import recording_rules as recording_rules_api
app.include_router(recording_rules_api.router, tags=["V6 Recording Rules"])

# Register V7 SNMP Monitoring
from api import snmp as snmp_api
app.include_router(snmp_api.router, tags=["V7 SNMP Monitoring"])

# Register V8 Advanced Analytics (ML Anomaly Detection, SLO Tracking, Synthetic Monitoring, Alert Correlation)
from api import analytics as analytics_api
from api import slo as slo_api
from api import synthetics as synthetics_api
from api import incidents as incidents_api
app.include_router(analytics_api.router, tags=["V8 Analytics & ML"])
app.include_router(slo_api.router, tags=["V8 SLO Tracking"])
app.include_router(synthetics_api.router, tags=["V8 Synthetic Monitoring"])
app.include_router(incidents_api.router, tags=["V8 Alert Incidents"])

# Register V9 Rate Query Functions (PromQL-equivalent rate/irate/increase/delta)
from api import rate_query as rate_query_api
app.include_router(rate_query_api.router, tags=["V9 Rate Queries"])

# Register V10 Internal Metrics & Self-Monitoring
from api import internal_metrics as internal_metrics_api
app.include_router(internal_metrics_api.router, tags=["V10 Internal Metrics"])

# Register V11 Live Alerts API (real-time alerts for dashboard)
from api import live_alerts as live_alerts_api
app.include_router(live_alerts_api.router, tags=["V11 Live Alerts"])

# Import and register metrics API (History Charts)
# NOTE: The metrics_api router is NOT registered here because main.py already defines
# /api/metrics/* endpoints inline (lines 828-1055) with correct metric names and response format.
# The api/metrics.py has wrong metric names (memory_used_percent vs memory_usage_percent) 
# and wrong response format (bare list vs {"data": [...]}), which broke CPU, Memory, Network charts.
# Keeping the import for metrics_api.set_clickhouse_client() call in startup_event.
from api import metrics as metrics_api
# app.include_router(metrics_api.router, prefix="/api/metrics", tags=["System Metrics"])

# Import and register realtime WebSocket router
from api import realtime
app.include_router(realtime.router, tags=["realtime"])

# Global instances
clickhouse_client = None
ai_engine = None
hourly_analyzer = None
daily_analyzer = None
scheduler = None
bucket_manager = None
ingestion_gateway = None
settings_manager = None
latest_reports = {}  # Store the latest hourly reports per hostname
_reports_loaded = False


# ClickHouse persistence for latest reports
async def save_latest_report_to_clickhouse(hostname: str, report: dict):
    """Save latest analysis report to ClickHouse."""
    import json
    import httpx
    
    ch_host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    ch_port = os.getenv("CLICKHOUSE_PORT", "8123")
    ch_db = os.getenv("CLICKHOUSE_DB", "AncientReport")
    ch_user = os.getenv("CLICKHOUSE_USER", "default")
    ch_password = os.getenv("CLICKHOUSE_PASSWORD", "")
    
    try:
        report_id = report.get('report_id', f"report-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        timestamp = report.get('timestamp', datetime.utcnow().isoformat())
        
        # Convert timestamp to ClickHouse format
        if isinstance(timestamp, str) and 'T' in timestamp:
            timestamp = timestamp.replace('T', ' ')[:19]
        elif hasattr(timestamp, 'strftime'):
            timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # Extract system_health score - handle both dict and int formats
        system_health = report.get('system_health', {})
        if isinstance(system_health, dict):
            health_score = system_health.get('overall_score', 100)
        else:
            health_score = system_health if isinstance(system_health, (int, float)) else 100
        
        # Safely serialize JSON fields
        def safe_json(data, default):
            try:
                return json.dumps(data if data else default).replace("'", "\\'").replace("\\n", " ")
            except Exception as e:
                logger.warning(f"JSON serialization failed: {e}")
                return json.dumps(default)
        
        metrics_json = safe_json(report.get('resource_usage', {}), {})
        ai_insights_json = safe_json(report.get('ai_insights', {}), {})
        recommendations_json = safe_json(report.get('recommendations', []), [])
        capacity_json = safe_json(report.get('capacity_forecast', {}), {})
        
        query = f"""
        INSERT INTO hourly_reports (report_id, timestamp, hostname, system_health, metrics, ai_insights, recommendations, capacity_forecast)
        VALUES (
            '{report_id}',
            '{timestamp}',
            '{hostname}',
            {int(health_score)},
            '{metrics_json}',
            '{ai_insights_json}',
            '{recommendations_json}',
            '{capacity_json}'
        )
        """
        
        url = f"http://{ch_host}:{ch_port}/"
        params = {"database": ch_db, "query": query}
        if ch_user:
            params["user"] = ch_user
        if ch_password:
            params["password"] = ch_password
        
        logger.info(f"Saving analysis report for {hostname} to ClickHouse (report_id={report_id}, health={health_score})...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to save report to ClickHouse: {response.status_code} - {response.text}")
            else:
                logger.info(f"✓ Saved analysis report for {hostname} to ClickHouse")
    except Exception as e:
        logger.error(f"Error saving latest report to ClickHouse: {e}", exc_info=True)


async def load_latest_reports_from_clickhouse():
    """Load most recent analysis reports from ClickHouse on startup."""
    global latest_reports, _reports_loaded
    import json
    import httpx
    
    ch_host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    ch_port = os.getenv("CLICKHOUSE_PORT", "8123")
    ch_db = os.getenv("CLICKHOUSE_DB", "AncientReport")
    ch_user = os.getenv("CLICKHOUSE_USER", "default")
    ch_password = os.getenv("CLICKHOUSE_PASSWORD", "")
    
    logger.info(f"Loading latest analysis reports from ClickHouse ({ch_host}:{ch_port}/{ch_db})...")
    
    try:
        # Get the most recent report for each hostname
        query = """
        SELECT report_id, timestamp, hostname, system_health, metrics, ai_insights, recommendations, capacity_forecast
        FROM hourly_reports
        WHERE (hostname, timestamp) IN (
            SELECT hostname, max(timestamp) FROM hourly_reports GROUP BY hostname
        )
        FORMAT JSONEachRow
        """
        
        url = f"http://{ch_host}:{ch_port}/"
        params = {"database": ch_db, "query": query}
        if ch_user:
            params["user"] = ch_user
        if ch_password:
            params["password"] = ch_password
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200 and response.text.strip():
                logger.info(f"ClickHouse query returned {len(response.text)} bytes of data")
                for line in response.text.strip().split('\n'):
                    if line:
                        try:
                            row = json.loads(line)
                            hostname = row.get('hostname', 'all')
                            
                            # Parse JSON fields with individual error handling
                            def safe_parse_json(data, field_name, default):
                                if not data:
                                    return default
                                if isinstance(data, dict) or isinstance(data, list):
                                    return data
                                if isinstance(data, str):
                                    try:
                                        return json.loads(data)
                                    except json.JSONDecodeError as e:
                                        logger.warning(f"Failed to parse {field_name}: {e}")
                                        return default
                                return default
                            
                            metrics = safe_parse_json(row.get('metrics'), 'metrics', {})
                            ai_insights = safe_parse_json(row.get('ai_insights'), 'ai_insights', {})
                            recommendations = safe_parse_json(row.get('recommendations'), 'recommendations', [])
                            capacity = safe_parse_json(row.get('capacity_forecast'), 'capacity_forecast', {})
                            
                            # Reconstruct system_health as a dict
                            health_score = row.get('system_health', 100)
                            if isinstance(health_score, (int, float)):
                                system_health = {
                                    'overall_score': int(health_score),
                                    'status': 'healthy' if health_score >= 80 else 'warning' if health_score >= 50 else 'critical'
                                }
                            else:
                                system_health = health_score
                            
                            report = {
                                'report_id': row.get('report_id'),
                                'timestamp': row.get('timestamp'),
                                'hostname': hostname,
                                'system_health': system_health,
                                'resource_usage': metrics,
                                'ai_insights': ai_insights,
                                'recommendations': recommendations,
                                'capacity_forecast': capacity
                            }
                            
                            key = hostname if hostname and hostname != 'all' else 'all'
                            latest_reports[key] = report
                            logger.info(f"Loaded latest report for {key} from ClickHouse (health: {health_score})")
                        except Exception as e:
                            logger.error(f"Failed to parse report row: {e}")
                
                logger.info(f"✓ Loaded {len(latest_reports)} latest reports from ClickHouse")
            else:
                logger.warning(f"No previous reports found in ClickHouse (status={response.status_code}, empty={not response.text.strip()})")
    except Exception as e:
        logger.error(f"Error loading latest reports from ClickHouse: {e}", exc_info=True)
    
    _reports_loaded = True

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    global clickhouse_client, ai_engine, hourly_analyzer, daily_analyzer, scheduler, bucket_manager, ingestion_gateway, settings_manager
    
    logger.info("🚀 Starting AncientReport AI Analysis Engine...")
    
    # Detect if running in V2 mode (with NATS)
    nats_url = os.getenv("NATS_URL", "")
    v2_mode = bool(nats_url)
    
    if v2_mode:
        logger.info("🚀 Running in V2 STREAMING mode")
    else:
        logger.info("📊 Running in V1 LEGACY mode")
    
    # Initialize ClickHouse client
    clickhouse_client = ClickHouseClient(
        host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        database=os.getenv("CLICKHOUSE_DB", "AncientReport"),
        user=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "")
    )
    logger.info("✓ ClickHouse client initialized")
    
    # Set ClickHouse client in containers and healthchecks modules
    containers.set_clickhouse_client(clickhouse_client)
    healthchecks.set_clickhouse_client(clickhouse_client)
    ebpf_api.set_clickhouse_client(clickhouse_client)
    metrics_api.set_clickhouse_client(clickhouse_client)
    
    # Initialize ClickHouse tables for network metrics
    await ebpf_api.ensure_network_metrics_tables()
    
    # Initialize ClickHouse tables for container apps
    await container_apps_api.ensure_container_app_tables()
    
    # Initialize AI engine
    ai_provider = os.getenv("AI_PROVIDER", "google")
    ai_model = os.getenv("AI_MODEL", "gemini-2.5-flash-lite")
    ai_engine = AIEngine(provider=ai_provider, model=ai_model)
    logger.info("✓ AI engine initialized")
    
    # Initialize analyzers
    hourly_analyzer = HourlyAnalyzer(clickhouse_client, ai_engine)
    daily_analyzer = DailyAnalyzer(clickhouse_client, ai_engine)
    logger.info("✓ Analyzers initialized")
    
    # Initialize bucket manager
    bucket_manager = BucketManager()
    logger.info("✓ Bucket manager initialized")
    
    # Initialize settings manager
    settings_manager = init_settings_manager(clickhouse_client)
    logger.info("✓ Settings manager initialized")
    
    # Initialize scheduler
    scheduler = AsyncIOScheduler()
    
    # Schedule hourly analysis (every hour at minute 0)
    scheduler.add_job(
        run_hourly_analysis,
        'cron',
        minute=0,
        id='hourly_analysis',
        name='Hourly Analysis',
        replace_existing=True
    )
    logger.info("✓ Scheduled hourly analysis (runs every hour at :00)")
    
    # Schedule daily analysis (every day at 23:55)
    scheduler.add_job(
        run_daily_analysis,
        'cron',
        hour=23,
        minute=55,
        id='daily_analysis'
    )
    
    # Schedule bucket cleanup (every hour at minute 30)
    scheduler.add_job(
        cleanup_buckets,
        'cron',
        minute=30,
        id='bucket_cleanup',
        name='Bucket Cleanup',
        replace_existing=True
    )
    logger.info("✓ Scheduled bucket cleanup (runs every hour at :30)")
    
    # Schedule data retention cleanup (daily at 3:00 AM)
    scheduler.add_job(
        cleanup_old_data,
        'cron',
        hour=3,
        minute=0,
        id='data_cleanup',
        name='Data Retention Cleanup',
        replace_existing=True
    )
    logger.info(f"✓ Scheduled data cleanup (daily at 3:00 AM, retention: {DATA_RETENTION_DAYS} days)")
    
    # Schedule network metrics collection (every 30 seconds to reduce CPU load)
    scheduler.add_job(
        ebpf_api.collect_metrics_sample,
        'interval',
        seconds=30,
        id='network_metrics_collection',
        name='Network Metrics Collection',
        replace_existing=True
    )
    logger.info("✓ Scheduled network metrics collection (every 30 seconds)")
    
    # Schedule HTTP client refresh (every 6 hours to prevent FD leaks)
    scheduler.add_job(
        refresh_http_clients,
        'interval',
        hours=6,
        id='http_client_refresh',
        name='HTTP Client Refresh',
        replace_existing=True
    )
    logger.info("✓ Scheduled HTTP client refresh (every 6 hours)")
    
    # Schedule cardinality tracker cleanup (every hour to prevent memory leak)
    async def cleanup_cardinality_cache():
        """Clean up stale series from cardinality tracker to prevent memory leak"""
        try:
            from ingestion_gateway import CARDINALITY_ENABLED
            from cardinality.tracker import get_cardinality_tracker
            if CARDINALITY_ENABLED:
                tracker = get_cardinality_tracker()
                await tracker.cleanup_stale_series(max_age_hours=6)  # Clean entries not seen in 6 hours
                stats = tracker.get_stats()
                logger.info(f"✓ Cardinality cleanup: {stats['total_series']} active series, {stats['dropped_total']} dropped total")
        except Exception as e:
            logger.debug(f"Cardinality cleanup skipped: {e}")
    
    scheduler.add_job(
        cleanup_cardinality_cache,
        'interval',
        hours=1,
        id='cardinality_cleanup',
        name='Cardinality Cache Cleanup',
        replace_existing=True
    )
    logger.info("✓ Scheduled cardinality cache cleanup (every hour)")
    
    # Schedule comprehensive system health check (every minute)
    async def comprehensive_health_check_job():
        """Check all system health: containers, CPU, memory, disk, latency, agents"""
        try:
            from monitors.system_health import run_comprehensive_health_check
            from monitors.alert_manager import trigger_alerts_batch
            
            alerts = await run_comprehensive_health_check(clickhouse_client)
            if alerts:
                # Store alerts in DB and send to Telegram
                triggered = await trigger_alerts_batch(clickhouse_client, alerts)
                if triggered > 0:
                    logger.warning(f"🔔 Health check triggered {triggered} alerts")
        except ImportError as e:
            logger.debug(f"Health monitoring not available: {e}")
        except Exception as e:
            logger.error(f"Health check failed: {e}")
    
    scheduler.add_job(
        comprehensive_health_check_job,
        'interval',
        minutes=1,
        id='comprehensive_health_check',
        name='Comprehensive Health Check',
        replace_existing=True
    )
    logger.info("✓ Scheduled comprehensive health check (every minute)")
    
    scheduler.start()
    logger.info("✓ Scheduler started")
    
    # Load latest reports from ClickHouse
    await load_latest_reports_from_clickhouse()
    logger.info("✓ Loaded latest analysis reports from ClickHouse")
    
    # Load security scan results from ClickHouse
    try:
        await load_security_scans()
        logger.info("✓ Loaded security scan results from ClickHouse")
    except Exception as e:
        logger.warning(f"Could not load security scan results: {e}")
    
    # Start NATS subscriber for remote container scans
    if v2_mode:
        import asyncio
        asyncio.create_task(start_security_nats_subscriber())
        logger.info("✓ Started NATS subscriber for remote container scans")
    
    # Load custom monitors from ClickHouse
    try:
        await load_monitors()
        logger.info("✓ Loaded custom monitors from ClickHouse")
    except Exception as e:
        logger.warning(f"Could not load custom monitors: {e}")
    
    # Log next run times
    hourly_job = scheduler.get_job('hourly_analysis')
    daily_job = scheduler.get_job('daily_analysis')
    if hourly_job:
        next_hourly = hourly_job.next_run_time
        logger.info(f"   Next hourly analysis: {next_hourly}")
    if daily_job:
        next_daily = daily_job.next_run_time
        logger.info(f"   Next daily analysis: {next_daily}")
    
    # Verify security scanning scheduler is initialized
    try:
        from api.security_scanning import scheduler as sec_scheduler
        if sec_scheduler is not None:
            sec_job = sec_scheduler.get_job("daily_security_scan")
            if sec_job:
                next_sec_scan = sec_job.next_run_time
                logger.info(f"✓ Security scan scheduler verified - Next scan: {next_sec_scan}")
            else:
                logger.warning("⚠ Security scan scheduler job not found")
        else:
            logger.warning("⚠ Security scan scheduler not initialized")
    except Exception as e:
        logger.warning(f"⚠ Could not verify security scan scheduler: {e}")
    
    # Start NATS ingestion gateway in V2 mode
    if v2_mode:
        logger.info(f"Starting NATS ingestion gateway (URL: {nats_url})...")
        
        # Import and set WebSocket broadcast function
        try:
            from api.realtime import broadcast_metric
            from ingestion_gateway import set_broadcast_function
            set_broadcast_function(broadcast_metric)
            logger.info("✓ WebSocket broadcasting enabled for real-time metrics")
        except Exception as e:
            logger.warning(f"Could not enable WebSocket broadcasting: {e}")
        
        ingestion_gateway = IngestionGateway(nats_url, clickhouse_client)
        
        # Create task with error handling
        async def run_ingestion_gateway():
            try:
                await ingestion_gateway.start()
            except Exception as e:
                logger.error(f"❌ FATAL: Ingestion gateway crashed: {e}", exc_info=True)
                
        asyncio.create_task(run_ingestion_gateway())
        logger.info("✓ NATS ingestion gateway task created (NATS → ClickHouse + WebSocket)")
    
    # Start Prometheus-compatible metrics scraper
    try:
        prometheus_api.start_scraper()
        logger.info("✓ Metrics scraper started (Prometheus-compatible)")
    except Exception as e:
        logger.warning(f"Could not start metrics scraper: {e}")
    
    # Start metric alert evaluator background task
    try:
        asyncio.create_task(metric_alerts_api.alert_evaluator_loop())
        logger.info("✓ Metric alert evaluator started (30s cycle)")
    except Exception as e:
        logger.warning(f"Could not start alert evaluator: {e}")
    
    # Start recording rules evaluator background task
    try:
        asyncio.create_task(recording_rules_api.run_recording_rules_evaluator())
        logger.info("✓ Recording rules evaluator started (10s cycle)")
    except Exception as e:
        logger.warning(f"Could not start recording rules evaluator: {e}")
    
    # Start SNMP polling loop and initialize templates
    try:
        snmp_api.set_clickhouse_client(clickhouse_client)
        await snmp_api.initialize_default_templates()
        await snmp_api.start_polling_loop()
        logger.info("✓ SNMP monitoring started (polling loop active)")
    except Exception as e:
        logger.warning(f"Could not start SNMP monitoring: {e}")
    
    # Start V8 Advanced Analytics background tasks
    try:
        asyncio.create_task(analytics_api.anomaly_detection_loop())
        logger.info("✓ Anomaly detection loop started (60s cycle)")
    except Exception as e:
        logger.warning(f"Could not start anomaly detection: {e}")
    
    try:
        asyncio.create_task(slo_api.slo_calculation_loop())
        logger.info("✓ SLO calculation loop started (60s cycle)")
    except Exception as e:
        logger.warning(f"Could not start SLO calculation: {e}")
    
    try:
        asyncio.create_task(synthetics_api.synthetic_check_loop())
        logger.info("✓ Synthetic monitoring loop started (10s cycle)")
    except Exception as e:
        logger.warning(f"Could not start synthetic monitoring: {e}")
    
    try:
        asyncio.create_task(incidents_api.alert_correlation_loop())
        logger.info("✓ Alert correlation loop started (30s cycle)")
    except Exception as e:
        logger.warning(f"Could not start alert correlation: {e}")
    
    logger.info("🎉 AncientReport AI Analysis Engine is running!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    if scheduler:
        scheduler.shutdown()
    if ingestion_gateway and hasattr(ingestion_gateway, 'nc') and ingestion_gateway.nc:
        await ingestion_gateway.nc.close()
    
    # Clean up HTTP clients to prevent connection leaks
    try:
        from api.prometheus import close_http_client as close_prometheus_client
        await close_prometheus_client()
        logger.info("Closed Prometheus HTTP client")
    except Exception as e:
        logger.warning(f"Failed to close Prometheus HTTP client: {e}")
    
    try:
        from api.synthetics import _http_client as synthetics_client
        if synthetics_client:
            await synthetics_client.aclose()
            logger.info("Closed Synthetics HTTP client")
    except Exception as e:
        logger.warning(f"Failed to close Synthetics HTTP client: {e}")
    
    logger.info("👋 Shutdown complete")


async def run_hourly_analysis(hostname: str = None):
    """Run hourly analysis job"""
    global latest_reports
    try:
        end_time = now()  # Use Tehran timezone
        logger.info("=" * 60)
        logger.info(f"🔄 Starting scheduled hourly analysis for {end_time}")
        logger.info("=" * 60)
        
        report = await hourly_analyzer.run_analysis(end_time, hostname)
        
        # Store the latest report
        key = hostname if hostname else "all"
        latest_reports[key] = report
        
        # Persist to ClickHouse
        await save_latest_report_to_clickhouse(key, report)
        
        # Log the metrics that were found
        resource_usage = report.get('resource_usage', {})
        cpu_avg = resource_usage.get('cpu', {}).get('average', 0)
        mem_avg = resource_usage.get('memory', {}).get('average', 0)
        
        # Log top processes
        top_processes = report.get('top_processes', {})
        process_count = len(top_processes.get('cpu', []))
        
        logger.info("=" * 60)
        logger.info(f"✅ Hourly analysis complete for {key}!")
        logger.info(f"   Health Score: {report.get('system_health', {}).get('overall_score', 'N/A')}/100")
        logger.info(f"   Status: {report.get('system_health', {}).get('status', 'N/A')}")
        logger.info(f"   CPU: {cpu_avg:.2f}% avg, Memory: {mem_avg:.2f}% avg")
        logger.info(f"   Top Processes: {process_count}")
        logger.info("=" * 60)
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Hourly analysis failed: {e}", exc_info=True)
        logger.error("=" * 60)


async def run_daily_analysis():
    """Run daily analysis job"""
    try:
        date = now().date()  # Use Tehran timezone
        logger.info(f"Running daily analysis for {date}")
        report = await daily_analyzer.run_analysis(date)
        logger.info("✓ Daily analysis complete")
    except Exception as e:
        logger.error(f"Daily analysis failed: {e}", exc_info=True)


async def cleanup_buckets():
    """Run bucket cleanup job"""
    global bucket_manager
    try:
        logger.info("=" * 60)
        logger.info("🧹 Starting bucket cleanup")
        logger.info("=" * 60)
        
        stats = bucket_manager.cleanup_old_buckets()
        
        logger.info("=" * 60)
        logger.info(f"✅ Bucket cleanup complete!")
        logger.info(f"   Raw files deleted: {stats['raw_deleted']}")
        logger.info(f"   Processed files deleted: {stats['processed_deleted']}")
        logger.info(f"   Errors: {stats['errors']}")
        logger.info("=" * 60)
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Bucket cleanup failed: {e}", exc_info=True)
        logger.error("=" * 60)


async def cleanup_old_data():
    """Delete data older than DATA_RETENTION_DAYS from ClickHouse tables."""
    global clickhouse_client
    
    if not clickhouse_client:
        logger.warning("ClickHouse client not available for cleanup")
        return
    
    tables_to_cleanup = [
        # (table_name, date_column)
        ("docker_containers", "timestamp"),
        ("security_scans", "timestamp"),
        ("security_events", "timestamp"),
        ("container_connections", "timestamp"),
        ("custom_monitor_results", "timestamp"),
        ("alert_history", "timestamp"),
        ("hourly_reports", "timestamp"),
        ("metrics", "timestamp"),
        ("events", "timestamp"),
    ]
    
    logger.info(f"🧹 Cleaning up data older than {DATA_RETENTION_DAYS} days...")
    
    total_deleted = 0
    for table, date_col in tables_to_cleanup:
        try:
            # Use ALTER TABLE DELETE for efficient cleanup
            query = f"""
                ALTER TABLE {table} DELETE 
                WHERE {date_col} < now() - INTERVAL {DATA_RETENTION_DAYS} DAY
            """
            clickhouse_client.execute(query)
            logger.info(f"  ✓ Cleaned {table}")
        except Exception as e:
            # Table may not exist or have different schema
            logger.debug(f"  - Skipped {table}: {e}")
    
    logger.info(f"✅ Data cleanup complete (retention: {DATA_RETENTION_DAYS} days)")


async def refresh_http_clients():
    """Periodically refresh HTTP clients to prevent connection pool exhaustion.
    
    This helps prevent file descriptor leaks from accumulated connections
    that may not be properly released over time.
    """
    try:
        logger.info("🔄 Refreshing HTTP clients to prevent connection leaks...")
        
        # Refresh Prometheus HTTP client
        try:
            from api.prometheus import close_http_client as close_prometheus, get_http_client as get_prometheus
            await close_prometheus()
            await get_prometheus()  # Re-create the client
            logger.info("  ✓ Refreshed Prometheus HTTP client")
        except Exception as e:
            logger.warning(f"  - Failed to refresh Prometheus client: {e}")
        
        # Refresh Synthetics HTTP client
        try:
            from api import synthetics
            if synthetics._http_client:
                await synthetics._http_client.aclose()
                synthetics._http_client = None
            await synthetics.get_http_client()  # Re-create
            logger.info("  ✓ Refreshed Synthetics HTTP client")
        except Exception as e:
            logger.warning(f"  - Failed to refresh Synthetics client: {e}")
        
        logger.info("✅ HTTP clients refreshed successfully")
    except Exception as e:
        logger.error(f"❌ HTTP client refresh failed: {e}")


async def get_storage_stats():
    """Get storage usage statistics."""
    import subprocess
    
    try:
        # Get disk usage
        result = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                return {
                    "filesystem": parts[0],
                    "total": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "use_percent": parts[4],
                    "mount": parts[5] if len(parts) > 5 else "/"
                }
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
    
    return None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "AncientReport AI Analysis Engine",
        "version": "1.0.0"
    }


@app.get("/api/")
async def api_root():
    """API root endpoint"""
    return {
        "status": "running",
        "service": "AncientReport AI Analysis Engine",
        "version": "1.0.0"
    }


@app.get("/api/servers")
async def get_servers():
    """Get list of active servers"""
    try:
        servers = await clickhouse_client.get_active_servers()
        return {"servers": servers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/servers/info")
async def get_servers_info():
    """Get hardware information for all servers"""
    try:
        servers = await clickhouse_client.get_active_servers()
        server_info = {}
        
        for hostname in servers:
            # Fetch latest hardware metrics for this server
            # Hardware info doesn't change often, so look back 7 days
            info_query = f"""
            SELECT 
                metric_name,
                argMax(value, timestamp) as value
            FROM metrics
            WHERE hostname = '{hostname}'
              AND metric_name IN ('cpu_cores', 'memory_total_mb', 'disk_total_gb', 'disk_used_gb')
              AND timestamp >= now() - INTERVAL 7 DAY
            GROUP BY metric_name
            """
            
            result = await clickhouse_client.query_df(info_query)
            
            # Build server info from query results
            info = {
                "hostname": hostname,
                "cpu_cores": 0,
                "memory_total_gb": 0,
                "disk_total_gb": 0,
                "disk_used_gb": 0,
                "disk_free_gb": 0
            }
            
            if result and result.get('data'):
                for row in result['data']:
                    metric_name = row[0]
                    value = float(row[1]) if row[1] else 0
                    
                    if metric_name == 'cpu_cores':
                        info["cpu_cores"] = int(value)
                    elif metric_name == 'memory_total_mb':
                        info["memory_total_gb"] = round(value / 1024, 2)
                    elif metric_name == 'disk_total_gb':
                        info["disk_total_gb"] = round(value, 2)
                    elif metric_name == 'disk_used_gb':
                        info["disk_used_gb"] = round(value, 2)
            
            # Calculate free space from total - used
            info["disk_free_gb"] = round(info["disk_total_gb"] - info["disk_used_gb"], 2)
            
            server_info[hostname] = info
        
        return {"servers": server_info}
    except Exception as e:
        logger.error(f"Failed to fetch server info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/servers/info/{hostname}")
async def get_server_info(hostname: str):
    """Get hardware information for a specific server"""
    try:
        # Fetch latest hardware metrics for this server
        # Hardware info doesn't change often, so look back 7 days
        info_query = f"""
        SELECT 
            metric_name,
            argMax(value, timestamp) as value
        FROM metrics
        WHERE hostname = '{hostname}'
          AND metric_name IN ('cpu_cores', 'memory_total_mb', 'disk_total_gb', 'disk_used_gb')
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY metric_name
        """
        
        result = await clickhouse_client.query_df(info_query)
        
        # Build server info from query results
        info = {
            "hostname": hostname,
            "cpu_cores": 0,
            "memory_total_gb": 0,
            "disk_total_gb": 0,
            "disk_used_gb": 0,
            "disk_free_gb": 0
        }
        
        if result and result.get('data'):
            for row in result['data']:
                metric_name = row[0]
                value = float(row[1]) if row[1] else 0
                
                if metric_name == 'cpu_cores':
                    info["cpu_cores"] = int(value)
                elif metric_name == 'memory_total_mb':
                    info["memory_total_gb"] = round(value / 1024, 2)
                elif metric_name == 'disk_total_gb':
                    info["disk_total_gb"] = round(value, 2)
                elif metric_name == 'disk_used_gb':
                    info["disk_used_gb"] = round(value, 2)
        
        # Calculate free space from total - used
        info["disk_free_gb"] = round(info["disk_total_gb"] - info["disk_used_gb"], 2)
        
        return info
    except Exception as e:
        logger.error(f"Failed to fetch server info for {hostname}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/latest")
async def get_latest_report(hostname: str = None):
    """Get the latest hourly report"""
    global latest_reports
    try:
        # If hostname is specified, fetch specific report
        # If not, fetch aggregated report ("all")
        key = hostname if hostname else "all"
        report = latest_reports.get(key)
        
        # Get storage info
        storage_info = await get_storage_stats()
        
        if report is None:
            return {
                "report_id": None,
                "system_health": {"overall_score": 0, "status": "no_data"},
                "message": f"No reports available yet for {key}. Trigger an analysis to generate a report.",
                "storage_info": storage_info,
                "data_retention_days": DATA_RETENTION_DAYS
            }
        
        # Add storage info to existing report
        if isinstance(report, dict):
            report["storage_info"] = storage_info
            report["data_retention_days"] = DATA_RETENTION_DAYS
            
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/hourly/{report_id}")
async def get_hourly_report(report_id: str):
    """Get a specific hourly report by ID"""
    try:
        # TODO: Fetch from ClickHouse
        return {"message": "Report fetching not yet implemented"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/daily/{date}")
async def get_daily_report(date: str):
    """Get daily report for a specific date"""
    try:
        # TODO: Fetch from ClickHouse
        return {"message": "Report fetching not yet implemented"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analysis/trigger/hourly")
async def trigger_hourly_analysis(hostname: str = None):
    """Manually trigger an hourly analysis"""
    try:
        # Convert 'all' to None for correct filtering in analyzer
        target_hostname = None if hostname == "all" else hostname
        
        await run_hourly_analysis(target_hostname)
        
        # Get the report that was just generated
        key = hostname if hostname else "all"
        report = latest_reports.get(key)
        return {
            "status": "success", 
            "message": f"Hourly analysis triggered for {hostname if hostname else 'all servers'}",
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analysis/trigger/daily")
async def trigger_daily_analysis():
    """Manually trigger a daily analysis"""
    try:
        await run_daily_analysis()
        return {"status": "success", "message": "Daily analysis triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/cpu")
async def get_cpu_metrics(start: str = None, end: str = None, hostname: str = None):
    """Get CPU metrics for charting"""
    try:
        if end:
            end_time = from_iso(end)
        else:
            end_time = now()
        
        if start:
            start_time = from_iso(start)
        else:
            start_time = end_time - timedelta(hours=1)
        
        # Pass Tehran time directly (ClickHouse client handles timestamp conversion)
        data = await clickhouse_client.get_metrics_raw(start_time, end_time, "cpu_usage_percent", hostname=hostname)
        
        if data and len(data) > 0:
            logger.info(f"DEBUG: Raw timestamp from driver: {data[0][0]} (type: {type(data[0][0])})")
            
        logger.debug(f"Retrieved {len(data)} CPU metric rows from {start_time} to {end_time}")
        
        # Format for frontend - convert UTC timestamps back to Tehran timezone for display
        formatted = []
        for row in data:
            try:
                timestamp = row[0]
                value = row[1]
                
                # ClickHouse with TZ=Asia/Tehran returns Tehran timestamps (not UTC)
                if isinstance(timestamp, datetime):
                    if timestamp.tzinfo is None:
                        # Naive datetime from ClickHouse is already in Tehran time
                        timestamp = TEHRAN_TZ.localize(timestamp)
                    timestamp_str = format_for_chart(timestamp)
                else:
                    # If it's already a string, try to parse and reformat
                    try:
                        ts_dt = from_iso(str(timestamp))
                        timestamp_str = format_for_chart(ts_dt)
                    except:
                        timestamp_str = str(timestamp)
                
                formatted.append({
                    "timestamp": timestamp_str, 
                    "value": float(value) if value is not None else 0.0
                })
            except Exception as e:
                logger.warning(f"Error formatting row: {e}, row={row}")
                continue
        
        logger.info(f"Formatted {len(formatted)} CPU data points for chart")
        return {"data": formatted}
    except Exception as e:
        logger.error(f"Failed to fetch CPU metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/memory")
async def get_memory_metrics(start: str = None, end: str = None, hostname: str = None):
    """Get memory metrics for charting"""
    try:
        if end:
            end_time = from_iso(end)
        else:
            end_time = now()
        
        if start:
            start_time = from_iso(start)
        else:
            start_time = end_time - timedelta(hours=1)
        
        # Pass Tehran time directly
        data = await clickhouse_client.get_metrics_raw(start_time, end_time, "memory_usage_percent", hostname=hostname)
        
        # Format for frontend - ClickHouse with TZ=Asia/Tehran returns Tehran timestamps
        formatted = []
        for row in data:
            timestamp = row[0]
            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    # Naive datetime from ClickHouse is already in Tehran time
                    timestamp = TEHRAN_TZ.localize(timestamp)
                timestamp_str = format_for_chart(timestamp)
            else:
                try:
                    ts_dt = from_iso(str(timestamp))
                    timestamp_str = format_for_chart(ts_dt)
                except:
                    timestamp_str = str(timestamp)
            formatted.append({"timestamp": timestamp_str, "value": float(row[1])})
        
        return {"data": formatted}
    except Exception as e:
        logger.error(f"Failed to fetch memory metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/disk")
async def get_disk_metrics(start: str = None, end: str = None, hostname: str = None):
    """Get disk I/O metrics for charting"""
    try:
        if end:
            end_time = from_iso(end)
        else:
            end_time = now()
        
        if start:
            start_time = from_iso(start)
        else:
            start_time = end_time - timedelta(hours=1)
        
        # Fetch reads and writes separately
        reads_data = await clickhouse_client.get_metrics_raw(start_time, end_time, "disk_reads_per_sec", hostname=hostname)
        writes_data = await clickhouse_client.get_metrics_raw(start_time, end_time, "disk_writes_per_sec", hostname=hostname)
        
        # Combine into single dataset with both metrics
        data_map = {}
        
        # Process reads
        for row in reads_data:
            timestamp = row[0]
            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    # ClickHouse with TZ=Asia/Tehran returns Tehran timestamps
                    timestamp = TEHRAN_TZ.localize(timestamp)
                timestamp_str = format_for_chart(timestamp)
            else:
                try:
                    ts_dt = from_iso(str(timestamp))
                    timestamp_str = format_for_chart(ts_dt)
                except:
                    timestamp_str = str(timestamp)
            if timestamp_str not in data_map:
                data_map[timestamp_str] = {"timestamp": timestamp_str, "reads": 0, "writes": 0}
            data_map[timestamp_str]["reads"] = float(row[1])
        
        # Process writes
        for row in writes_data:
            timestamp = row[0]
            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    # ClickHouse with TZ=Asia/Tehran returns Tehran timestamps
                    timestamp = TEHRAN_TZ.localize(timestamp)
                timestamp_str = format_for_chart(timestamp)
            else:
                try:
                    ts_dt = from_iso(str(timestamp))
                    timestamp_str = format_for_chart(ts_dt)
                except:
                    timestamp_str = str(timestamp)
            if timestamp_str not in data_map:
                data_map[timestamp_str] = {"timestamp": timestamp_str, "reads": 0, "writes": 0}
            data_map[timestamp_str]["writes"] = float(row[1])
        
        # Convert to sorted list
        formatted = sorted(data_map.values(), key=lambda x: x["timestamp"])
        
        return {"data": formatted}
    except Exception as e:
        logger.error(f"Failed to fetch disk metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/network")
async def get_network_metrics(start: str = None, end: str = None, hostname: str = None):
    """Get network metrics for charting"""
    try:
        if end:
            end_time = from_iso(end)
        else:
            end_time = now()
        
        if start:
            start_time = from_iso(start)
        else:
            start_time = end_time - timedelta(hours=1)
        
        # Fetch sent and received separately
        sent_data = await clickhouse_client.get_metrics_raw(start_time, end_time, "network_packets_sent", hostname=hostname)
        received_data = await clickhouse_client.get_metrics_raw(start_time, end_time, "network_packets_received", hostname=hostname)
        
        # Combine into single dataset with both metrics
        data_map = {}
        
        # Process sent
        for row in sent_data:
            timestamp = row[0]
            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    # ClickHouse with TZ=Asia/Tehran returns Tehran timestamps
                    timestamp = TEHRAN_TZ.localize(timestamp)
                timestamp_str = format_for_chart(timestamp)
            else:
                try:
                    ts_dt = from_iso(str(timestamp))
                    timestamp_str = format_for_chart(ts_dt)
                except:
                    timestamp_str = str(timestamp)
            if timestamp_str not in data_map:
                data_map[timestamp_str] = {"timestamp": timestamp_str, "sent": 0, "received": 0}
            data_map[timestamp_str]["sent"] = float(row[1])
        
        # Process received
        for row in received_data:
            timestamp = row[0]
            if isinstance(timestamp, datetime):
                if timestamp.tzinfo is None:
                    # ClickHouse with TZ=Asia/Tehran returns Tehran timestamps
                    timestamp = TEHRAN_TZ.localize(timestamp)
                timestamp_str = format_for_chart(timestamp)
            else:
                try:
                    ts_dt = from_iso(str(timestamp))
                    timestamp_str = format_for_chart(ts_dt)
                except:
                    timestamp_str = str(timestamp)
            if timestamp_str not in data_map:
                data_map[timestamp_str] = {"timestamp": timestamp_str, "sent": 0, "received": 0}
            data_map[timestamp_str]["received"] = float(row[1])
        
        # Convert to sorted list
        formatted = sorted(data_map.values(), key=lambda x: x["timestamp"])
        
        return {"data": formatted}
    except Exception as e:
        logger.error(f"Failed to fetch network metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debug/metrics")
async def debug_metrics():
    """Debug endpoint to check if metrics exist in ClickHouse"""
    try:
        end_time = now()  # Use Tehran timezone
        start_time = end_time - timedelta(hours=24)  # Check last 24 hours
        
        # Get all metrics from last 24 hours
        result = await clickhouse_client.get_metrics_aggregated(start_time, end_time)
        
        metrics_found = []
        if result and result.get('data'):
            for row in result['data']:
                metrics_found.append({
                    "metric_name": row[0],
                    "min": row[1],
                    "max": row[2],
                    "avg": row[3],
                    "sample_count": row[8]
                })
        
        # Also check for most recent data
        recent_start = end_time - timedelta(minutes=15)
        recent_cpu = await clickhouse_client.get_metrics_raw(
            recent_start, 
            end_time, 
            "cpu_usage_percent",
            limit=1
        )
        
        return {
            "status": "ok",
            "time_range": f"{start_time} to {end_time}",
            "metrics_found": len(metrics_found),
            "metrics": metrics_found,
            "recent_cpu_data": len(recent_cpu) > 0,
            "latest_report": latest_report is not None
        }
    except Exception as e:
        logger.error(f"Debug metrics failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/debug/ai-response")
async def debug_ai_response():
    """Debug endpoint to inspect AI response structure"""
    global latest_report
    try:
        if latest_report is None:
            return {
                "status": "no_report",
                "message": "No report available yet"
            }
        
        ai_insights = latest_report.get('ai_insights', {})
        critical_alerts = ai_insights.get('critical_alerts', [])
        
        return {
            "status": "ok",
            "has_ai_insights": ai_insights is not None,
            "critical_alerts_type": type(critical_alerts).__name__,
            "critical_alerts_count": len(critical_alerts) if isinstance(critical_alerts, list) else 0,
            "critical_alerts": critical_alerts,
            "ai_insights_keys": list(ai_insights.keys()) if isinstance(ai_insights, dict) else [],
            "full_ai_insights": ai_insights
        }
    except Exception as e:
        logger.error(f"Debug AI response failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/bucket/stats")
async def get_bucket_stats():
    """Get bucket storage statistics"""
    try:
        global bucket_manager
        if not bucket_manager:
            return {"error": "Bucket manager not initialized"}
        
        stats = bucket_manager.get_storage_stats()
        return {
            "status": "ok",
            "storage": stats
        }
    except Exception as e:
        logger.error(f"Failed to get bucket stats: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/debug/metrics-detail")
async def debug_metrics_detail():
    """Debug endpoint to check metrics collection status"""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        
        # Check total metrics
        total_query = "SELECT count(*) FROM metrics"
        total_result = await clickhouse_client.query_df(total_query)
        total_count = total_result['data'][0][0] if total_result.get('data') else 0
        
        # Check when the most recent metrics were collected
        latest_query = """
        SELECT 
            max(timestamp) as latest_timestamp,
            min(timestamp) as earliest_timestamp
        FROM metrics
        """
        latest_result = await clickhouse_client.query_df(latest_query)
        latest_timestamp = None
        earliest_timestamp = None
        if latest_result and latest_result.get('data'):
            latest_timestamp = str(latest_result['data'][0][0]) if latest_result['data'][0][0] else None
            earliest_timestamp = str(latest_result['data'][0][1]) if latest_result['data'][0][1] else None
        
        # Check what metric names exist
        metric_names_query = """
        SELECT DISTINCT metric_name 
        FROM metrics 
        ORDER BY metric_name 
        LIMIT 30
        """
        metric_names_result = await clickhouse_client.query_df(metric_names_query)
        available_metrics = []
        if metric_names_result and metric_names_result.get('data'):
            available_metrics = [row[0] for row in metric_names_result['data']]
        
        # Check recent metrics (last hour) - use NOW() for comparison
        recent_query = """
        SELECT 
            metric_name,
            count(*) as count,
            min(timestamp) as earliest,
            max(timestamp) as latest,
            avg(value) as avg_value
        FROM metrics
        WHERE timestamp >= now() - INTERVAL 1 HOUR
        GROUP BY metric_name
        ORDER BY count DESC
        LIMIT 20
        """
        recent_result = await clickhouse_client.query_df(recent_query)
        
        recent_metrics = []
        if recent_result and recent_result.get('data'):
            for row in recent_result['data']:
                recent_metrics.append({
                    "metric_name": row[0],
                    "count": row[1],
                    "earliest": str(row[2]) if row[2] else None,
                    "latest": str(row[3]) if row[3] else None,
                    "avg_value": float(row[4]) if row[4] is not None else 0.0
                })
        
        # Check last 24 hours instead of just 1 hour
        last_24h_query = """
        SELECT 
            metric_name,
            count(*) as count,
            max(timestamp) as latest
        FROM metrics
        WHERE timestamp >= now() - INTERVAL 24 HOUR
        GROUP BY metric_name
        ORDER BY count DESC
        LIMIT 20
        """
        last_24h_result = await clickhouse_client.query_df(last_24h_query)
        
        last_24h_metrics = []
        if last_24h_result and last_24h_result.get('data'):
            for row in last_24h_result['data']:
                last_24h_metrics.append({
                    "metric_name": row[0],
                    "count": row[1],
                    "latest": str(row[2]) if row[2] else None
                })
        
        # Check specific key metrics using NOW() for last hour
        key_metrics = ['cpu_usage_percent', 'memory_usage_percent', 'disk_reads_per_sec', 'network_packets_sent']
        key_metrics_data = {}
        for metric_name in key_metrics:
            check_query = f"""
            SELECT count(*), avg(value), max(value), min(value), max(timestamp) as latest
            FROM metrics
            WHERE metric_name = '{metric_name}'
              AND timestamp >= now() - INTERVAL 1 HOUR
            """
            check_result = await clickhouse_client.query_df(check_query)
            if check_result and check_result.get('data') and check_result['data'][0][0] > 0:
                row = check_result['data'][0]
                key_metrics_data[metric_name] = {
                    "count": row[0],
                    "avg": float(row[1]) if row[1] is not None else 0.0,
                    "max": float(row[2]) if row[2] is not None else 0.0,
                    "min": float(row[3]) if row[3] is not None else 0.0,
                    "latest_timestamp": str(row[4]) if row[4] else None
                }
            else:
                # Check when this metric was last collected
                last_seen_query = f"""
                SELECT max(timestamp) as latest
                FROM metrics
                WHERE metric_name = '{metric_name}'
                """
                last_seen_result = await clickhouse_client.query_df(last_seen_query)
                last_seen = None
                if last_seen_result and last_seen_result.get('data') and last_seen_result['data'][0][0]:
                    last_seen = str(last_seen_result['data'][0][0])
                
                key_metrics_data[metric_name] = {
                    "count": 0, 
                    "avg": 0.0, 
                    "max": 0.0, 
                    "min": 0.0,
                    "last_seen": last_seen
                }
        
        return {
            "status": "ok",
            "total_metrics_in_db": total_count,
            "earliest_timestamp": earliest_timestamp,
            "latest_timestamp": latest_timestamp,
            "available_metric_names": available_metrics,
            "recent_metrics_last_hour": recent_metrics,
            "metrics_last_24h": last_24h_metrics,
            "key_metrics_status": key_metrics_data,
            "current_time": end_time.isoformat(),
            "time_range_checked": "last 1 hour (using NOW() - INTERVAL 1 HOUR)"
        }
    except Exception as e:
        logger.error(f"Debug metrics detail failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/settings")
async def get_settings():
    """Get application settings (sensitive values masked)"""
    try:
        global settings_manager
        if not settings_manager:
            raise HTTPException(status_code=503, detail="Settings manager not initialized")
        
        settings = settings_manager.get_all_settings(mask_sensitive=True)
        
        # Ensure all required keys exist with defaults
        defaults = {
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "telegram_alerts_enabled": "true",
            "gemini_api_key": ""
        }
        
        for key, default_value in defaults.items():
            if key not in settings:
                settings[key] = default_value
        
        return {"settings": settings}
    except Exception as e:
        logger.error(f"Failed to get settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings")
async def update_settings(settings: dict):
    """Update application settings"""
    try:
        global settings_manager, ai_engine
        if not settings_manager:
            raise HTTPException(status_code=503, detail="Settings manager not initialized")
        
        # Validate and update each setting
        for key, value in settings.items():
            if key in ["telegram_bot_token", "telegram_chat_id", "telegram_alerts_enabled", "gemini_api_key"]:
                settings_manager.set_setting(key, str(value))
        
        # If Gemini API key was updated, reinitialize AI engine
        if "gemini_api_key" in settings:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings["gemini_api_key"])
                logger.info("✓ Gemini API key updated")
            except Exception as e:
                logger.warning(f"Failed to reconfigure Gemini API: {e}")
        
        # If Telegram settings changed, reload telegram notifier
        if any(k in settings for k in ["telegram_bot_token", "telegram_chat_id", "telegram_alerts_enabled"]):
            try:
                from alerts.telegram_notifier import reload_telegram_notifier
                reload_telegram_notifier()
                logger.info("✓ Telegram notifier reloaded")
            except Exception as e:
                logger.warning(f"Failed to reload Telegram notifier: {e}")
        
        return {"status": "success", "message": "Settings updated successfully"}
    except Exception as e:
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
