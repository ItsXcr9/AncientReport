
import asyncio
import os
from clickhouse_driver import Client

def run_debug():
    try:
        # Connect to localhost since we will run this INSIDE the analysis container
        client = Client(
            host='clickhouse',
            user=os.getenv('CLICKHOUSE_USER', 'AncientReport'),
            password=os.getenv('CLICKHOUSE_PASSWORD', 'AncientReport'),
            database=os.getenv('CLICKHOUSE_DB', 'AncientReport')
        )

        
        query = """
            SELECT 
                toStartOfInterval(timestamp, INTERVAL 30 SECOND) as ts,
                argMax(hostname, timestamp) as host,

                
                maxIf(value, metric_name = 'network_bytes_sent') as bytes_sent,
                maxIf(value, metric_name = 'network_bytes_received') as bytes_recv,
                maxIf(value, metric_name = 'network_packets_sent') as pkts_sent,
                maxIf(value, metric_name = 'network_packets_received') as pkts_recv,

                maxIf(value, metric_name = 'network_connection_open_rate') as open_rate,
                maxIf(value, metric_name = 'network_connection_close_rate') as close_rate,
                maxIf(value, metric_name = 'network_latency_p50') as latency_p50,
                maxIf(value, metric_name = 'network_latency_p90') as latency_p90,
                maxIf(value, metric_name = 'network_latency_p99') as latency_p99,
                maxIf(value, metric_name = 'network_active_connections_detailed') as active_opens_detailed,
                maxIf(value, metric_name = 'network_active_connections') as active_opens_legacy,
                maxIf(value, metric_name = 'network_established') as established,
                maxIf(value, metric_name = 'network_time_wait') as time_wait,
                maxIf(value, metric_name = 'network_close_wait') as close_wait,
                maxIf(value, metric_name = 'network_retransmits') - minIf(value, metric_name = 'network_retransmits') as retransmits,
                maxIf(value, metric_name = 'network_drops') - minIf(value, metric_name = 'network_drops') as drops,
                maxIf(value, metric_name = 'softirq_net_percent') as softirq,
                maxIf(value, metric_name = 'cpu_system_percent') as cpu_system,
                maxIf(value, metric_name = 'socket_queue_pressure') as socket_pressure,
                maxIf(value, metric_name = 'disk_reads_per_sec') as disk_reads,
                maxIf(value, metric_name = 'disk_writes_per_sec') as disk_writes,
                maxIf(value, metric_name = 'disk_latency_ms') as disk_latency,
                maxIf(value, metric_name = 'disk_usage_percent') as disk_usage
            FROM metrics
            WHERE hostname = 'xcr9'
              AND timestamp >= now() - INTERVAL 10 MINUTE
              AND metric_name IN ('network_drops', 'network_bytes_sent', 'network_bytes_received', 
                                  'network_packets_sent', 'network_packets_received',
                                  'network_connection_open_rate', 'network_connection_close_rate', 
                                  'network_latency_p50', 'network_latency_p90', 'network_latency_p99',
                                  'network_active_connections', 'network_active_connections_detailed', 'network_established',
                                  'network_time_wait', 'network_close_wait', 'network_retransmits',
                                  'softirq_net_percent', 'cpu_system_percent', 'socket_queue_pressure',
                                  'disk_reads_per_sec', 'disk_writes_per_sec', 'disk_latency_ms', 'disk_usage_percent')
            GROUP BY ts
            ORDER BY ts DESC
            LIMIT 720
        """
        
        print("Executing query...")
        result = client.execute(query)
        print(f"Result count: {len(result)}")
        if len(result) > 0:
            print(f"First row: {result[0]}")
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    run_debug()
