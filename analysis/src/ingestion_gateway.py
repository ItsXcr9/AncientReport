"""
NATS Ingestion Gateway
Consumes metrics from NATS JetStream and writes to ClickHouse in batches
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
        self.batch_size = 500
        
    async def connect(self):
        """Connect to NATS JetStream"""
        logger.info(f"Connecting to NATS at {self.nats_url}...")
        self.nc = NATS()
        await self.nc.connect(servers=[self.nats_url])
        self.js = self.nc.jetstream()
        logger.info("Connected to NATS JetStream")
        
    async def start(self):
        """Start consuming from NATS and writing to ClickHouse"""
        try:
            await self.connect()
            
            # Subscribe to metrics stream with pull consumer
            subscription = await self.js.pull_subscribe(
                subject="metrics.>",
                durable="clickhouse_writer"
            )
            
            logger.info("Started ingestion gateway, consuming from METRICS stream")
            
            # Continuously fetch messages
            while True:
                try:
                    # Fetch batch of messages (up to 10 at a time)
                    msgs = await subscription.fetch(batch=10, timeout=5)
                    
                    for msg in msgs:
                        try:
                            # Deserialize MessagePack payload
                            metrics = msgpack.unpackb(msg.data, raw=False)
                            
                            # Flatten nested structures (only flatten lists, not dicts)
                            def flatten_metrics(data):
                                """Recursively flatten metrics to list of dicts"""
                                result = []
                                if isinstance(data, dict):
                                    # Check if this is a valid metric (has required fields)
                                    if 'timestamp' in data or 'hostname' in data or 'value' in data:
                                        result.append(data)
                                    else:
                                        # This is probably nested data (like tags), skip it
                                        pass
                                elif isinstance(data, list):
                                    for item in data:
                                        if isinstance(item, dict):
                                            # Only add if it looks like a metric
                                            if 'timestamp' in item or 'hostname' in item or 'value' in item:
                                                result.append(item)
                                        elif isinstance(item, list):
                                            # Recursively flatten nested lists
                                            result.extend(flatten_metrics(item))
                                return result
                            
                            # Add flattened metrics to batch buffer
                            flattened = flatten_metrics(metrics)
                            if flattened:
                                self.batch_buffer.extend(flattened)
                            elif isinstance(metrics, dict) and ('timestamp' in metrics or 'value' in metrics):
                                # Single metric, add directly
                                self.batch_buffer.append(metrics)
                            
                            # Flush if batch is full
                            if len(self.batch_buffer) >= self.batch_size:
                                await self.flush_batch()
                            
                            # Acknowledge message
                            await msg.ack()
                            
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                            # Negative acknowledge to retry
                            await msg.nak()
                            
                except asyncio.TimeoutError:
                    # No messages available, flush any pending buffer
                    if self.batch_buffer:
                        await self.flush_batch()
                    continue
                    
                except Exception as e:
                    logger.error(f"Error fetching messages: {e}")
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
            
            # Log first few metrics for debugging (only on first batch)
            if count > 0 and count < 50:  # Only log first batch
                logger.info(f"Sample metric from NATS: {self.batch_buffer[0] if self.batch_buffer else 'empty'}")
            
            # Convert to ClickHouse format
            rows = []
            for metric in self.batch_buffer:
                try:
                    # Handle both dict and object-like structures
                    if not isinstance(metric, dict):
                        # Skip non-dict metrics
                        logger.warning(f"Skipping non-dict metric: {type(metric)}")
                        continue
                    
                    # Parse timestamp - handle multiple formats
                    ts = metric.get('timestamp')
                    
                    # Handle None/missing timestamp
                    if ts is None:
                        logger.warning(f"Metric missing timestamp, using current time: {metric.get('metric_name', 'unknown')}")
                        timestamp = datetime.utcnow()
                    elif isinstance(ts, str):
                        # Try to parse ISO format or other common formats
                        try:
                            timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        except:
                            # Try common timestamp formats
                            try:
                                timestamp = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                            except:
                                logger.warning(f"Could not parse timestamp string: {ts}, using current time")
                                timestamp = datetime.utcnow()
                    elif isinstance(ts, (int, float)):
                        # Unix timestamp (seconds since epoch)
                        try:
                            timestamp = datetime.utcfromtimestamp(ts)
                        except (ValueError, OSError) as e:
                            logger.warning(f"Invalid unix timestamp {ts}: {e}, using current time")
                            timestamp = datetime.utcnow()
                    elif isinstance(ts, datetime):
                        timestamp = ts
                    else:
                        logger.warning(f"Unknown timestamp type {type(ts)}, using current time")
                        timestamp = datetime.utcnow()
                    
                    # Build row tuple for ClickHouse (must match table schema)
                    # tags column is Map(String, String) so it needs a dict with string keys/values
                    tags_value = metric.get('tags', {})
                    if isinstance(tags_value, dict):
                        # Ensure all values are strings (ClickHouse Map requires string values)
                        tags_dict = {str(k): str(v) for k, v in tags_value.items()}
                    else:
                        tags_dict = {}
                    
                    row = (
                        timestamp,  # timestamp (DateTime)
                        str(metric.get('hostname', 'unknown')),  # hostname (String)
                        str(metric.get('metric_type', 'system')),  # metric_type (String)
                        str(metric.get('metric_name', 'unknown')),  # metric_name (String)
                        float(metric.get('value', 0)),  # value (Float64)
                        tags_dict  # tags (Map(String, String))
                    )
                    
                    rows.append(row)
                except Exception as e:
                    logger.error(f"Error converting metric: {e}, metric: {metric}")
                    continue
            
            if rows:
                # Batch insert to ClickHouse
                await self.clickhouse.insert('metrics', rows)
                logger.info(f"Flushed {len(rows)} metrics to ClickHouse (from {count} total)")
            else:
                logger.warning(f"No valid metrics to flush from {count} items")
            
            # Clear buffer
            self.batch_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}", exc_info=True)
            # Clear buffer anyway to avoid infinite retry of bad data
            self.batch_buffer.clear()
    
    async def close(self):
        """Close NATS connection"""
        if self.nc:
            await self.nc.drain()
            await self.nc.close()
