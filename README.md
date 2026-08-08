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

`zqm-ai-master` integrates with `zqm-intel-platforms` for shared OSINT/CTI/SIEM/Windows-telemetry primitives. The integration is optional; core installs do not pull it in automatically.

**Install**

```bash
# With intel-platforms extras
pip install 'zqm-ai-master[intel-platforms]'

# Or standalone
pip install 'zqm-intel-platforms[all]>=0.1.0'
```

**Wire the runtime**

The VoidCouncil runtime can attach the intel platform as push targets inside `initialize_integrations()`.

```bash
export ZQM_INTEL_PLATFORMS_URL="http://127.0.0.1:9400"
export ZQM_OBSERVABILITY_URL="http://127.0.0.1:9090"
export ZQM_FLATSPACE_URL="http://127.0.0.1:8080"
export ZQM_GARDEN_URL="http://127.0.0.1:8761"
export ZQM_REDIS_URL="redis://127.0.0.1:6379/0"
```

Start the master service and let the router layer resolve the active config:

```bash
zqm-ai-master serve --host 127.0.0.1 --port 8808 --reload
```

Convene a council session to exercise the integration surface:

```bash
zqm-ai-master council-convene --host 127.0.0.1 --port 8808 --domain reliability
zqm-ai-master council-history --host 127.0.0.1 --port 8808 --limit 20
zqm-ai-master self-improve --host 127.0.0.1 --port 8808
```

**Verify**

```bash
curl -s http://127.0.0.1:8808/api/version
curl -s http://127.0.0.1:8808/api/integration/status
```

If `zqm-intel-platforms` is not installed, integration status reports `unavailable`; install the extra to enable pushes.

**Docs**

See `docs/VOID_INTEGRATION.md` for full wiring details.

## License

Apache-2.0

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
zqm-ai-master void-version --host 127.0.0.1 --port 8808
zqm-ai-master council-domains --host 127.0.0.1 --port 8808
zqm-ai-master council-history --host 127.0.0.1 --port 8808 --limit 20
zqm-ai-master council-convene --host 127.0.0.1 --port 8808 --domain reliability --auto-apply
zqm-ai-master void-talk --host 127.0.0.1 --port 8808 --message "check integrations"
zqm-ai-master self-improve --host 127.0.0.1 --port 8808
```

