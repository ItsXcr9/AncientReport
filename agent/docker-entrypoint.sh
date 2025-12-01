#!/bin/bash
set -e

# Create config directory if it doesn't exist
mkdir -p /etc/AncientReport

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


