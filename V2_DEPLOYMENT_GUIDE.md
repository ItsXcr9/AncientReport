# V2 Deployment Guide - Bug Fix Applied

## Quick Start

```bash
# SSH to server
ssh root@65.109.200.75
cd /home/AncientReport

# Pull latest code with fix
git pull origin develop

# Restart analysis service
docker compose restart analysis

# Verify data flow
bash verify-v2-flow.sh
```

## What Was Fixed

### Critical Bug in Ingestion Gateway
**File**: `analysis/src/ingestion_gateway.py`

**Problem**: Message acknowledgment was incorrectly placed inside a conditional block, causing:
- Only 1% of messages acknowledged (when buffer reached 100 items)
- 99% of messages redelivered by NATS repeatedly
- Data never reaching ClickHouse or WebSocket clients
- Charts showing no data

**Solution**: Moved `await msg.ack()` to correct position in the message processing loop, ensuring every message is acknowledged after successful processing.

## V2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     V2 Streaming Pipeline                    │
└─────────────────────────────────────────────────────────────┘

Agent (Rust)                    Analysis Service (Python)
┌──────────┐                    ┌────────────────────────┐
│  eBPF    │                    │  Ingestion Gateway     │
│ Metrics  │ ──(1s)──> NATS ───>│  - Consumes NATS      │
│Collection│           JetStream │  - Batches to CH      │
└──────────┘                    │  - Broadcasts WS      │
                                └────────────────────────┘
                                         │         │
                                         ▼         ▼
                                  ClickHouse   WebSocket
                                  (Storage)    (Real-time)
                                                   │
                                                   ▼
                                              UI (React)
                                              - Historical API
                                              - Real-time WS
                                              - LiveChart
```

## Data Flow Step-by-Step

### 1. Agent Collection (Every 1 second)
- Collects metrics via eBPF and /proc
- Serializes to MessagePack
- Publishes to NATS subjects: `metrics.system.*`, `metrics.network.*`, etc.

### 2. NATS JetStream (Message Queue)
- Stores messages in stream "METRICS"
- Retention: 24 hours or 1GB
- Pull-based consumer: "clickhouse_writer"

### 3. Ingestion Gateway (Python)
- Fetches messages in batches (10 at a time)
- **Acknowledges each message** (FIX APPLIED HERE)
- Adds to buffer (max 100 items)
- Broadcasts to WebSocket clients immediately
- Flushes to ClickHouse when buffer full or timeout

### 4. ClickHouse (Storage)
- Receives batch inserts
- Stores in `metrics` table
- Indexed by timestamp, hostname, metric_name

### 5. WebSocket (Real-time)
- Broadcasts metrics to all connected UI clients
- Message format: `{"type": "metric", "data": {...}}`
- Heartbeat every 30 seconds

### 6. UI (React + Zustand)
- Connects to WebSocket on mount
- Stores real-time metrics in ring buffer (1000 points)
- Fetches historical data from API
- Merges historical + real-time in LiveChart
- Updates every second

## Verification Checklist

### On Server (SSH)

```bash
# 1. Check all containers running
docker ps

# 2. Check agent sending to NATS
docker logs AncientReport-agent --tail 50 | grep "Published"
# Expected: "Published X metrics to NATS"

# 3. Check ingestion gateway receiving
docker logs AncientReport-analysis --tail 100 | grep "Fetched"
# Expected: "📬 Fetched N messages from NATS"
# Expected: "✓ Acked message"

# 4. Check ClickHouse has data
docker exec AncientReport-clickhouse clickhouse-client -q "
SELECT count(*) FROM metrics WHERE timestamp >= now() - INTERVAL 5 MINUTE
"
# Expected: > 0 (should have hundreds or thousands)

# 5. Run verification script
bash verify-v2-flow.sh
```

### In Browser

1. **Open UI**: http://65.109.200.75:6080

2. **Check V2 Indicator**:
   - Look for "V2 Live" badge in header (green, pulsing)
   - If shows "V1 Mode", WebSocket not connected

3. **Check Charts**:
   - CPU Usage chart should show data
   - Memory Usage chart should show data
   - Look for "LIVE" badge on charts (green, pulsing)
   - Charts should update smoothly every second

4. **Check Browser Console** (F12):
   ```
   [Realtime] WebSocket connected
   [WebSocket] Connected
   ```

5. **Check Network Tab** (F12):
   - WebSocket connection to `ws://65.109.200.75:6080/ws/metrics`
   - Status: 101 Switching Protocols (green)
   - Messages flowing (check WS frames)

## Troubleshooting

### Issue: "V1 Mode" showing instead of "V2 Live"

**Cause**: WebSocket not connecting

