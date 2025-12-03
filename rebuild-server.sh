#!/bin/bash
set -e

echo "============================================"
echo "Rebuilding AncientReport after Docker fixes"
echo "============================================"

cd /home/AncientReport

# Step 1: Apply database migration
echo ""
echo "Step 1: Applying ClickHouse migration..."
cat deploy/clickhouse/migrations/002_add_healthcheck_columns.sql | docker exec -i AncientReport-clickhouse clickhouse-client --database AncientReport
echo "✓ Migration applied"

# Step 2: Rebuild and restart agent
echo ""
echo "Step 2: Rebuilding agent..."
cd agent
cargo build --release
echo "✓ Agent built"

echo "Restarting agent service..."
systemctl restart systempulse.service
echo "✓ Agent service restarted"
cd ..

# Step 3: Restart analysis service
echo ""
echo "Step 3: Restarting analysis service..."
docker-compose -f docker-compose.central.yml restart analysis
echo "✓ Analysis service restarted"

# Step 4: Rebuild and restart UI
echo ""
echo "Step 4: Rebuilding UI..."
cd ui
npm run build
echo "✓ UI built"
cd ..

echo "Restarting UI service..."
docker-compose -f docker-compose.central.yml restart ui
echo "✓ UI service restarted"

echo ""
echo "============================================"
echo "✅ All services rebuilt and restarted!"
echo "============================================"
echo ""
echo "The Docker containers and healthchecks should now work correctly."
echo "Check the UI at your server's address to verify."

