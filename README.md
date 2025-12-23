# AncientReport

> 🔮 **Autonomous Observability Platform powered by eBPF**

AncientReport provides deep system-level observability through eBPF technology, offering real-time insights into your infrastructure with AI-powered analysis.

## Features

- **🔬 eBPF-Powered Metrics** — Kernel-level visibility without agents
- **🤖 AI-Driven Insights** — Automatic anomaly detection and root cause analysis
- **📊 Real-time Dashboards** — Beautiful, responsive monitoring interface
- **🔔 Smart Alerting** — Telegram, email, and webhook notifications
- **🔄 Multi-Host Support** — Distributed agent architecture
- **📈 Historical Analysis** — ClickHouse-backed time-series storage

## Quick Start

### Single Server (Default)
```bash
docker compose up -d
```

### Distributed Deployment (Multi-Server)

**Central Server:**
```bash
./deploy-central.sh
```

**Remote Agent:**
```bash
# Set your central server IP
export CENTRAL_SERVER_IP=your-server-ip
docker compose -f docker-compose.agent.yml up -d
```

See [DISTRIBUTED_DEPLOYMENT.md](docs/DISTRIBUTED_DEPLOYMENT.md) for the full guide.

## Environment Variables

Copy `.env.agent.example` to `.env.agent` and configure:

```env
CENTRAL_SERVER_IP=your-server-ip
CLICKHOUSE_USER=AncientReport
CLICKHOUSE_PASSWORD=AncientReport
```

## Part of Xcr9 Platform

AncientReport is part of the [Xcr9](https://xcr9.site) AI infrastructure suite:

- **[MithrilLog](https://xcr9.site/mithrillog.html)** — AI-powered log management
- **[AncientReport](https://xcr9.site/ancientreport.html)** — Autonomous observability (eBPF)
- **[MetalHive](https://xcr9.site/metalhive.html)** — Bare-metal Docker orchestration

## License & Enterprise

This software is licensed under the **Xcr9 Community License**.

- ✅ **Free** for personal and non-commercial use
- ✅ **Free** for small teams (up to 5 nodes)
- 🏢 **Enterprise License** required for commercial use with more than 5 nodes

### Get Enterprise License

Visit **[xcr9.site/pricing](https://xcr9.site/pricing.html)** to purchase an Enterprise license which includes:

- Unlimited nodes
- Priority support
- Custom integrations
- SLA guarantees
- Professional services

### Contact

- 🌐 Website: [xcr9.site](https://xcr9.site)
- � Sales: [xcr9.site/contact](https://xcr9.site/contact.html)

---

*© 2025 Xcr9. Building the future of AI infrastructure.*
