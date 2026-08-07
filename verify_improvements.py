import urllib.request, json, time, sys, subprocess, os

base = 'http://127.0.0.1:8808'
login = urllib.request.Request(base + '/api/users/login',
    data=json.dumps({'username': 'admin', 'password': ''}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(login, timeout=20) as r:
    token = json.loads(r.read())['data']['access_token']
H = {**{'Authorization': 'Bearer ' + token}, 'Content-Type': 'application/json'}

proofs = []

def check(name, fn):
    try:
        fn()
        proofs.append((name, 'PASS', ''))
    except Exception as e:
        proofs.append((name, 'FAIL', str(e)[:160]))

# 1. Observability enabled in health endpoint
def obs_check():
    req = urllib.request.Request(base + '/api/observability/health', headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
        assert d.get('enabled') is True, f"enabled={d.get('enabled')}"
        assert d.get('status') == 'ok', f"status={d.get('status')}"
        assert d.get('prometheus_client') is True
check('observability_enabled', obs_check)

# 2. Settings reflect observability_enabled=true
def settings_check():
    req = urllib.request.Request(base + '/api/settings', headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())['data']
        assert d.get('observability_enabled') is True
check('settings_observability_enabled', settings_check)

# 3. Scheduler agent exists, idle, and registered
def scheduler_check():
    req = urllib.request.Request(base + '/api/agents', headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
        items = d.get('data', {}).get('items', [])
        scheduler = next((a for a in items if a.get('name') == 'ZQM-Scheduler-Chronos'), None)
        assert scheduler, 'ZQM-Scheduler-Chronos not found'
        assert scheduler.get('status') == 'idle', f"status={scheduler.get('status')}"
        assert scheduler.get('agent_type') == 'scheduler'
check('scheduler_registered_idle', scheduler_check)

# 4. Pagination: page 1 != page 2
def pagination_check():
    def get_ids(page, size):
        req = urllib.request.Request(base + f'/api/agents?page={page}&page_size={size}', headers=H)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
            return [x['agent_id'] for x in d['data']['items']]
    ids1 = get_ids(1, 10)
    ids2 = get_ids(2, 10)
    assert ids1 != ids2, "page 1 and page 2 returned identical agent IDs"
    assert len(ids1) == 10 and len(ids2) == 10
check('pagination_distinct_pages', pagination_check)

# 5. Service status
def service_check():
    out = subprocess.check_output(['nssm', 'status', 'ZQM-Void-N4'], text=True)
    assert 'SERVICE_RUNNING' in out, out
check('nssm_service_running', service_check)

# 6. Fresh boot after restart: uptime under 1 hour
def uptime_check():
    req = urllib.request.Request(base + '/api/status', headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())['data']
        uptime = d.get('uptime_seconds', 0)
        assert uptime < 3600, f"uptime too high: {uptime}"
        assert d.get('status') == 'healthy'
check('process_healthy_fresh_boot', uptime_check)

# Print summary
print('=== PROOF REPORT ===')
passed = sum(1 for p in proofs if p[1] == 'PASS')
failed = sum(1 for p in proofs if p[1] == 'FAIL')
for name, status, err in proofs:
    print(f'{status:4} {name}' + (f' -> {err}' if err else ''))
print(f'\n{passed}/{len(proofs)} passed, {failed} failed')
sys.exit(0 if failed == 0 else 1)
