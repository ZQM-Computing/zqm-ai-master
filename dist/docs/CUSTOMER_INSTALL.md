# Customer Installation Guide — The Void AI Orchestration System

## Requirements
- Windows 10/11 Pro or Server 2019+
- 16 GB RAM minimum, 64 GB recommended
- NVIDIA GPU optional for faster inference
- Docker Desktop installed and running
- Ports 8808, 11434, 7701, 8080 available locally

## Quick Start
1. Clone the private repository provided by ZQM Computing LLC.
2. Copy `.env.example` to `.env` and set the required keys.
3. Run `docker compose up -d`.
4. Run `scripts\\rag_bootstrap.py` to ingest local documents.
5. Start the app service with NSSM or `python -m uvicorn app.main:app --app-dir . --host 0.0.0.0 --port 8808`.
6. Visit `http://localhost:8808/healthz` to verify.

## Authentication
- Default login route: `POST /api/users/login`
- Customer-specific credentials are issued during onboarding.
- JWT tokens are valid for 24 hours by default.

## Support
- Email: admin@zqmlabs.com
- Include node ID, logs/, and .env-safe redacted config when reporting issues.
