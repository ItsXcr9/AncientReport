#!/bin/bash
set -e

echo "🚀 Deploying AncientReport Central Server..."

# Ensure .env exists
if [ ! -f .env ]; then
    echo "⚠️ .env not found, copying from .env.example..."
    cp .env.example .env
fi

# Pull and build
docker-compose -f docker-compose.central.yml pull
docker-compose -f docker-compose.central.yml up -d --build --remove-orphans

echo "✅ Central Server Deployed Successfully!"
echo "📊 UI available at http://localhost:3000"
echo "🗄️ ClickHouse available at http://localhost:8123"
