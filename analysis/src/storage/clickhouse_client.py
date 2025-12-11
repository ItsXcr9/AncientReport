import logging
from clickhouse_driver import Client
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ClickHouseClient:
    """
    Client for interacting with ClickHouse time-series database
    """
    
    def __init__(self, host: str = "localhost", port: int = 8123, database: str = "AncientReport", user: str = "default", password: str = ""):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        
        # Use clickhouse-driver's native protocol (port 9000 inside Docker)
        # When running inside Docker network, use 9000 (internal). External access uses 6001 mapping.
        self.client = Client(host=host, port=9000, database=database, user=user, password=password)
        
        logger.info(f"ClickHouse client initialized: {host}:{port}/{database} (user: {user})")
    
    async def query(self, sql: str) -> List[tuple]:
        """Execute a query and return results"""
        try:
            logger.debug(f"Executing query: {sql[:100]}...")
            result = self.client.execute(sql)
            return result
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise
    
    async def query_df(self, sql: str) -> Dict[str, Any]:
        """Execute a query and return as dictionary"""
        try:
            result = self.client.execute(sql, with_column_types=True)
            if not result:
                return {"columns": [], "data": []}
            
            rows, columns_with_types = result
            column_names = [col[0] for col in columns_with_types]
            
            return {"columns": column_names, "data": rows}
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise
    
    async def get_metrics_aggregated(
        self, 
        start_time: datetime, 
        end_time: datetime, 
        metric_name: str = None,
        hostname: str = None
    ) -> Dict[str, Any]:
        """Fetch pre-aggregated metrics for a time range"""
        
        # Use ClickHouse's toDateTime() to handle timezone properly
        # Convert Python datetime to Unix timestamp, then to ClickHouse DateTime
        # This avoids timezone issues
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        
        # Use toDateTime() with Unix timestamp for timezone-safe conversion
        where_clause = f"WHERE timestamp >= toDateTime({start_ts}) AND timestamp <= toDateTime({end_ts})"
        if metric_name:
            where_clause += f" AND metric_name = '{metric_name}'"
        
        if hostname:
            where_clause += f" AND hostname = '{hostname}'"
        
        sql = f"""
        SELECT 
            metric_name,
            min(value) as min_value,
            max(value) as max_value,
            avg(value) as avg_value,
            quantile(0.5)(value) as p50,
            quantile(0.95)(value) as p95,
            quantile(0.99)(value) as p99,
            stddevPop(value) as std_dev,
            count(*) as sample_count
        FROM metrics
        {where_clause}
        GROUP BY metric_name
        """
        
        logger.debug(f"Executing aggregation query: {sql[:200]}...")
        logger.debug(f"Time range: {start_time} to {end_time} (timestamps: {start_ts} to {end_ts})")
        result = await self.query_df(sql)
        
        if result and result.get('data'):
            logger.info(f"Query returned {len(result['data'])} metric types")
        else:
            logger.warning(f"No data returned for query between {start_time} and {end_time}")
            # Try alternative query using NOW() for comparison
            alt_sql = f"""
            SELECT 
                metric_name,
                count(*) as sample_count,
                max(timestamp) as latest
            FROM metrics
            WHERE timestamp >= now() - INTERVAL 1 HOUR
            GROUP BY metric_name
            LIMIT 10
            """
            alt_result = await self.query_df(alt_sql)
            if alt_result and alt_result.get('data'):
                logger.warning(f"Found {len(alt_result['data'])} metrics in last hour using NOW(), suggesting timezone mismatch")
        
        return result
    
    async def get_metrics_raw(
        self, 
        start_time: datetime, 
        end_time: datetime, 
        metric_name: str,
        limit: int = 1000,
        hostname: str = None
    ) -> List[tuple]:
        """Fetch raw metrics for charting - expects UTC datetime (ClickHouse stores in UTC)"""
        
        # Ensure timezone-aware datetime - assume system local time (Tehran) if naive
        # or just let timestamp() handle it (it uses system local for naive)
        pass
        
        # Use Unix timestamps for timezone-safe conversion
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        
        # Build WHERE clause with optional hostname filter
        where_clauses = [
            f"timestamp >= toDateTime({start_ts})",
            f"timestamp <= toDateTime({end_ts})",
            f"metric_name = '{metric_name}'"
        ]
        
        if hostname:
            where_clauses.append(f"hostname = '{hostname}'")
        
        where_clause = " AND ".join(where_clauses)
        
        sql = f"""
        SELECT 
            timestamp,
            value
        FROM metrics
        WHERE {where_clause}
        ORDER BY timestamp ASC
        LIMIT {limit}
        """
        
        logger.debug(f"Fetching raw metrics: {metric_name} from {start_time} to {end_time} (ts: {start_ts}-{end_ts}){f' for hostname={hostname}' if hostname else ' (all servers)'}")
        result = await self.query(sql)
        logger.debug(f"Retrieved {len(result)} rows for {metric_name}")
        return result
    
    async def insert(self, table: str, data: list):
        """Insert data into table"""
        try:
            if not data:
                return
            
            self.client.execute(f"INSERT INTO {table} VALUES", data)
            logger.info(f"Inserted {len(data)} rows into {table}")
        except Exception as e:
            logger.error(f"Insert failed: {e}")
            raise

    async def get_active_servers(self, hours: int = 24) -> List[str]:
        """Get list of servers that have reported metrics recently
        
        Filters out container IDs (12-char hex strings) that shouldn't be treated as hostnames
        """
        try:
            sql = f"""
            SELECT DISTINCT hostname 
            FROM metrics 
            WHERE timestamp >= now() - INTERVAL {hours} HOUR
              AND hostname != ''
              AND length(hostname) != 12
            ORDER BY hostname
            """
            result = await self.query(sql)
            
            # Additional filter: exclude hostnames that look like container IDs (all hex chars)
            servers = []
            for row in result:
                hostname = row[0]
                # Skip if it looks like a container ID (12 chars, all lowercase hex)
                if len(hostname) == 12 and all(c in '0123456789abcdef' for c in hostname.lower()):
                    logger.debug(f"Filtering out container ID hostname: {hostname}")
                    continue
                servers.append(hostname)
            
            return servers
        except Exception as e:
            logger.error(f"Failed to get active servers: {e}")
            return []
