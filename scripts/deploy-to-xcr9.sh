#!/bin/bash
set -e

# Deployment script for xcr9 server
# This syncs the latest local code and rebuilds the services

XCR9_HOST="root@65.109.200.75"
XCR9_PATH="/home/AncientReport"

echo "🚀 Deploying AncientReport to xcr9..."
echo "========================================"

# Step 1: Backup current deployment
echo ""
echo "📦 Step 1: Creating backup of current deployment..."
ssh $XCR9_HOST "cd $XCR9_PATH && \
  mkdir -p backups && \
  BACKUP_NAME=backup-\$(date +%Y%m%d-%H%M%S) && \
  echo Creating backup: \$BACKUP_NAME && \
  cp -r ui/src backups/\$BACKUP_NAME-ui-src || true && \
  cp -r analysis/src backups/\$BACKUP_NAME-analysis-src || true && \
  echo ✓ Backup created: \$BACKUP_NAME"

# Step 2: Sync critical files
echo ""
echo "📤 Step 2: Syncing updated files to xcr9..."

# Sync analysis service files
echo "  → Syncing analysis service..."
rsync -avz --progress \
  ./analysis/src/ \
  $XCR9_HOST:$XCR9_PATH/analysis/src/

# Sync UI files
echo "  → Syncing UI components..."
rsync -avz --progress \
  ./ui/src/ \
  $XCR9_HOST:$XCR9_PATH/ui/src/

# Sync Agent files
echo "  → Syncing Agent components..."
rsync -avz --progress --exclude 'target' \
  ./agent/ \
  $XCR9_HOST:$XCR9_PATH/agent/

# Sync docker-compose if needed
echo "  → Syncing docker-compose files..."
rsync -avz --progress \
  ./remote_docker_compose.yml \
  $XCR9_HOST:$XCR9_PATH/docker-compose.yml

echo "✓ Files synced successfully"

# Step 3: Rebuild and restart services
echo ""
echo "🔨 Step 3: Rebuilding services on xcr9..."
ssh $XCR9_HOST "cd $XCR9_PATH && \
  echo '  → Rebuilding and starting services...' && \
  docker compose up -d --build && \
  echo '✓ Services restarted and rebuilt'"

# Step 4: Wait for services to be ready
echo ""
echo "⏳ Step 4: Waiting for services to start..."
sleep 5

# Step 5: Verification
echo ""
echo "🔍 Step 5: Verifying deployment..."

# Check if services are running
echo "  → Checking service status..."
ssh $XCR9_HOST "cd $XCR9_PATH && docker compose ps"

# Test API endpoints
echo ""
echo "  → Testing API endpoints..."
ssh $XCR9_HOST "cd $XCR9_PATH && \
  echo '    - API root...' && \
  curl -s http://localhost:8000/api/ | grep -q status && echo '      ✓ API root OK' || echo '      ✗ API root FAILED' && \
  echo '    - Server list...' && \
  curl -s http://localhost:8000/api/servers | grep -q servers && echo '      ✓ Servers endpoint OK' || echo '      ✗ Servers endpoint FAILED' && \
  echo '    - CPU metrics...' && \
  curl -s 'http://localhost:8000/api/metrics/cpu?start=2025-12-03T00:00:00Z&end=2025-12-03T23:59:59Z' | grep -q data && echo '      ✓ CPU metrics OK' || echo '      ✗ CPU metrics FAILED'"

# Check for errors in logs
echo ""
echo "  → Checking for errors in logs..."
ssh $XCR9_HOST "cd $XCR9_PATH && \
  echo '    Recent analysis errors:' && \
  docker compose logs --tail=20 analysis 2>&1 | grep -i error || echo '      No errors found' && \
  echo '    Recent UI errors:' && \
  docker compose logs --tail=20 ui 2>&1 | grep -i error || echo '      No errors found'"

echo ""
echo "========================================"
echo "✅ Deployment complete!"
echo ""
echo "📊 Next steps:"
echo "  1. Open browser to http://65.109.200.75 (or appropriate port)"
echo "  2. Verify all 4 charts are rendering (CPU, Memory, Disk, Network)"
echo "  3. Test server selector dropdown if multi-server setup"
echo "  4. Check browser console for any JavaScript errors"
echo ""
echo "To view live logs:"
echo "  ssh $XCR9_HOST 'cd $XCR9_PATH && docker compose logs -f analysis'"
echo ""
