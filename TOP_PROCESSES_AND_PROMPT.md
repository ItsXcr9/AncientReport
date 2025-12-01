# Top Processes Collection & AI Prompt Location

## Top Processes Implementation Status

### ✅ Code is Implemented

The top processes collection **IS implemented** in the code:

1. **Agent Collection** (`agent/src/collectors/proc_collector.rs`):
   - Collects top 3 CPU processes every 60 seconds
   - Collects top 3 memory processes every 60 seconds  
   - Collects top 3 disk I/O processes every 60 seconds
   - Stores with tags: `process_name`, `pid`, `rank`

2. **Analysis Fetching** (`analysis/src/analyzers/hourly.py`):
   - `fetch_top_processes()` method queries ClickHouse
   - Uses `_get_top_processes_by_metric()` to aggregate by process
   - Returns top 3 for each category

3. **UI Display** (`ui/src/App.tsx`):
   - Displays top processes in the report section
   - Shows CPU, memory, and disk I/O top consumers

### ⚠️ Why You Might Not See Them

**Possible Reasons:**

1. **No Data Yet**: 
   - Agent needs to run for at least 1 minute to collect process data
   - Analysis needs to run AFTER data is collected
   - Check: `GET /api/debug/metrics` to see if process metrics exist

2. **Query Issue**:
   - The ClickHouse query uses `mapGet(tags, 'process_name')`
   - If tags aren't stored correctly, query will return empty
   - Check analysis logs for errors

3. **Empty Results**:
   - If no processes have CPU/memory/disk I/O, arrays will be empty
   - UI conditionally renders only if arrays have data

### 🔍 How to Debug

1. **Check if agent is collecting**:
   ```bash
   docker-compose logs agent | grep "process"
   ```

2. **Check ClickHouse directly**:
   ```sql
   SELECT 
       metric_name,
       mapGet(tags, 'process_name') as process_name,
       mapGet(tags, 'pid') as pid,
       count(*) as count
   FROM metrics
   WHERE metric_name LIKE 'process_%'
   GROUP BY metric_name, process_name, pid
   LIMIT 20;
   ```

3. **Check analysis logs**:
   ```bash
   docker-compose logs analysis | grep "top_processes"
   ```

4. **Check the API response**:
   ```bash
   curl http://localhost:6800/api/reports/latest | jq '.top_processes'
   ```

---

## AI Prompt Location

### 📍 Location

**File**: `analysis/src/ai/engine.py`

**Method**: `build_analysis_prompt()`

**Lines**: 80-121

### 📝 Current Prompt Structure

```python
def build_analysis_prompt(self, context: Dict[str, Any]) -> str:
    prompt = f"""You are a senior SRE with 10+ years experience analyzing Linux server performance.

SYSTEM CONTEXT:
- Hostname: {context.get('hostname', 'unknown')}
- Uptime: {context.get('uptime', 'unknown')} days
- Hardware: {context.get('cpu_count', 'N/A')} cores, {context.get('memory_gb', 'N/A')}GB RAM
- OS: {context.get('os_info', 'Linux')}

CURRENT HOUR METRICS (vs 7-day baseline):
- CPU: {context.get('cpu_avg', 0):.1f}% avg, {context.get('cpu_peak', 0):.1f}% peak
- Memory: {context.get('memory_percent', 0):.1f}% used
- Disk I/O: {context.get('disk_iops', 0)} IOPS, {context.get('disk_latency_ms', 0):.1f}ms latency
- Network: {context.get('packets_total', 0)} packets, {context.get('packet_drops', 0)} drops

TOP PROCESSES:
- Top CPU Consumers: {context.get('top_cpu_processes', 'None')}
- Top Memory Consumers: {context.get('top_memory_processes', 'None')}
- Top Disk I/O Consumers: {context.get('top_disk_io_processes', 'None')}

ANOMALIES DETECTED:
{self._format_anomalies(context.get('anomalies', []))}

CONFIGURATION ISSUES FOUND:
{self._format_config_issues(context.get('config_issues', []))}

PROVIDE:
1. Critical Alerts (if any urgent issues requiring immediate attention)
2. 3-5 Actionable Recommendations (specific, technical, implementable)
3. Capacity Forecast Assessment (weeks until resource exhaustion)
4. Configuration Optimizations (specific parameters with values and impact)

Format as JSON with these keys:
{{
  "critical_alerts": [...],
  "recommendations": [...],
  "capacity_forecast": {{...}},
  "config_optimizations": [...]
}}

Be concise, technical, and focus on actionable insights.
Use specific numbers and timeframes. Explain the "why" behind each recommendation.
"""
    return prompt
```

