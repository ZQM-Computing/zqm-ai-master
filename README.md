# zqm-ai-master


![CI](https://github.com/ZQM-Computing/zqm-ai-master/actions/workflows/ci.yml/badge.svg)
![Ruff](https://img.shields.io/badge/lint-ruff-blue)
![Mypy](https://img.shields.io/badge/type--check-mypy-green)


The Void AI Orchestration System — local-first RAG, reasoning, mesh ops, and commercial packaging.

`zqm-ai-master` holds the canonical scripts, verification tests, and orchestration entry points for ZQM AI/ML workflows. It includes LoRA training probes, falsification protocol verifiers, MeiliSync remediation, RAG bootstrap, Windows service installers, and capacity probes — all oriented toward running on ZQM Windows workstations.

## Contents

| Path | Role |
|------|------|
| `scripts/train_lora.py` | LoRA fine-tuning runner |
| `scripts/train_lora_poc.py` | LoRA proof-of-concept runner |
| `scripts/train_distributed.py` | Multi-node distributed training |
| `scripts/rag_bootstrap.py` | RAG index bootstrap |
| `scripts/diag_rag.py` | RAG diagnostic runner |
| `scripts/sync_meili.py` | MeiliSearch sync |
| `scripts/eval_benchmark.py` | Evaluation/benchmark runner |
| `scripts/model_registry.py` | Model registry management |
| `scripts/verify_falsification_protocol.py` | Falsification protocol verifier |
| `scripts/verify_falsification_integration.py` | Falsification integration checker |
| `scripts/repro_flatspace_semantic.py` | Flatspace semantic reproducer |
| `scripts/meili_chroma_remediation_plan.py` | Meili/Chroma remediation plan |
| `scripts/full_enumeration_tests.py` | Full enumeration test runner |
| `scripts/ingest_c_drive.py` | C:\ ingest pipeline |
| `scripts/setup_env.ps1` | Environment setup |
| `scripts/verify_install.ps1` | Install verification |
| `scripts/install_service.ps1` | Windows service install |
| `scripts/probe_winrm.ps1` | WinRM probe |
| `scripts/capacity.ps1` | Capacity check |
| `scripts/fix_mesh_firewall.ps1` | Mesh firewall fix |
| `void-operations-diagram.html` | Void operations diagram |
| `void-3d-explorer.html` | 3D void explorer |
| `tests/` | pytest test suite |

## Integration: zqm-intel-platforms

This repo integrates with `zqm-intel-platforms` for shared OSINT/CTI/SIEM/Windows-telemetry primitives.

## License

MIT unless otherwise noted in submodules.

## Contact

Alex Zelenski — zqmcomputing@gmail.com
Brand: ZQM Computing / ZQM-Labs


## CLI

Installed entrypoint:
```bash
zqm-ai-master --help
```

Subcommands:
```bash
zqm-ai-master serve --host 127.0.0.1 --port 8808 --reload
zqm-ai-master health --host 127.0.0.1 --port 8808
zqm-ai-master status --host 127.0.0.1 --port 8808
zqm-ai-master info --host 127.0.0.1 --port 8808
zqm-ai-master agents --host 127.0.0.1 --port 8808
zqm-ai-master routes --host 127.0.0.1 --port 8808
zqm-ai-master routes --offline
zqm-ai-master config --host 127.0.0.1 --port 8808
zqm-ai-master logs --tail 100
zqm-ai-master logs --follow
zqm-ai-master test
zqm-ai-master version
```
