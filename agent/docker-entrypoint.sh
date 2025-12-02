#!/bin/bash
set -e

# Create config directory if it doesn't exist
mkdir -p /etc/AncientReport

# Determine config file source
# Determine config file source
CONFIG_SOURCE=""
if [ -f /etc/AncientReport/config-source/config.toml ]; then
    # Use mounted config file if it exists
    CONFIG_SOURCE="/etc/AncientReport/config-source/config.toml"
elif [ -f /etc/AncientReport/config-source/config.example.toml ]; then
    # Fall back to example config
    CONFIG_SOURCE="/etc/AncientReport/config-source/config.example.toml"
elif [ -f /etc/AncientReport/config.example.toml ]; then
    # Use example from image
    CONFIG_SOURCE="/etc/AncientReport/config.example.toml"
elif [ -f /etc/agent/config.toml ]; then
    # Use default from image
    CONFIG_SOURCE="/etc/agent/config.toml"
fi

# Copy config to final location
if [ -n "$CONFIG_SOURCE" ] && [ -f "$CONFIG_SOURCE" ]; then
    cp "$CONFIG_SOURCE" /etc/AncientReport/config.toml
    echo "Using config from: $CONFIG_SOURCE"
    
    # Apply environment variable overrides if they exist
    if [ -n "$CLICKHOUSE_HOST" ]; then
        echo "Configuring ClickHouse host: $CLICKHOUSE_HOST"
        # Construct URL from host and port
        CH_PORT="${CLICKHOUSE_PORT:-6123}"
        CH_URL="http://${CLICKHOUSE_HOST}:${CH_PORT}"
        sed -i "s|url = \".*\"|url = \"$CH_URL\"|g" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$CLICKHOUSE_DB" ]; then
        sed -i "s|database = \".*\"|database = \"$CLICKHOUSE_DB\"|g" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$CLICKHOUSE_USER" ]; then
        sed -i "s|username = \".*\"|username = \"$CLICKHOUSE_USER\"|g" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$CLICKHOUSE_PASSWORD" ]; then
        sed -i "s|password = \".*\"|password = \"$CLICKHOUSE_PASSWORD\"|g" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$AGENT_HOSTNAME" ]; then
        echo "Configuring Hostname: $AGENT_HOSTNAME"
        sed -i "s|hostname = \".*\"|hostname = \"$AGENT_HOSTNAME\"|g" /etc/AncientReport/config.toml
    fi
else
    echo "Error: Could not find any config file"
    exit 1
fi

# Verify Docker is accessible
echo "Checking Docker availability..."
if which docker > /dev/null 2>&1; then
    echo "Docker binary found at: $(which docker)"
    if docker ps > /dev/null 2>&1; then
        echo "Docker daemon is accessible"
        echo "Running containers: $(docker ps --format '{{.Names}}' | wc -l)"
    else
        echo "WARNING: Docker binary found but daemon is not accessible"
        echo "This usually means the Docker socket is not mounted or permissions are incorrect"
    fi
else
    echo "ERROR: Docker binary not found in PATH"
    echo "Current PATH: $PATH"
fi

# Execute the main command
exec "$@"


