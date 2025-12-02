#!/bin/bash
set -e

echo "🚀 Deploying AncientReport Agent..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️ .env not found, creating from .env.agent.example..."
    cp .env.agent.example .env
    
    # Prompt for Central Server IP
    read -p "Enter Central Server IP: " CENTRAL_IP
    if [ -n "$CENTRAL_IP" ]; then
        # Cross-platform sed
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/CLICKHOUSE_HOST=localhost/CLICKHOUSE_HOST=$CENTRAL_IP/" .env
        else
            sed -i "s/CLICKHOUSE_HOST=localhost/CLICKHOUSE_HOST=$CENTRAL_IP/" .env
        fi
    fi
    
    # Prompt for Hostname
    CURRENT_HOST=$(hostname)
    read -p "Enter Agent Hostname [default: $CURRENT_HOST]: " AGENT_HOST
    AGENT_HOST=${AGENT_HOST:-$CURRENT_HOST}
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/AGENT_HOSTNAME=auto-detect/AGENT_HOSTNAME=$AGENT_HOST/" .env
    else
        sed -i "s/AGENT_HOSTNAME=auto-detect/AGENT_HOSTNAME=$AGENT_HOST/" .env
    fi
fi

echo "📦 Building and starting agent..."
docker-compose -f docker-compose.agent.yml up -d --build --remove-orphans

echo "✅ Agent Deployed Successfully!"
echo "📝 Check logs with: docker-compose -f docker-compose.agent.yml logs -f agent"
