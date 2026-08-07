# The Void AI Orchestration System — Customer Operations Guide

## Overview
- Local AI platform: chat, RAG, reasoning, document automation, workflow orchestration
- Runs on your hardware, no mandatory cloud dependency
- Access via HTTP API and optional web UIs

## Core Capabilities
- Conversational AI through `/api/void/talk`
- Retrieval-augmented generation over your own documents through `/api/rag/query`
- Reasoning workflows through `/api/reasoning/query`
- Self-improvement and audit logs through `/api/self-improvement`, `/api/task-audit`, `/api/mcp-audit`
- Optional automation through n8n, document processing through Stirling PDF, speech through Whisper

## Administration
- Health check: `GET /healthz`
- Readiness: `GET /api/healthz`
- Version: `GET /api/version`
- Auth: `POST /api/users/login`
- Tokens expire after 24 hours by default

## Support
- Contact: admin@zqmlabs.com
- Include deployment ID, logs/, and redacted `.env` when reporting issues
