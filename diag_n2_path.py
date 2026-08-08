import os

import paramiko

pw = os.environ.get("QUANTUM_LLM_SSH_PW", "EllaRose89!")
host = "192.168.1.31"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, username="zqmlocal", password=pw, timeout=15, look_for_keys=False)
cmds = [
    'powershell -Command "Get-CimInstance Win32_Process -Filter name=ollama.exe | Select-Object ProcessId,ExecutablePath,CommandLine | Format-List"',
    'cmd /c "curl -s http://127.0.0.1:11434/api/version"',
    'cmd /c "curl -s http://127.0.0.1:11434/api/tags"',
]
for cmd in cmds:
    try:
        _, o, e = c.exec_command(cmd, timeout=30)
        out = o.read().decode(errors="replace").strip()
        err = e.read().decode(errors="replace").strip()
        print("CMD:", cmd)
        print("OUT:", out[:600])
        print("ERR:", err[:200])
        print()
    except Exception as ex:
        print("CMD", cmd, "FAIL", type(ex).__name__, str(ex)[:120])
c.close()
