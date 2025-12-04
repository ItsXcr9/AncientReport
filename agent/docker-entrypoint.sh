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
    
    # Function to update TOML value in a specific section
    update_toml_value() {
        local section=$1
        local key=$2
        local value=$3
        local file=$4
        
        # Use awk to update value only in the specified section
        awk -v section="[$section]" -v key="$key" -v value="$value" '
        BEGIN { in_section=0 }
        /^\[.*\]/ {
            if ($0 == section) {
                in_section=1
            } else {
                in_section=0
            }
            print
            next
        }
        in_section && $0 ~ "^" key " *=" {
            print key " = \"" value "\""
            next
        }
        { print }
        ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
    }
    
    # Apply environment variable overrides if they exist
    
    # ClickHouse configuration
    if [ -n "$CLICKHOUSE_HOST" ]; then
        echo "Configuring ClickHouse host: $CLICKHOUSE_HOST"
        # Construct URL from host and port
        CH_PORT="${CLICKHOUSE_PORT:-6123}"
        CH_URL="http://${CLICKHOUSE_HOST}:${CH_PORT}"
        update_toml_value "clickhouse" "url" "$CH_URL" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$CLICKHOUSE_DB" ]; then
        update_toml_value "clickhouse" "database" "$CLICKHOUSE_DB" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$CLICKHOUSE_USER" ]; then
        update_toml_value "clickhouse" "username" "$CLICKHOUSE_USER" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$CLICKHOUSE_PASSWORD" ]; then
        update_toml_value "clickhouse" "password" "$CLICKHOUSE_PASSWORD" /etc/AncientReport/config.toml
    fi
    
    # Agent configuration
    if [ -n "$AGENT_HOSTNAME" ]; then
        echo "Configuring Hostname: $AGENT_HOSTNAME"
        update_toml_value "agent" "hostname" "$AGENT_HOSTNAME" /etc/AncientReport/config.toml
    fi
    
    # NATS configuration
    if [ -n "$NATS_URL" ]; then
        echo "Configuring NATS URL: $NATS_URL"
        update_toml_value "nats" "url" "$NATS_URL" /etc/AncientReport/config.toml
    fi
    
    if [ -n "$NATS_ENABLED" ]; then
        echo "Configuring NATS enabled: $NATS_ENABLED"
        # Update boolean value (no quotes)
        awk -v enabled="$NATS_ENABLED" '
        BEGIN { in_section=0 }
        /^\[nats\]/ {
            in_section=1
            print
            next
        }
        /^\[.*\]/ {
            in_section=0
            print
            next
        }
        in_section && /^enabled *=/ {
            print "enabled = " enabled
            next
        }
        { print }
        ' /etc/AncientReport/config.toml > /etc/AncientReport/config.toml.tmp && \
        mv /etc/AncientReport/config.toml.tmp /etc/AncientReport/config.toml
    fi
    
    # Display final configuration for debugging
    echo "=== Final Configuration ==="
    echo "ClickHouse URL: $(grep -A5 '^\[clickhouse\]' /etc/AncientReport/config.toml | grep '^url' || echo 'not set')"
    echo "NATS URL: $(grep -A5 '^\[nats\]' /etc/AncientReport/config.toml | grep '^url' || echo 'not set')"
    echo "NATS Enabled: $(grep -A5 '^\[nats\]' /etc/AncientReport/config.toml | grep '^enabled' || echo 'not set')"
    echo "=========================="
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


