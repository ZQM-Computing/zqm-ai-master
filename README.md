# zqm-ai-master

The Void AI Orchestration System — local-first RAG, reasoning, mesh ops, commercial packaging.

## Overview

This repository contains the core AI orchestration system for ZQM computing infrastructure. It provides:

- **Local-first RAG**: Retrieval-augmented generation with local embeddings
- **Reasoning engine**: Multi-step reasoning and planning
- **Mesh operations**: Distributed agent coordination
- **Commercial packaging**: Production-ready deployment configurations

## Quick Start

```bash
# Clone the repository
git clone https://github.com/ZQM-Computing/zqm-ai-master.git
cd zqm-ai-master

# Install dependencies
pip install -r requirements.txt

# Run the service
python -m app.main
```

## Requirements

- Python 3.12+
- FastAPI
- Ollama (for local LLM inference)
- See `requirements.txt` for full dependencies

## Environment Variables

Create a `.env` file with:

```env
APP_DEBUG=false
LOG_LEVEL=INFO
OLLAMA_HOST=http://localhost:11434
```

## Project Structure

```
zqm-ai-master/
├── app/
│   ├── main.py              # FastAPI application entry
│   ├── core/                # Core utilities (config, logging, security)
│   ├── models/              # Pydantic models
│   ├── inference/           # LLM inference and routing
│   ├── memory/              # Memory and caching
│   └── orchestrator/        # Agent orchestration
├── scripts/                 # Utility scripts
├── tests/                   # Test suite
└── requirements.txt         # Python dependencies
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

See [LICENSE](LICENSE) for details.