### ✅ Recent Updates

**Added Top Processes to Prompt** (just fixed):
- Top processes are now included in the AI context
- Format: "nginx (PID 1234, 15.2%), python (PID 5678, 12.1%)"
- AI can now reference specific processes in recommendations

### 🔄 How It's Called

1. **Hourly Analyzer** (`hourly.py`):
   ```python
   # Fetch top processes
   top_processes = await self.fetch_top_processes(start_time, end_time)
   
   # Build context (includes top processes)
   context = self.build_context(current_metrics, baseline, anomalies, config_issues, top_processes)
   
   # Generate AI insights
   ai_insights = await self.generate_ai_insights(context)
   ```

2. **AI Engine** (`engine.py`):
   ```python
   # Build prompt from context
   prompt = self.ai.build_analysis_prompt(context)
   
   # Send to Gemini API
   response = await self.ai.generate_insights(prompt)
   ```

---

## Verification Steps

### 1. Verify Agent is Collecting

```bash
# Check agent logs
docker-compose logs -f agent

# Should see every 60 seconds:
# "CPU usage: X.XX%"
# Process collection happens silently
```

### 2. Verify Data in ClickHouse

```bash
# Connect to ClickHouse
docker-compose exec clickhouse clickhouse-client

# Query process metrics
SELECT 
    metric_name,
    mapGet(tags, 'process_name') as process_name,
    mapGet(tags, 'pid') as pid,
    count(*) as count,
    avg(value) as avg_value
FROM metrics
WHERE metric_name LIKE 'process_%'
  AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY metric_name, process_name, pid
ORDER BY avg_value DESC
LIMIT 10;
```

### 3. Verify Analysis is Fetching

```bash
# Check analysis logs
docker-compose logs -f analysis

# Should see:
# "Fetched top processes: CPU=X, Memory=Y, DiskIO=Z"
```

### 4. Verify UI is Receiving

```bash
# Check API response
curl http://localhost:6800/api/reports/latest | jq '.top_processes'

# Should return:
# {
#   "cpu": [{"name": "...", "pid": "...", "average": X, "peak": Y}, ...],
#   "memory": [...],
#   "disk_io": [...]
# }
```

---

## Troubleshooting

### If Top Processes Are Empty

1. **Check agent is running**:
   ```bash
   docker-compose ps agent
   ```

2. **Check collection interval**:
   - Should be 60 seconds (1 minute)
   - Check `agent/src/config.rs` or config file

3. **Check permissions**:
   - Agent needs read access to `/proc/<pid>/io`
   - Some processes may not be readable

4. **Check ClickHouse connection**:
   ```bash
   docker-compose logs agent | grep "ClickHouse"
   ```

### If Query Fails

The query uses ClickHouse Map functions:
- `mapGet(tags, 'key')`: Get value from Map
- `has(tags, 'key')`: Check if key exists

If this fails, check:
1. ClickHouse version (needs Map support)
2. Tags are stored as Map type
3. Tag keys match exactly ('process_name', 'pid', 'rank')

---

## Summary

✅ **Top Processes**: Code is implemented and should work
✅ **AI Prompt**: Located in `analysis/src/ai/engine.py`, now includes top processes
⚠️ **Visibility**: May not show if:
   - No data collected yet (wait 1+ minutes)
   - Query returns empty (check ClickHouse)
   - Processes have zero usage

**Next Steps**:
1. Wait for agent to collect data (1+ minute)
2. Trigger new analysis
3. Check logs for "Fetched top processes"
4. Verify data in ClickHouse if still empty

