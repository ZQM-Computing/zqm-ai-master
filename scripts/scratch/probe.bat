@echo off
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONPATH=C:\Users\zqmco\AppData\Roaming\Python\Python312\site-packages
cd /d C:\Void\ZQM-AI-Master
"C:\Program Files\Python312\python.exe" -c "import fastapi; print('fastapi', fastapi.__version__, 'from', fastapi.__file__)" > "C:\Void\ZQM-AI-Master\sysrun3.log" 2>&1
"C:\Program Files\Python312\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8812 --workers 1 --app-dir C:\Void\ZQM-AI-Master >> "C:\Void\ZQM-AI-Master\sysrun3.log" 2>&1
