"""
NATS Ingestion Gateway
Consumes metrics from NATS JetStream and writes to ClickHouse in batches
"""
import asyncio
import logging
from typing import List
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
        await self.connect()
        
        # Subscribe to metrics stream
        subscription = await self.js.subscribe(
            subject="metrics.>",
            stream="METRICS",
            durable_name="clickhouse_writer"
        )
        
        logger.info("Started ingestion gateway, consuming from METRICS stream")
        
        async for msg in subscription.messages:
            try:
                # Deserialize MessagePack payload
                metrics = msgpack.unpackb(msg.data, raw=False)
                
                # Add to batch buffer
                if isinstance(metrics, list):
                    self.batch_buffer.extend(metrics)
                else:
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
    
    async def flush_batch(self):
        """Flush batch buffer to ClickHouse"""
        if not self.batch_buffer:
            return
        
        try:
            count = len(self.batch_buffer)
            
            # Convert to ClickHouse format
            rows = []
            for metric in self.batch_buffer:
                row = {
                    'timestamp': metric['timestamp'],
                    'hostname': metric['hostname'],
                    'metric_type': metric['metric_type'],
                    'metric_name': metric['metric_name'],
                    'value': float(metric['value']),
                    'tags': metric.get('tags', {})
                }
                rows.append(row)
            
            # Batch insert to ClickHouse
            self.clickhouse.client.insert('metrics', rows)
            logger.info(f"Flushed {count} metrics to ClickHouse")
            
            # Clear buffer
            self.batch_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}")
            # Don't clear buffer on error, will retry
    
    async def close(self):
        """Close NATS connection"""
        if self.nc:
            await self.nc.drain()
            await self.nc.close()
