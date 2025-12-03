#!/bin/bash

# Verification script for xcr9 deployment
XCR9_HOST="root@65.109.200.75"
XCR9_PATH="/home/AncientReport"
API_BASE="http://localhost:8000"

echo "🔍 Verifying xcr9 Chart Functionality"
echo "======================================"
echo ""

# Give analysis service time to fully start
echo "⏳ Waiting for analysis service to fully initialize (15 seconds)..."
sleep 15

echo ""
echo "📊 Testing API Endpoints:"
echo "-------------------------"

# Test 1: API Root
echo -n "1. API Root (/api/)... "
RESULT=$(ssh $XCR9_HOST "curl -s ${API_BASE}/api/ 2>/dev/null | grep -q status && echo 'OK' || echo 'FAILED'")
echo "$RESULT"

# Test 2: Servers List
echo -n "2. Servers List (/api/servers)... "
SERVERS=$(ssh $XCR9_HOST "curl -s ${API_BASE}/api/servers 2>/dev/null")
if echo "$SERVERS" | grep -q "servers"; then
    echo "OK"
    echo "   └─ Found servers: $(echo $SERVERS | grep -o '"xcr9"' || echo 'checking...')"
else
    echo "FAILED"
fi

# Test 3: CPU Metrics
echo -n "3. CPU Metrics (/api/metrics/cpu)... "
CPU_DATA=$(ssh $XCR9_HOST "curl -s '${API_BASE}/api/metrics/cpu?start=2025-12-01T00:00:00Z&end=2025-12-04T23:59:59Z' 2>/dev/null")
if echo "$CPU_DATA" | grep -q "data"; then
    COUNT=$(echo "$CPU_DATA" | grep -o '"timestamp"' | wc -l | tr -d ' ')
    echo "OK ($COUNT data points)"
else
    echo "FAILED"
fi

# Test 4: Memory Metrics
echo -n "4. Memory Metrics (/api/metrics/memory)... "
MEM_DATA=$(ssh $XCR9_HOST "curl -s '${API_BASE}/api/metrics/memory?start=2025-12-01T00:00:00Z&end=2025-12-04T23:59:59Z' 2>/dev/null")
if echo "$MEM_DATA" | grep -q "data"; then
    COUNT=$(echo "$MEM_DATA" | grep -o '"timestamp"' | wc -l | tr -d ' ')
    echo "OK ($COUNT data points)"
else
    echo "FAILED"
fi

# Test 5: Disk Metrics  
echo -n "5. Disk Metrics (/api/metrics/disk)... "
DISK_DATA=$(ssh $XCR9_HOST "curl -s '${API_BASE}/api/metrics/disk?start=2025-12-01T00:00:00Z&end=2025-12-04T23:59:59Z' 2>/dev/null")
if echo "$DISK_DATA" | grep -q "data"; then
    COUNT=$(echo "$DISK_DATA" | grep -o '"timestamp"' | wc -l | tr -d ' ')
    echo "OK ($COUNT data points)"
else
    echo "FAILED"
fi

# Test 6: Network Metrics
echo -n "6. Network Metrics (/api/metrics/network)... "
NET_DATA=$(ssh $XCR9_HOST "curl -s '${API_BASE}/api/metrics/network?start=2025-12-01T00:00:00Z&end=2025-12-04T23:59:59Z' 2>/dev/null")
if echo "$NET_DATA" | grep -q "data"; then
    COUNT=$(echo "$NET_DATA" | grep -o '"timestamp"' | wc -l | tr -d ' ')
    echo "OK ($COUNT data points)"
else
    echo "FAILED"
fi

echo ""
echo "🔧 Service Status:"
echo "-------------------------"
ssh $XCR9_HOST "cd $XCR9_PATH && docker compose ps --format 'table {{.Name}}\t{{.Status}}'"

echo ""
echo "📋 Recent Service Logs:"
echo "-------------------------"
echo "Analysis Service:"
ssh $XCR9_HOST "cd $XCR9_PATH && docker compose logs --tail=5 analysis 2>&1 | tail -5"

echo ""
echo "======================================"
echo "✅ Verification Complete!"
echo ""
echo "🌐 Access UI at: http://65.109.200.75:6080"
echo ""
