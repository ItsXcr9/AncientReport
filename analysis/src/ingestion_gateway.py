"""
NATS Ingestion Gateway
Consumes metrics from NATS JetStream and:
1. Writes to ClickHouse in batches (persistence)
2. Broadcasts to WebSocket clients (real-time)
"""
import asyncio
import logging
from typing import List
from datetime import datetime
import msgpack
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext

from storage.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Enable DEBUG logging for ingestion gateway

# Will be set by main.py to enable WebSocket broadcasting
websocket_broadcast_func = None

def set_broadcast_function(func):
    """Set the WebSocket broadcast function"""
    global websocket_broadcast_func
    websocket_broadcast_func = func


class IngestionGateway:
    """
    Consumes metrics from NATS JetStream and batches writes to ClickHouse
    """
    
    def __init__(self, nats_url: str, clickhouse_client: ClickHouseClient):
        self.nats_url = nats_url
        self.clickhouse = clickhouse_client
        self.nc: NATS = None
        self.js: JetStreamContext = None
        self.batch_buffer: List[dict] = []
        self.batch_size = 5  # Flush very frequently for testing
        
    async def connect(self):
        """Connect to NATS JetStream"""
        logger.info(f"Connecting to NATS at {self.nats_url}...")
        self.nc = NATS()
        await self.nc.connect(servers=[self.nats_url])
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS JetStream")
        
        # Ensure METRICS stream exists (should match agent's stream config)
        try:
            from nats.js.api import StreamConfig, RetentionPolicy, StorageType
            
            stream_config = StreamConfig(
                name="METRICS",
                subjects=["metrics.system.*", "metrics.network.*", "metrics.disk.*", "metrics.process.*"],
                retention=RetentionPolicy.LIMITS,
                max_bytes=1_000_000_000,  # 1GB
                max_age=86400,  # 24 hours
                storage=StorageType.FILE
            )
            
            # Try to get or create the stream
            try:
                await self.js.stream_info("METRICS")
                logger.info("✓ METRICS stream exists")
            except:
                await self.js.add_stream(stream_config)
                logger.info("✓ Created METRICS stream")
                
        except Exception as e:
            logger.warning(f"Could not ensure METRICS stream: {e}")
            logger.warning("Stream should be created by agent, continuing anyway...")
        
    async def start(self):
        """Start consuming from NATS and writing to ClickHouse using pull-based consumer"""
        try:
            await self.connect()
            
            # Use pull-based consumer (recommended for ingestion pipelines)
            logger.info("Creating pull consumer for metrics.> on stream METRICS...")
            
            # Try to delete existing consumer first (in case it's stuck)
            try:
                await self.js.delete_consumer(stream="METRICS", consumer="clickhouse_writer")
                logger.info("Deleted old consumer")
            except:
                pass  # Consumer doesn't exist, that's fine
            
            psub = await self.js.pull_subscribe(
                subject="metrics.>",
                stream="METRICS",
                durable="clickhouse_writer"
            )
            
            logger.info("✅ Pull consumer 'clickhouse_writer' created on METRICS stream")
            logger.info("   Subject filter: metrics.>")
            logger.info("   Starting fetch loop...")
            
            # Main consumption loop
            loop_count = 0
            while True:
                try:
                    loop_count += 1
                    if loop_count % 10 == 1:
                        logger.info(f"💓 Fetch loop heartbeat (iteration {loop_count})")
                    
                    # Fetch batch of messages (up to 10 at a time)
                    logger.debug("Calling psub.fetch(batch=10, timeout=5)...")
                    msgs = await psub.fetch(batch=10, timeout=5)
                    
                    logger.info(f"📬 Fetched {len(msgs)} messages from NATS (subject: metrics.>)")
                    
                    # Process each message
                    for msg in msgs:
                        try:
                            # Deserialize MessagePack payload
                            metrics = msgpack.unpackb(msg.data, raw=False)
                            
                            # DEBUG: Log every message to see what's coming through
                            logger.info(f"📥 Received message: type={type(metrics)}, is_list={isinstance(metrics, list)}, count={len(metrics) if isinstance(metrics, list) else 'N/A'}")
                            
                            # Log first message
                            if not hasattr(self, '_logged_first'):
                                logger.info(f"✅ First NATS message! Type: {type(metrics)}, Count: {len(metrics) if isinstance(metrics, list) else 1}")
                                if isinstance(metrics, list) and len(metrics) > 0 and isinstance(metrics[0], dict):
                                    logger.info(f"   Sample: hostname={metrics[0].get('hostname')}, metric={metrics[0].get('metric_name')}, ts={metrics[0].get('timestamp')}")
                                self._logged_first = True
                            
                            # Process metrics - agent sends list of Metric structs
                            if isinstance(metrics, list):
                                logger.debug(f"Processing list of {len(metrics)} items")
                                added_count = 0
                                skipped_count = 0
                                for i, metric in enumerate(metrics):
                                    logger.debug(f"  Item {i}: type={type(metric)}, is_dict={isinstance(metric, dict)}")
                                    
                                    # Handle nested list format (agent bug workaround)
                                    if isinstance(metric, list) and len(metric) > 0:
                                        metric = metric[0]  # Unwrap the nested list
                                    
                                    if isinstance(metric, dict):
                                        hostname = metric.get('hostname')
                                        if hostname:
                                            self.batch_buffer.append(metric)
                                            added_count += 1
                                            logger.debug(f"  ✓ Added metric: {metric.get('metric_name')} from {hostname}")
                                            
                                            # V2: Broadcast to WebSocket clients immediately for real-time updates
                                            if websocket_broadcast_func:
                                                try:
                                                    await websocket_broadcast_func(metric)
                                                except Exception as e:
                                                    logger.debug(f"WebSocket broadcast failed: {e}")
                                        else:
                                            skipped_count += 1
                                            logger.warning(f"  ✗ Skipping metric (no hostname): {metric.get('metric_name', 'unknown')}")
                                    else:
                                        skipped_count += 1
                                        logger.warning(f"  ✗ Skipping non-dict item: type={type(metric)}")
                                
                                logger.info(f"📊 Processed list: added={added_count}, skipped={skipped_count}, buffer_size={len(self.batch_buffer)}")
                                                
                            elif isinstance(metrics, dict) and metrics.get('hostname'):
                                self.batch_buffer.append(metrics)
                                logger.info(f"Added 1 dict metric to buffer (buffer size now: {len(self.batch_buffer)})")
                                
                                # V2: Broadcast to WebSocket
                                if websocket_broadcast_func:
                                    try:
                                        await websocket_broadcast_func(metrics)
                                    except Exception as e:
                                        logger.debug(f"WebSocket broadcast failed: {e}")
                            else:
                                logger.warning(f"⚠️ Unhandled message format: type={type(metrics)}, has_hostname={'hostname' in metrics if isinstance(metrics, dict) else 'N/A'}")
                            
                            # IMPORTANT: Always ack() after successful processing
                            await msg.ack()
                            logger.debug(f"✓ Acked message")
                            
                        except Exception as e:
                            logger.error(f"❌ Error processing message: {e}", exc_info=True)
                            # Negative ack to retry later
                            try:
                                await msg.nak()
                            except:
                                pass
                    
                    # Flush if batch is full
                    if len(self.batch_buffer) >= self.batch_size:
                        logger.info(f"📦 Buffer full ({len(self.batch_buffer)} metrics), flushing to ClickHouse...")
                        await self.flush_batch()
                
                except TimeoutError:
                    # No messages available (normal), flush any pending buffer
                    logger.debug("Fetch timeout (no messages), flushing buffer if not empty...")
                    if self.batch_buffer:
                        logger.info(f"⏰ Periodic flush of {len(self.batch_buffer)} buffered metrics")
                        await self.flush_batch()
                    continue
                    
                except Exception as e:
                    logger.error(f"❌ Error in fetch loop: {e}", exc_info=True)
                    await asyncio.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Ingestion gateway error: {e}")
            raise
    
    async def flush_batch(self):
        """Flush batch buffer to ClickHouse"""
        if not self.batch_buffer:
            return
        
        try:
            count = len(self.batch_buffer)
            
            # Log first few metrics for debugging
            if count > 0:
                sample = self.batch_buffer[0] if self.batch_buffer else {}
                logger.info(f"Batch of {count} items - Sample: hostname={sample.get('hostname')}, metric={sample.get('metric_name')}, ts={sample.get('timestamp')}")
            
            # Convert to ClickHouse format
            # Separate metrics by destination table
            generic_metrics_rows = []
            network_metrics_rows = []
            anomaly_rows = []
            
            for metric in self.batch_buffer:
                try:
                    # Handle both dict and object-like structures
                    if not isinstance(metric, dict):
                        logger.warning(f"Skipping non-dict metric: {type(metric)}")
                        continue
                    
                    # Parse timestamp
                    ts_val = metric.get('timestamp')
                    hostname_val = metric.get('hostname')
                    
                    # Validation
                    if not hostname_val or hostname_val == 'unknown':
                        continue
                        
                    # Normalize timestamp to datetime object
                    timestamp = datetime.utcnow()
                    if ts_val:
                        if isinstance(ts_val, str):
                            try:
                                timestamp = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
                            except:
                                try:
                                    timestamp = datetime.strptime(ts_val, '%Y-%m-%d %H:%M:%S')
                                except:
                                    pass
                        elif isinstance(ts_val, (int, float)):
                            try:
                                timestamp = datetime.fromtimestamp(ts_val)
                            except:
                                pass
                    
                    # 1. Check if this is a Network Metric Sample (has latency_p50)
                    if 'latency_p50' in metric:
                        row = (
                            timestamp,
                            str(hostname_val),
                            float(metric.get('latency_p50', 0)),
                            float(metric.get('latency_p90', 0)),
                            float(metric.get('latency_p99', 0)),
                            int(metric.get('retransmits', 0)),
                            int(metric.get('packet_drops', 0)),
                            int(metric.get('active_connections', 0)),
                            int(metric.get('established', 0)),
                            float(metric.get('open_rate', 0)),
                            float(metric.get('close_rate', 0)),
                            float(metric.get('memory_used_percent', 0)),
                            float(metric.get('cpu_system_percent', 0)),
                            float(metric.get('softirq_net_percent', 0)),
                            float(metric.get('socket_queue_pressure', 0)),
                            int(1 if metric.get('oom_risk') else 0)
                        )
                        network_metrics_rows.append(row)
                        
                    # 2. Check if this is an Anomaly Event (has event_type)
                    elif 'event_type' in metric and 'severity' in metric:
                        row = (
                            timestamp,
                            str(hostname_val),
                            str(metric.get('event_type')),
                            str(metric.get('severity')),
                            metric.get('process'), # Nullable
                            str(metric.get('description', '')),
                            float(metric.get('value', 0)),
                            float(metric.get('threshold', 0))
                        )
                        anomaly_rows.append(row)
                        
                    # 3. Default to Generic Metric
                    else:
                        tags_value = metric.get('tags', {})
                        tags_dict = {str(k): str(v) for k, v in tags_value.items()} if isinstance(tags_value, dict) else {}
                        
                        row = (
                            timestamp,
                            str(hostname_val),
                            str(metric.get('metric_type', 'system')),
                            str(metric.get('metric_name', 'unknown')),
                            float(metric.get('value', 0)),
                            tags_dict
                        )
                        generic_metrics_rows.append(row)
                        
                except Exception as e:
                    logger.error(f"Error converting metric: {e}, metric: {metric}")
                    continue
            
            # Batch insert to ClickHouse tables
            if generic_metrics_rows:
                logger.info(f"Inserting {len(generic_metrics_rows)} rows to 'metrics' table...")
                await self.clickhouse.insert('metrics', generic_metrics_rows)
                
            if network_metrics_rows:
                logger.info(f"Skipping {len(network_metrics_rows)} rows to 'network_metrics_ts' table due to schema mismatch...")
                # await self.clickhouse.insert('network_metrics_ts', network_metrics_rows)
                
            if anomaly_rows:
                logger.info(f"Inserting {len(anomaly_rows)} rows to 'network_anomalies' table...")
                await self.clickhouse.insert('network_anomalies', anomaly_rows)
                
            logger.info(f"✅ Flushed batch: {len(generic_metrics_rows)} generic, {len(network_metrics_rows)} network, {len(anomaly_rows)} anomalies")
            
            # Clear buffer
            self.batch_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}", exc_info=True)
            self.batch_buffer.clear()
    
    async def close(self):
        """Close NATS connection"""
        if self.nc:
            await self.nc.drain()
            await self.nc.close()
