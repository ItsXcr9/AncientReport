import asyncio
from nats.aio.client import Client as NATS
import json

async def main():
    nc = NATS()
    try:
        await nc.connect(servers=["nats://nats:4222"])
        js = nc.jetstream()
        
        print("--- Stream Info ---")
        try:
            info = await js.stream_info("METRICS")
            print(f"Stream Name: {info.config.name}")
            print(f"Subjects: {info.config.subjects}")
            print(f"Messages: {info.state.messages}")
            print(f"Bytes: {info.state.bytes}")
            print(f"Consumers: {info.state.consumer_count}")
        except Exception as e:
            print(f"Error getting stream info: {e}")

        print("\n--- Consumer Info ---")
        try:
            cinfo = await js.consumer_info("METRICS", "clickhouse_writer")
            print(f"Consumer Name: {cinfo.name}")
            print(f"Deliver Subject: {cinfo.config.deliver_subject}")
            print(f"Filter Subject: {cinfo.config.filter_subject}")
            print(f"Ack Floor: {cinfo.ack_floor}")
            print(f"Num Pending: {cinfo.num_pending}")
            print(f"Num Redelivered: {cinfo.num_redelivered}")
        except Exception as e:
            print(f"Error getting consumer info: {e}")
            
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        await nc.close()

if __name__ == "__main__":
    asyncio.run(main())
