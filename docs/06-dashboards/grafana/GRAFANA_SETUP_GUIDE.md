# SENTINEL Building Intelligence Dashboard — Grafana Setup Guide

> Media Wall Intelligence for Facilities Management Operations

---

## Overview

The SENTINEL Building Intelligence Dashboard provides real-time visibility into facility operations across your building portfolio. Designed for 24/7 media wall display in operations centres, it surfaces critical alerts, equipment health, KPIs, and maintenance workload at a glance.

**9 Dashboard Panels:**

| # | Panel | Type | Purpose |
|---|-------|------|---------|
| 1 | Active Alerts by Severity | Donut chart | Distribution of open alerts (critical/warning/info) |
| 2 | Critical Alerts | Stat (large) | Count of active critical alerts — turns red when > 0 |
| 3 | First-Time Fix Rate | Gauge | Target 95%+ — measures operational effectiveness |
| 4 | SLA Attainment | Gauge | Target 95%+ — measures service delivery reliability |
| 5 | Avg Critical Response Time | Stat | Target < 5 minutes — time to first response |
| 6 | Job Card Throughput Trend | Time series | Jobs processed per hour over 24 hours |
| 7 | Active Equipment Issues | Table | Current issues by building, colour-coded severity |
| 8 | Degrading Equipment | Pie chart | Predictive view — equipment showing early degradation |
| 9 | Maintenance Backlog | Stacked bar | Pending maintenance days per building |

---

## Installation (5 Phases)

### Phase 1: Install Grafana

```bash
# Debian/Ubuntu
sudo apt-get install -y apt-transport-https software-properties-common
sudo mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install grafana

# Start and enable
sudo systemctl daemon-reload
sudo systemctl start grafana-server
sudo systemctl enable grafana-server
```

Access at `http://localhost:3000` (default credentials: admin/admin).

### Phase 2: Add Prometheus Data Source

1. Go to **Configuration > Data Sources**
2. Click **Add data source** and select **Prometheus**
3. Set URL to your Prometheus server (e.g., `http://localhost:9090`)
4. Click **Save & Test** to verify connection

### Phase 3: Import Dashboard JSON

1. Go to **Dashboards > New > Import**
2. Upload `grafana-dashboard-config.json` from this directory
3. Select **Prometheus** as the data source
4. Click **Import**

### Phase 4: Configure SENTINEL Metrics Export

SENTINEL must expose Prometheus metrics at a `/metrics` endpoint. Add this scrape config to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'sentinel'
    static_configs:
      - targets: ['localhost:9095']
    scrape_interval: 10s
    metrics_path: /api/metrics
```

Adjust `localhost:9095` to match your SENTINEL backend deployment.

**Required Prometheus metrics from SENTINEL:**

| Metric Name | Labels | Description |
|------------|--------|-------------|
| `sentinel_alerts` | `severity`, `building`, `status` | Active alert gauge by severity and building |
| `sentinel_job_cards` | `building`, `status`, `outcome` | Job card records (completed, in_progress, etc.) |
| `sentinel_job_cards_total` | `building` | Counter of total job cards created |
| `sentinel_sla_met` | `building` | Count of SLA-compliant completed jobs |
| `sentinel_critical_response_time_seconds` | `severity`, `building` | Response time histogram for critical alerts |
| `sentinel_equipment_health` | `building`, `equipment`, `health` | Equipment health status (healthy/degrading/failed) |
| `sentinel_equipment_issues` | `building`, `equipment`, `issue`, `severity` | Active equipment issue details |
| `sentinel_maintenance_backlog_days` | `building` | Days of pending maintenance work per building |

### Phase 5: Deploy on Media Wall

1. Open the dashboard URL on your media wall display browser
2. Press **F** for full-screen mode (or **Ctrl+K** > **Toggle kiosk mode**)
3. Auto-refresh is pre-configured at 10 seconds
4. Set the browser to auto-start on boot with the dashboard URL

**Recommended kiosk URL:**
```
http://grafana-host:3000/d/sentinel-media-wall/sentinel-building-intelligence-media-wall?orgId=1&kiosk
```

---

## Customisation

### Building Filter

The dashboard includes a **Building** dropdown at the top:
- **All** (default) — portfolio-wide view for media wall
- Select specific buildings to drill down
- Multi-select supported for regional views (e.g., all inland sites)

### Refresh Rate

Currently set to **10 seconds** (real-time feel for media wall).
- For slower networks: increase to 30s or 1m
- For busy Prometheus instances: increase to 30s
- To change: click refresh icon in top-right > select interval

### Colour Thresholds

Pre-configured thresholds:

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| First-Time Fix Rate | >= 95% | 80-95% | < 80% |
| SLA Attainment | >= 95% | 90-95% | < 90% |
| Critical Response Time | < 5 min | 5-10 min | > 10 min |
| Critical Alerts Count | 0 | 1-4 | >= 5 |

To adjust: edit panel > Field > Thresholds.

### Time Range

- Default: **Last 24 hours** (recommended for media wall — shows daily context)
- Adjustable via time picker (top right)
- For shift-based ops: set to 8h or 12h

### Timezone

Pre-configured for `Africa/Johannesburg` (SAST). Change in dashboard settings if deploying elsewhere.

---

## Media Wall Best Practices

1. **Screen size:** 55" or larger for visibility from across the operations room
2. **Dark theme:** Pre-configured — reduces eye strain for 24/7 display
3. **Full-screen mode:** Always use kiosk mode (`?kiosk` URL parameter)
4. **Panel positioning:** Critical alerts stat (top right) draws eyes immediately
5. **Refresh rate:** 10s gives real-time feel without overloading the server
6. **Auto-start:** Configure the display browser to open the dashboard URL on boot
7. **Multiple screens:** Use the building filter to show different regions on different screens
8. **Daily briefing:** Screenshot or PDF export for facility team shift handover
9. **Alert sound:** Consider browser extension for audible alert when critical count > 0

---

## Troubleshooting

### No Data Appearing

- Check Prometheus data source connection: **Configuration > Data Sources > Test**
- Verify SENTINEL is exporting metrics: `curl http://localhost:9095/api/metrics`
- Check Prometheus scrape targets: `http://prometheus:9090/targets`
- Ensure scrape interval matches dashboard refresh (10s recommended)

### Panels Show "No Data"

- Verify metric names match exactly (case-sensitive)
- Check label names in queries (`building`, `severity`, `status`)
- Test queries directly in Prometheus: `http://prometheus:9090/graph`
- Ensure the building filter variable isn't filtering out all data

### High Memory/CPU Usage

- Increase refresh interval from 10s to 30s
- Reduce time range from 24h to 12h or 6h
- Check Prometheus retention policy (default 15 days, reduce if needed)
- Consider recording rules for expensive aggregation queries

### Dashboard Not Loading on Media Wall

- Check browser memory (Chrome can OOM on long-running kiosk sessions)
- Add a browser extension to auto-reload every 24h to prevent memory leaks
- Ensure Grafana server has sufficient resources (2 CPU, 2GB RAM minimum)

---

## File Reference

| File | Purpose |
|------|---------|
| `grafana-dashboard-config.json` | Import directly into Grafana (Dashboards > Import) |
| `GRAFANA_SETUP_GUIDE.md` | This file — installation and configuration guide |
| `grafana-dashboard-preview.tsx` | React component for visual preview with simulated data |

---

*Last updated: 2026-03-03 | SENTINEL Building Intelligence v43.0*
