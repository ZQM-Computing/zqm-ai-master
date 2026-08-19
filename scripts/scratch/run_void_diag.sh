#!/bin/bash
cd /c/Void/ZQM-AI-Master || { echo "cd FAIL"; exit 1; }
export PYTHONPATH=/c/Void/ZQM-AI-Master
echo "== launching void app (will show crash traceback) =="
timeout 8 "/c/Program Files/Python312/python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8808 --workers 1 --app-dir /c/Void/ZQM-AI-Master
echo "exit=$? (124=survived-timeout=healthy, other=crashed)"
