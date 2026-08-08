"""
Verify falsification protocol integration in The Void.
"""
import json
import os
import sys

sys.path.insert(0, r'C:\Void\ZQM-AI-Master')
os.chdir(r'C:\Void\ZQM-AI-Master')

class _FakeLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): print('[WARN]', *a)
    def debug(self, *a, **kw): pass

import app.services.falsification_protocol as fp

fp.get_logger = lambda name: _FakeLogger()

protocol = fp.FalsificationProtocol(app_state={
    "envelope": {"task_id": "test-1", "status": "running", "step": 3},
    "working_memory": [
        "analyzing falsification protocol",
        "checking KV-cache boundary",
        "hypothesis: drift detected",
    ],
    "kv_cache": [0.1, 0.2, 0.3, 0.4, 0.5] * 20,
    "cumulative_error": 0.05,
    "last_tool_output": {
        "timestamp": "2026-08-03T12:00:00Z",
        "requestId": "req-1234",
        "random": 5678,
        "result": "success",
        "data": {"value": 42, "label": "integration_test", "checksum": "abc123"},
    },
    "error_curve": [0.01 + i * 0.0001 for i in range(200)],
    "seed": 42,
    "constraints": ["max_length=100", "no_code_switch", "preserve_tense"],
})

# Re-init manifest inside this process so baseline matches
protocol._init_manifest()

report = protocol.full_audit()
print(json.dumps(report, indent=2))
print('\nALL PASSED:', report.get('all_passed'))
