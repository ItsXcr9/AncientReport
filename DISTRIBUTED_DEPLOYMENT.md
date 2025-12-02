# Distributed Deployment Guide for AncientReport

AncientReport supports a distributed architecture where a central server collects and analyzes data from multiple remote agents. This guide explains how to set up this deployment.

## Architecture

*   **Central Server**: Hosts the ClickHouse database, AI Analysis Engine, and Web UI. It acts as the aggregation point.
*   **Agents**: Lightweight collectors running on each target server. They collect system metrics (via eBPF and /proc) and send them to the Central Server's ClickHouse instance.

## Prerequisites

*   **Docker** and **Docker Compose** installed on all machines.
*   **Network Connectivity**: Agents must be able to reach the Central Server on port `8123` (ClickHouse HTTP) and `9000` (ClickHouse Native).

---

## 1. Central Server Setup

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/AncientReport.git
    cd AncientReport
    ```

2.  **Configure Environment**:
    Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` if you need to change default passwords or AI provider settings.

3.  **Start the Central Services**:
    Use the `docker-compose.central.yml` file:
    ```bash
    docker-compose -f docker-compose.central.yml up -d
    ```

4.  **Verify**:
    *   **UI**: Access `http://<central-server-ip>:3000`
    *   **ClickHouse**: Port `8123` should be accessible.

---

## 2. Agent Setup (Remote Servers)

For each server you want to monitor:

1.  **Prepare Files**:
    You only need `docker-compose.agent.yml` and `.env.agent.example` on the remote server. You can copy them from the repo or create them manually.

2.  **Configure Agent**:
    Create a `.env` file for the agent:
    ```bash
    cp .env.agent.example .env
    ```
    
    **Crucial Step**: Edit `.env` and set the following:
    *   `CLICKHOUSE_HOST`: The IP address or domain of your **Central Server**.
    *   `AGENT_HOSTNAME`: A unique name for this server (e.g., `prod-db-01`).
    *   `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD`: Must match the Central Server credentials.

    Example `.env`:
    ```ini
    CLICKHOUSE_HOST=192.168.1.100
    CLICKHOUSE_PORT=8123
    CLICKHOUSE_DB=AncientReport
    CLICKHOUSE_USER=default
    CLICKHOUSE_PASSWORD=
    
    AGENT_HOSTNAME=web-server-01
    TZ=Asia/Tehran
    ```

3.  **Start the Agent**:
    ```bash
    docker-compose -f docker-compose.agent.yml up -d
    ```

4.  **Verify**:
    Check agent logs to ensure it's connected:
    ```bash
    docker-compose -f docker-compose.agent.yml logs -f agent
    ```
    You should see "Connected to ClickHouse" messages.

---

## 3. Viewing Data

1.  Open the **AncientReport UI** on the Central Server (`http://<central-server-ip>:3000`).
2.  Use the **Server Selector** in the top navigation bar to switch between different servers.
3.  The dashboard will update to show metrics and AI reports specific to the selected server.
