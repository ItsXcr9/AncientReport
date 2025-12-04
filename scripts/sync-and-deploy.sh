#!/bin/bash
set -e

SERVER="root@65.109.200.75"
REMOTE_PATH="/home/AncientReport"
CENTRAL_IP="65.109.200.75"

echo "🚀 Syncing AncientReport Agent to $SERVER..."

# Sync the changed files
echo "📦 Uploading files..."
rsync -avz --progress \
  agent/docker-entrypoint.sh \
  docker-compose.agent.yml \
  "$SERVER:$REMOTE_PATH/"

echo "🔧 Setting up configuration on server..."
ssh "$SERVER" << EOF
cd $REMOTE_PATH

# Create .env file with correct NATS configuration
cat > .env << 'ENVFILE'
# AncientReport Agent Configuration
TZ=Asia/Tehran

# Central Server Configuration
CLICKHOUSE_HOST=$CENTRAL_IP
CLICKHOUSE_PORT=6123
CLICKHOUSE_DB=AncientReport
CLICKHOUSE_USER=AncientReport
CLICKHOUSE_PASSWORD=AncientReport

# Agent Configuration
AGENT_HOSTNAME=auto-detect

# V2 Mode: NATS Streaming
NATS_URL=nats://$CENTRAL_IP:4222
NATS_ENABLED=true
ENVFILE

echo "✅ Configuration file created"
cat .env

echo ""
echo "🔄 Rebuilding agent container..."
docker compose -f docker-compose.agent.yml down
docker compose -f docker-compose.agent.yml up -d --build

echo ""
echo "📋 Waiting for container to start..."
sleep 3

echo ""
echo "📊 Container logs (Ctrl+C to exit):"
docker compose -f docker-compose.agent.yml logs -f agent
EOF

echo "✅ Deployment complete!"