**Solutions**:
```bash
# Check analysis service logs
docker logs AncientReport-analysis | grep -i websocket

# Check if WebSocket endpoint exists
curl -i http://localhost:6800/ws/metrics
# Should return: 426 Upgrade Required (normal for HTTP request to WS endpoint)

# Restart analysis service
docker compose restart analysis
```

### Issue: Charts show no data

**Cause 1**: No metrics in ClickHouse
```bash
# Check if agent is running
docker ps | grep agent

# Check agent logs
docker logs AncientReport-agent --tail 50

# Check ClickHouse
docker exec AncientReport-clickhouse clickhouse-client -q "
SELECT count(*) FROM metrics WHERE timestamp >= now() - INTERVAL 1 HOUR
"
```

**Cause 2**: API endpoints not working
```bash
# Test CPU endpoint
curl http://localhost:6800/api/metrics/cpu | jq '.data | length'
# Should return number > 0

# Check analysis logs
docker logs AncientReport-analysis --tail 100
```

**Cause 3**: Time range issue
```bash
# Check server time
date

# Check ClickHouse time
docker exec AncientReport-clickhouse clickhouse-client -q "SELECT now()"

# Should be in Asia/Tehran timezone
```

### Issue: WebSocket connects but no real-time updates

**Cause**: Ingestion gateway not broadcasting

**Solution**:
```bash
# Check if broadcast function is set
docker logs AncientReport-analysis | grep "WebSocket broadcasting enabled"

# Check for broadcast errors
docker logs AncientReport-analysis | grep "broadcast failed"

# Restart to reinitialize
docker compose restart analysis
```

### Issue: High memory usage

**Cause**: Ring buffer not limiting properly

**Check**:
- Open browser console
- Check Zustand store size
- Should max out at 1000 points per metric

**Solution**: Already implemented in code (ring buffer)

## Performance Metrics

### Expected Performance
- **Latency**: Agent → UI < 100ms
- **Throughput**: 50-100 metrics/second
- **Memory**: UI ~100MB, Analysis ~150MB
- **CPU**: Agent <3%, Analysis <5%

### Monitoring
```bash
# Check resource usage
docker stats

# Check NATS stats
curl http://localhost:8222/varz | jq

# Check ClickHouse query performance
docker exec AncientReport-clickhouse clickhouse-client -q "
SELECT 
    query_duration_ms,
    query,
    event_time
FROM system.query_log
WHERE event_time >= now() - INTERVAL 1 HOUR
ORDER BY event_time DESC
LIMIT 10
"
```

## Rollback Plan

If issues occur, rollback to V1 mode:

```bash
# Edit docker-compose.yml
# Comment out NATS_URL in both agent and analysis services

# Restart
docker compose down
docker compose up -d

# UI will show "V1 Mode" and use polling instead
```

## Next Steps

### Optional Enhancements
1. **Alert Thresholds**: Configure in analysis service
2. **Custom Dashboards**: Add to UI
3. **Multi-server View**: Already supported
4. **Export Data**: Add CSV/JSON export
5. **Dark Mode**: Add theme toggle

### Monitoring
1. Set up alerts for container health
2. Monitor NATS message queue depth
3. Monitor ClickHouse disk usage
4. Monitor WebSocket connection count

## Support

### Logs Location
- Agent: `docker logs AncientReport-agent`
- Analysis: `docker logs AncientReport-analysis`
- ClickHouse: `docker logs AncientReport-clickhouse`
- UI: `docker logs AncientReport-ui`
- NATS: `docker logs AncientReport-nats`

### Debug Endpoints
- Health: http://localhost:6800/api/
- Metrics Debug: http://localhost:6800/api/debug/metrics-detail
- Servers: http://localhost:6800/api/servers
- Latest Report: http://localhost:6800/api/reports/latest

### Files Modified
- `analysis/src/ingestion_gateway.py` - Fixed message acknowledgment

### Documentation
- [BUGFIX_V2_DATA_FLOW.md](BUGFIX_V2_DATA_FLOW.md) - Detailed bug explanation
- [UI_V2_CHANGES.md](UI_V2_CHANGES.md) - UI features
- [VERSION2_PROPOSAL.md](VERSION2_PROPOSAL.md) - Architecture design

## Success Criteria

✅ All containers running  
✅ Agent publishing to NATS  
✅ Ingestion gateway consuming and acknowledging  
✅ Metrics in ClickHouse  
✅ WebSocket connected  
✅ UI shows "V2 Live"  
✅ Charts display data  
✅ Real-time updates working  

---

**Status**: ✅ Bug Fixed - Ready for Deployment  
**Date**: December 3, 2025  
**Version**: 2.0.1

