# Remote Logging Setup

All services have been configured to send logs to the remote UDP syslog server at `65.109.200.75:5515`.

## Configuration

The Docker `syslog` logging driver has been configured in `docker-compose.yml`, `docker-compose.central.yml`, and `docker-compose.agent.yml` for all services.

```yaml
logging:
  driver: syslog
  options:
    syslog-address: "udp://65.109.200.75:5515"
    tag: "{{.Name}}"
```

## How to Apply Changes

To apply these changes, you need to recreate the containers:

```bash
# For the main development environment
docker-compose up -d --force-recreate

# For the central server deployment
docker-compose -f docker-compose.central.yml up -d --force-recreate

# For the agent deployment
docker-compose -f docker-compose.agent.yml up -d --force-recreate
```

## Verification

To verify that logs are being sent, you can check the Docker container inspection:

```bash
docker inspect --format='{{.HostConfig.LogConfig.Type}}' AncientReport-analysis
# Should output: syslog
```

Note: When using the `syslog` driver, `docker logs` command will no longer show logs locally. To see logs locally AND send them remotely, you would need a more complex setup (e.g., using `fluentd` or `logspout`), or rely on the remote server for viewing logs.
