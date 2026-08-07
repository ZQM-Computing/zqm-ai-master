# The Void AI Orchestration System — Security Baseline for Customer Deployments

## Required Hardening
- Rotate `SECRET_KEY` before every customer deployment
- Set `ZQM_ADMIN_PASSWORD` to a strong value
- Set `ZQM_INTERNAL_KEY` and service keys
- Disable external providers unless explicitly enabled
- Remove debug logs from `logs/` before delivery

## Network
- Bind public services to specific interfaces in production
- Enable TLS termination via Traefik
- Restrict CORS origins to customer domains
- Disable or firewall unused mesh ports

## Data Handling
- Customer data stays on customer hardware by default
- Optional telemetry is disabled unless opted in
- Audit logs are stored locally in `app/` and `data/`

## Support Evidence Requirements
- Support requests should include a redacted `.env` and logs excerpt
- Do not send secrets, private keys, or customer documents to support channels
