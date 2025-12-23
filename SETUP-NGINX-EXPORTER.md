# NGINX Prometheus Exporter Setup for AncientReport

This guide will help you set up NGINX monitoring with AncientReport's auto-discovery feature.

## 📋 Prerequisites

- NGINX server running on xcr9 (65.109.200.75)
- AncientReport agent with `PROMETHEUS_ENABLED=true` ✅ (already enabled)
- Docker installed on the server

## 🚀 Quick Setup

### Step 1: Enable NGINX Stub Status

Your NGINX needs to expose a `/nginx_status` endpoint. There are two scenarios:

#### Scenario A: NGINX Running on Host (Port 80)

1. SSH to your server:
   ```bash
   ssh root@65.109.200.75
   ```

2. Edit your NGINX configuration (usually `/etc/nginx/sites-available/default` or `/etc/nginx/nginx.conf`):
   ```bash
   nano /etc/nginx/sites-available/default
   ```

3. Add this location block inside your existing `server {}` section:
   ```nginx
   location /nginx_status {
       stub_status on;
       access_log off;
       allow 127.0.0.1;
       allow 172.16.0.0/12;  # Docker networks
       deny all;
   }
   ```

4. Test and reload NGINX:
   ```bash
   nginx -t
   systemctl reload nginx
   ```

5. Verify it's working:
   ```bash
   curl http://localhost/nginx_status
   ```
   
   You should see output like:
   ```
   Active connections: 2
   server accepts handled requests
    10 10 15
   Reading: 0 Writing: 1 Waiting: 1
   ```

#### Scenario B: NGINX Running in Docker

1. Add a volume mount to your NGINX container to include the stub_status config:
   ```yaml
   volumes:
     - ./nginx-stub-status.conf:/etc/nginx/conf.d/stub_status.conf:ro
   ```

2. Restart your NGINX container:
   ```bash
   docker-compose restart nginx
   ```

### Step 2: Deploy NGINX Prometheus Exporter

1. Copy the Docker Compose file to your server:
   ```bash
   # From your local machine
   scp docker-compose.nginx-exporter.yml root@65.109.200.75:/home/AncientReport/
   ```

2. SSH to the server and start the exporter:
   ```bash
   ssh root@65.109.200.75
   cd /home/AncientReport
   docker-compose -f docker-compose.nginx-exporter.yml up -d
   ```

3. Verify the exporter is running:
   ```bash
   docker ps | grep nginx-exporter
   curl http://localhost:9113/metrics
   ```

### Step 3: Verify Auto-Discovery

The AncientReport agent will automatically discover the exporter within 5 minutes (or immediately on the next scrape cycle).

Check the agent logs:
```bash
docker logs AncientReport-agent | grep -i prometheus
```

You should see:
```
✓ Discovery complete: X exporters found
📊 nginx_exporter (port_scan) - http://127.0.0.1:9113/metrics
```

### Step 4: View Metrics in AncientReport UI

1. Open AncientReport UI
2. Navigate to **Prometheus Discovery** page
3. You should see:
   - **NGINX Exporter** in the discovered exporters list
   - Metrics like:
     - `nginx_connections_active`
     - `nginx_connections_accepted`
     - `nginx_connections_handled`
     - `nginx_http_requests_total`

## 🔧 Troubleshooting

### Exporter can't connect to NGINX

**Error**: `error scraping nginx: Get "http://host.docker.internal:80/nginx_status": dial tcp: lookup host.docker.internal`

**Solution**: Update the scrape URI in `docker-compose.nginx-exporter.yml`:

```yaml
command:
  # If NGINX is on host
  - '-nginx.scrape-uri=http://172.17.0.1:80/nginx_status'
  
  # Or if NGINX is in Docker on same network
  - '-nginx.scrape-uri=http://nginx:80/nginx_status'
```

Then restart:
```bash
docker-compose -f docker-compose.nginx-exporter.yml restart
```

### NGINX returns 404 for /nginx_status

Make sure you've added the `stub_status` configuration and reloaded NGINX.

Test from the server:
```bash
curl http://localhost/nginx_status
```

### Exporter not auto-discovered

Force a discovery run by restarting the agent:
```bash
docker restart AncientReport-agent
```

Check logs:
```bash
docker logs -f AncientReport-agent
```

## 📊 Available NGINX Metrics

Once discovered, you'll see these metrics:

| Metric | Description |
|--------|-------------|
| `nginx_connections_active` | Current active client connections |
| `nginx_connections_accepted` | Total accepted client connections |
| `nginx_connections_handled` | Total handled connections |
| `nginx_connections_reading` | Connections reading request |
| `nginx_connections_writing` | Connections writing response |
| `nginx_connections_waiting` | Idle keep-alive connections |
| `nginx_http_requests_total` | Total HTTP requests |

## 🎯 Advanced Configuration

### Custom Scrape Interval

To change the scrape interval for all Prometheus targets:

```bash
# In docker-compose.agent.yml
environment:
  PROMETHEUS_SCRAPE_INTERVAL: "15"  # Scrape every 15 seconds instead of 30
```

### Multiple NGINX Instances

If you have multiple NGINX servers, deploy separate exporters on different ports:

```yaml
# docker-compose.nginx-exporter2.yml
services:
  nginx-exporter-2:
    ports:
      - "9114:9113"  # Different port
    command:
      - '-nginx.scrape-uri=http://other-nginx:80/nginx_status'
```

## ✅ Success Checklist

- [ ] NGINX `/nginx_status` endpoint is accessible
- [ ] NGINX Prometheus Exporter container is running
- [ ] Exporter metrics are accessible (`curl http://localhost:9113/metrics`)
- [ ] AncientReport agent discovers the exporter (check logs)
- [ ] Metrics appear in AncientReport UI → Prometheus Discovery page
- [ ] Charts display NGINX connection metrics

## 📚 Additional Resources

- [NGINX Prometheus Exporter GitHub](https://github.com/nginxinc/nginx-prometheus-exporter)
- [NGINX stub_status Module](http://nginx.org/en/docs/http/ngx_http_stub_status_module.html)
- AncientReport Prometheus Scraper: `agent/src/collectors/prometheus_scraper.rs`
