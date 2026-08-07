# ZQM-AI-Master — Lessons Learned

Date: 2026-08-05
Runtime: N4 (192.168.1.228:8808) API version 2.1.4

---

## 1. Duplicate launchers beat code bugs
The :8808 port mismatch was not a service misconfiguration or code defect; it was a scheduled task double-launching uvicorn alongside NSSM. When a port owner looks wrong, check parent process lineage first. Process-parent inspection often beats code spelunking.

## 2. Disable, don’t delete, duplicate triggers
We disabled the `ZQM-Void-N4` scheduled task instead of deleting it or the batch file. Disable gives you instant rollback. If NSSM later fails, re-enable the scheduled task and you’re back up while debugging.

## 3. Health checks must distinguish core from external
`get_health()` separates core health from external deps (`garden`, `flatspace`, `observability`). That design prevented false 500s when optional backends were unreachable. It’s a pattern worth copying elsewhere.

## 4. Async side effects need ordering guarantees
The falsification audit runs before `_post_execution()` persists to FLATSPACE and pushes metrics. Audit the state first, then fire async side effects. Otherwise the report can diverge from what was actually stored.

## 5. Memory fallback needs existence checks
`FLATSPACE_MODE=auto` silently fails if remote is unreachable and local DB is missing. Always verify the local DB file exists at startup, or make the missing-DB case explicit in logs rather than silent.

## 6. Observability push should default to no-op, not crash
Observability is disabled in current config and the service handles that cleanly. Optional telemetry paths must be fail-soft. `if not enabled: return` is the correct primitive.

## 7. Traefik + hosts repoint beats port publishing
We chose hostname-based access via Traefik over publishing host ports. This keeps Docker internal, preserves ingress architecture, and avoids Windows service port conflicts.

## 8. DNS host-port conflicts on Windows need ownership clarity
CoreDNS was statically pinned to `172.21.0.6`, conflicting with authentik-server. Avoid static IP pins in Docker compose; let Docker assign dynamically and reference the assigned IP.

## 9. Python SSL on Windows needs explicit cafile
System tools trust Windows Root store; Python does not. Ship a reusable SSL-context helper for all internal HTTPS calls so custom CAs work without monkey-patching global state.

## 10. Rate-limited retries need the right request shape
First retry failed with `parent_id must be a UUID`; second retry used the correct body schema and succeeded. Read the exact error string. It tells you whether the problem is auth, schema, or rate limit.

## 11. Cross-posting deduplication is title+author based
Same title + author → same post ID across submolts. Vary titles if you truly want separate posts; otherwise you’re just moving one post.

## 12. Compact context is cheap; full investigation is not
Early probes assumed multiple bugs (`/api/status`, `/api/garden/metrics`, missing enum) that turned out to be either already fixed or probe artifacts. Run the minimal live probe first. Don’t stack hypotheses before evidence.
