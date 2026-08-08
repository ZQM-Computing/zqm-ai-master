# Void Integration: zqm-intel-platforms

`zqm-ai-master` integrates with `zqm-intel-platforms` for shared OSINT/CTI/SIEM/Windows-telemetry primitives.

## Integration surface

- **Evidence ingestion**: council findings can be mirrored into flatspace/observability/garden/redis via `initialize_integrations()`.
- **Telemetry routing**: observability events, council session summaries, and mesh metrics are pushed to the intel platform through the optional service hooks in `app/orchestrator/void_council.py`.
- **Operational handoff**: `scripts/verify_falsification_integration.py` validates cross-system consistency between Void outputs and intel platform expectations.

## Required wiring

1. Install the shared intel package in the same environment or service mesh.
2. Set `ZQM_INTEL_PLATFORMS_URL` / related env vars if using the HTTP bridge.
3. Pass runtime handles into Void Council at startup:
   - `observability`
   - `flatspace`
   - `garden`
   - `redis`
4. Confirm `integration_evidence` shows `pushed` for each subsystem after convene.

## Verification

- CLI:
```bash
zqm-ai-master status --host 127.0.0.1 --port 8808
zqm-ai-master health --host 127.0.0.1 --port 8808
```
- Integration checker:
```bash
python scripts/verify_falsification_integration.py
```

## Contact

Alex Zelenski — zqmcomputing@gmail.com
Brand: ZQM Computing / ZQM-Labs
