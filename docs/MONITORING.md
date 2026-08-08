# Prometheus + Grafana monitoring for ZQM-AI-Master

This repo ships optional monitoring wiring only. It does **not** start
monitoring services automatically; they are intentionally decoupled from the
application runtime.

## Contents

- `docker-compose.monitoring.yml` — node-exporter, cAdvisor, Prometheus, Grafana.
- `monitoring/prometheus.yml` — base Prometheus config.
- `scripts/prometheus_scrape_rules.yml` — alert rules.
- `app/routers/observability.py` — `/api/observability/metrics` endpoint.

## Local stack scrape targets

The local ZQM-Void-N4 service is the N4 service on this host. In Docker
Compose networking, `host.docker.internal:8808` resolves to the host N4 port.

Default scrape targets:

- ZQM-Void-N4: `http://host.docker.internal:8808/api/observability/metrics`
- Meilisearch: `http://host.docker.internal:7701/metrics`
- Chroma: `http://host.docker.internal:8001/metrics`
- SearXNG: `http://host.docker.internal:8080/metrics`
- Ollama: `http://host.docker.internal:11434/metrics`
- Redis: `http://host.docker.internal:6379/metrics` if redis_exporter is added
  by the operator; otherwise monitor via Redis INFO integration or an
  externally supplied exporter.

## How to start the monitoring stack

From the repo root:

```
docker compose -f docker-compose.monitoring.yml up -d
```

Then open Grafana at `http://localhost:3001`.

Prometheus UI: `http://localhost:9091`.

### Default Grafana credentials

- user: `admin`
- password: value of `GRAFANA_PASSWORD` or `zqm_void_admin`

## Scrape rules

`scripts/prometheus_scrape_rules.yml` is mounted into Prometheus. It provides
basic rules such as:

- alert when a target is down
- warning when a scrape is slow

Add service-specific rules under `groups:` as needed.

## Application metrics endpoint

`app/routers/observability.py` exposes:

- `GET /api/observability/metrics` — Prometheus text exposition format.
- `GET /api/observability/health` — pipeline health.

The metrics endpoint prefers `observability_service` metrics when available,
and falls back to dependency health-derived metrics so Prometheus always has
scrapeable content even before internal metrics are emitted.

## Do not restart runtime services

This wiring is additive. It does not modify `.env`, runtime containers, or the
NSSM-managed ZQM-Void-N4 service.
