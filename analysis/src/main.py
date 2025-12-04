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
from utils.timezone import now, from_iso, format_for_display, format_for_chart, TEHRAN_TZ

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AncientReport AI Analysis Engine",
    description="AI-powered infrastructure analysis and reporting",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(containers.router, prefix="/api/containers", tags=["containers"])
app.include_router(healthchecks.router, prefix="/api", tags=["healthchecks"])

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
    
    scheduler.start()
    logger.info("✓ Scheduler started")
    
    # Log next run times
    hourly_job = scheduler.get_job('hourly_analysis')
    daily_job = scheduler.get_job('daily_analysis')
    if hourly_job:
        next_hourly = hourly_job.next_run_time
        logger.info(f"   Next hourly analysis: {next_hourly}")
    if daily_job:
        next_daily = daily_job.next_run_time
        logger.info(f"   Next daily analysis: {next_daily}")
    
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
    
    logger.info("🎉 AncientReport AI Analysis Engine is running!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    if scheduler:
        scheduler.shutdown()
    if ingestion_gateway and hasattr(ingestion_gateway, 'nc') and ingestion_gateway.nc:
        await ingestion_gateway.nc.close()
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
              AND metric_name IN ('cpu_cores', 'memory_total_mb', 'disk_total_gb')
              AND timestamp >= now() - INTERVAL 7 DAY
            GROUP BY metric_name
            """
            
            result = await clickhouse_client.query_df(info_query)
            
            # Build server info from query results
            info = {
                "hostname": hostname,
                "cpu_cores": 0,
                "memory_total_gb": 0,
                "disk_total_gb": 0
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
          AND metric_name IN ('cpu_cores', 'memory_total_mb', 'disk_total_gb')
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY metric_name
        """
        
        result = await clickhouse_client.query_df(info_query)
        
        # Build server info from query results
        info = {
            "hostname": hostname,
            "cpu_cores": 0,
            "memory_total_gb": 0,
            "disk_total_gb": 0
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
        
        if report is None:
            # If specific hostname report not found, try to trigger a quick analysis for it
            # This is useful for the first time a server is selected
            if hostname:
                 # We won't await this to avoid blocking, but it means the first request might still return no data
                 # Alternatively, we could just return a "no data" message
                 pass

            return {
                "report_id": None,
                "system_health": {"overall_score": 0, "status": "no_data"},
                "message": f"No reports available yet for {key}. Trigger an analysis to generate a report."
            }
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
        await run_hourly_analysis(hostname)
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
