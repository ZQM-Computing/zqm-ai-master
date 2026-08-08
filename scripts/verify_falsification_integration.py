"""
Integration verification: simulate FastAPI app startup + router registration.
"""
import os
import sys

os.chdir(r'C:\Void\ZQM-AI-Master')
sys.path.insert(0, r'C:\Void\ZQM-AI-Master')

# 1. Verify all new imports resolve
print('=== Import checks ===')
try:
    from app.services.falsification_protocol import FalsificationProtocol
    print('[OK] app.services.falsification_protocol')
except Exception as e:
    print('[FAIL]', e)

try:
    from app.routers.falsification import router as falsification_router
    print('[OK] app.routers.falsification')
except Exception as e:
    print('[FAIL]', e)

try:
    from app.orchestrator.zqm_ai_orchestrator import ZQM_AIOrchestrator, _task_app_state
    print('[OK] zqm_ai_orchestrator (with _task_app_state)')
except Exception as e:
    print('[FAIL]', e)

try:
    from app.models.task import Task
    # Verify falsification_report field exists
    assert 'falsification_report' in Task.model_fields
    print('[OK] Task model has falsification_report field')
except Exception as e:
    print('[FAIL]', e)

# 2. Verify router routes
print('\n=== Router routes ===')
routes = [r.path for r in falsification_router.routes]
for path in sorted(set(routes)):
    print(f'  {path}')

# 3. Verify orchestrator instantiation + protocol attachment
print('\n=== Orchestrator instantiation ===')
try:
    orchestrator = ZQM_AIOrchestrator()
    assert hasattr(orchestrator, 'falsification')
    assert isinstance(orchestrator.falsification, FalsificationProtocol)
    print('[OK] orchestrator.falsification is FalsificationProtocol instance')
except Exception as e:
    print('[FAIL]', e)

# 4. Verify full_audit with empty state
print('\n=== full_audit empty-state ===')
try:
    report = orchestrator.falsification.full_audit({})
    assert report.get('all_passed') == True
    print('[OK] empty-state full_audit returns all_passed=true')
except Exception as e:
    print('[FAIL]', e)

# 5. Verify _task_app_state with None
print('\n=== _task_app_state with None trace ===')
try:
    state = _task_app_state(None, None)
    assert 'envelope' in state
    assert state['working_memory'] == []
    print('[OK] _task_app_state handles None gracefully')
except Exception as e:
    print('[FAIL]', e)

# 6. Verify router dependencies
print('\n=== Router dependency check ===')
try:
    from fastapi import APIRouter
    assert isinstance(falsification_router, APIRouter)
    print('[OK] falsification is a valid APIRouter')
except Exception as e:
    print('[FAIL]', e)

print('\nAll integration checks complete.')
