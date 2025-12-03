#!/bin/bash
# Verification script for V2 data flow
# Run this on the server after deploying the fix

set -e

echo "=================================================="
echo "V2 Data Flow Verification Script"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a container is running
check_container() {
    local container=$1
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "${GREEN}✓${NC} $container is running"
        return 0
    else
        echo -e "${RED}✗${NC} $container is NOT running"
        return 1
    fi
}

# Function to check logs for pattern
check_logs() {
    local container=$1
    local pattern=$2
    local description=$3
    
    if docker logs "$container" --tail 100 2>&1 | grep -q "$pattern"; then
        echo -e "${GREEN}✓${NC} $description"
        return 0
    else
        echo -e "${RED}✗${NC} $description (not found)"
        return 1
    fi
}

echo "Step 1: Checking Containers"
echo "----------------------------"
check_container "AncientReport-agent"
check_container "AncientReport-nats"
check_container "AncientReport-analysis"
check_container "AncientReport-clickhouse"
check_container "AncientReport-ui"
echo ""

echo "Step 2: Checking Agent → NATS"
echo "------------------------------"
check_logs "AncientReport-agent" "Published.*metrics to NATS" "Agent publishing to NATS"
echo ""

echo "Step 3: Checking NATS → Ingestion Gateway"
echo "------------------------------------------"
check_logs "AncientReport-analysis" "Fetched.*messages from NATS" "Gateway receiving from NATS"
check_logs "AncientReport-analysis" "Acked message" "Messages being acknowledged"
echo ""

echo "Step 4: Checking ClickHouse Data"
echo "---------------------------------"
METRIC_COUNT=$(docker exec AncientReport-clickhouse clickhouse-client -q "SELECT count(*) FROM metrics WHERE timestamp >= now() - INTERVAL 5 MINUTE" 2>/dev/null || echo "0")

if [ "$METRIC_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓${NC} ClickHouse has $METRIC_COUNT metrics in last 5 minutes"
    
    # Show metric breakdown
    echo ""
    echo "Recent metrics breakdown:"
    docker exec AncientReport-clickhouse clickhouse-client -q "
        SELECT 
            metric_name, 
            count(*) as count,
            formatDateTime(max(timestamp), '%Y-%m-%d %H:%M:%S') as latest
        FROM metrics
        WHERE timestamp >= now() - INTERVAL 5 MINUTE
        GROUP BY metric_name
        ORDER BY count DESC
        LIMIT 10
    " 2>/dev/null || echo "Could not query metrics"
else
    echo -e "${RED}✗${NC} No recent metrics in ClickHouse"
fi
echo ""

echo "Step 5: Checking WebSocket"
echo "--------------------------"
check_logs "AncientReport-analysis" "WebSocket connected" "WebSocket clients connected"
check_logs "AncientReport-analysis" "WebSocket broadcasting enabled" "WebSocket broadcasting active"
echo ""

echo "Step 6: Checking UI Service"
echo "---------------------------"
if curl -s http://localhost:6080 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} UI is accessible on port 6080"
else
    echo -e "${RED}✗${NC} UI is not accessible"
fi

if curl -s http://localhost:6800/api/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Analysis API is accessible on port 6800"
else
    echo -e "${RED}✗${NC} Analysis API is not accessible"
fi
echo ""

echo "Step 7: Testing API Endpoints"
echo "------------------------------"
# Test CPU metrics endpoint
CPU_DATA=$(curl -s "http://localhost:6800/api/metrics/cpu" | jq -r '.data | length' 2>/dev/null || echo "0")
if [ "$CPU_DATA" -gt 0 ]; then
    echo -e "${GREEN}✓${NC} CPU metrics API returning $CPU_DATA data points"
else
    echo -e "${YELLOW}⚠${NC} CPU metrics API returning no data (may need time to accumulate)"
fi

# Test memory metrics endpoint
MEM_DATA=$(curl -s "http://localhost:6800/api/metrics/memory" | jq -r '.data | length' 2>/dev/null || echo "0")
if [ "$MEM_DATA" -gt 0 ]; then
    echo -e "${GREEN}✓${NC} Memory metrics API returning $MEM_DATA data points"
else
    echo -e "${YELLOW}⚠${NC} Memory metrics API returning no data (may need time to accumulate)"
fi
echo ""

echo "=================================================="
echo "Verification Complete"
echo "=================================================="
echo ""
echo "Next Steps:"
echo "1. Open browser: http://$(hostname -I | awk '{print $1}'):6080"
echo "2. Look for 'V2 Live' indicator (green, pulsing)"
echo "3. Charts should show data and 'LIVE' badges"
echo ""
echo "Troubleshooting:"
echo "- If issues persist, check logs: docker compose logs -f analysis"
echo "- Restart services: docker compose restart analysis"
echo "- Full rebuild: docker compose up -d --build analysis"
echo ""

