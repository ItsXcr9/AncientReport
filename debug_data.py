
import asyncio
import os
from clickhouse_driver import Client

def run_debug():
    try:
        client = Client(
            host='clickhouse',
            user=os.getenv('CLICKHOUSE_USER', 'AncientReport'),
            password=os.getenv('CLICKHOUSE_PASSWORD', 'AncientReport'),
            database=os.getenv('CLICKHOUSE_DB', 'AncientReport')
        )
        

        # Check timestamps
        print("Checking timestamps...")
        time_res = client.execute("SELECT now(), toTimeZone(now(), 'UTC')")
        print(f"ClickHouse Server Time: {time_res[0][0]}")
        
        max_ts_res = client.execute("SELECT max(timestamp) FROM metrics WHERE hostname = 'xcr9'")
        print(f"Max xcr9 Timestamp: {max_ts_res[0][0]}")

        
        # List metric names
        query_names = "SELECT DISTINCT metric_name FROM metrics WHERE hostname = 'xcr9' AND timestamp >= now() - INTERVAL 15 MINUTE"
        print("Available metric names:")
        for row in client.execute(query_names):
            print(f"- {row[0]}")

    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    run_debug()
