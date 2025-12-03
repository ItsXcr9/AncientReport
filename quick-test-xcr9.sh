#!/bin/bash

# Quick test with correct port
XCR9_HOST="root@65.109.200.75"  
API_BASE="http://localhost:6800"  # External port mapping is 6800

echo "🔍 Testing xcr9 Charts with correct port (6800)"
echo "================================================"

# Test API
echo ""
echo "1. Testing API root..."
ssh $XCR9_HOST "curl -s ${API_BASE}/api/ | head -20"

echo ""
echo "2. Testing servers endpoint..."
ssh $XCR9_HOST "curl -s ${API_BASE}/api/servers | head -20"

echo ""
echo "3. Testing CPU metrics (last 1 hour)..."
END=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START=$(date -u -d '1 hour ago' +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -v-1H +"%Y-%m-%dT%H:%M:%SZ")
ssh $XCR9_HOST "curl -s '${API_BASE}/api/metrics/cpu?start=${START}&end=${END}' | python3 -m json.tool 2>/dev/null | head -30 || curl -s '${API_BASE}/api/metrics/cpu?start=${START}&end=${END}' | head -30"

echo ""
echo "4. Checking analysis logs for errors..."
ssh $XCR9_HOST "cd /home/AncientReport && docker compose logs --tail=50 analysis | grep -i ERROR || echo 'No errors found'"

echo ""
echo "================================================"
echo "✅ Test complete"
