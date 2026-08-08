import json
import time
import urllib.request

base = 'http://127.0.0.1:8808'
login = urllib.request.Request(base + '/api/users/login',
    data=json.dumps({'username': 'admin', 'password': ''}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(login, timeout=20) as r:
    token = json.loads(r.read())['data']['access_token']
H = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}

TESTS = [
    ('nlp', 'Translate to French: The agent reviewed the telemetry.'),
    ('reasoning', 'If A implies B and B implies C, does A imply C?'),
    ('gis', 'List GIS analyses relevant to flood risk mapping.'),
    ('hydrology', 'Explain baseflow separation in one paragraph.'),
    ('infrastructure', 'Summarize common infrastructure monitoring checks.'),
    ('synthesis', 'Synthesize the key tradeoffs between local and hosted inference.'),
    ('memory', 'What are the failure modes of session resumption from logs?'),
    ('code', 'Write a Python one-liner to compute SHA-256 of a string.'),
    ('network', 'List three network diagnostics for latency and packet loss.'),
    ('file', 'What does llava analyze best: images, audio, or video?'),
    ('security', 'List three controls for agent authorization boundary enforcement.'),
    ('data', 'List three SQL queries useful for task-cost analysis.'),
    ('observability', 'What does a falsification protocol audit at execution boundaries?'),
    ('garden', 'What is the role of a garden queen in a mesh node hierarchy?'),
    ('scheduler', 'List three scheduling constraints for multi-agent task execution.'),
    ('learning', 'Explain why calibration offset matters for agent confidence.'),
    ('flatspace', 'What is the difference between BitGarden and PollenStore tiers?'),
    ('api', 'List common API health-check endpoints and their purpose.'),
    ('quantum', 'What does quantum_llm_bridge verify across mesh nodes?'),
    ('translation', 'Translate to Spanish: The mesh latency was acceptable.'),
    ('entity_extraction', 'Extract named entities from: Alice in Seattle met Bob at AWS re:Invent.'),
    ('web_search', 'List typical sources used for live web discovery and verification.'),
    ('vector_search', 'What is the role of embedding-assisted search in a memory tier?'),
]

results = []
for agent_type, prompt in TESTS:
    body = json.dumps({
        'input': prompt,
        'cognitive_level': 'basic',
        'stream': False,
        'timeout': 180,
        'model': 'qwen2.5:0.5b',
        'context': {'functional_test_agent_type': agent_type},
    }).encode()
    req = urllib.request.Request(base + '/api/process', data=body, headers=H, method='POST')
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read())
            ok = r.status == 200 and data.get('success') is True
            rid = data.get('data', {}).get('request_id') or data.get('request_id')
            model = data.get('data', {}).get('model_used') or data.get('model_used')
            dur = round(time.time() - start, 2)
            results.append((agent_type, r.status, ok, dur, rid, model))
            print(f"{agent_type:18} status={r.status} ok={ok} time={dur}s model={model} id={rid}")
    except Exception as e:
        dur = round(time.time() - start, 2)
        results.append((agent_type, 'ERR', False, dur, None, str(e)[:80]))
        print(f"{agent_type:18} status=ERR ok=False time={dur}s err={str(e)[:80]}")

print(f"\ncompleted={len(results)} ok={sum(1 for r in results if r[2])} fail={sum(1 for r in results if not r[2])}")
