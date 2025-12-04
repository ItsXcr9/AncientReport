# Setting Up a New AncientReport Agent

This guide explains how to deploy a new AncientReport agent on a remote server to start monitoring it.

## Prerequisites

*   **Docker** and **Docker Compose** must be installed on the target server.
*   The server must have network access to the **Central Server** (specifically port `9000` for ClickHouse).

## Quick Start (Recommended)

1.  **Copy Files**:
    Transfer the following files from your central repository to the new server (e.g., via `scp`):
    *   `deploy-agent.sh`
    *   `docker-compose.agent.yml`
    *   `.env.agent.example`

2.  **Run Deployment Script**:
    Make the script executable and run it. You will need to provide the IP address of your Central Server.

    ```bash
    chmod +x deploy-agent.sh
    ./deploy-agent.sh <CENTRAL_SERVER_IP> <OPTIONAL_HOSTNAME>
    ```

    *   Replace `<CENTRAL_SERVER_IP>` with the IP of your central AncientReport server.
    *   Replace `<OPTIONAL_HOSTNAME>` with a unique name for this server (e.g., `db-prod-01`). If omitted, it defaults to the machine's hostname.

    **Example:**
    ```bash
    ./deploy-agent.sh 192.168.1.50 web-server-02
    ```

3.  **Verify**:
    Check the logs to ensure the agent connected successfully:
    ```bash
    docker-compose -f docker-compose.agent.yml logs -f agent
    ```

---

## Manual Setup

If you prefer to configure it manually:

1.  **Copy Files**:
    Copy `docker-compose.agent.yml` and `.env.agent.example` to the server.

2.  **Configure Environment**:
    ```bash
    cp .env.agent.example .env
    ```
    Edit `.env` and set:
    *   `CLICKHOUSE_HOST`: Your Central Server IP.
    *   `AGENT_HOSTNAME`: Unique name for this agent.
    *   `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD`: Credentials for the central DB.

3.  **Start Agent**:
    ```bash
    docker-compose -f docker-compose.agent.yml up -d
    ```
