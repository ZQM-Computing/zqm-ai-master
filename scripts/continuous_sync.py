"""
Background daemon that watches app/flatspace_local.db mtime and triggers
Meilisearch + Chroma sync scripts on change.

Windows-friendly polling watchdog; no inotify dependency.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, "app", "flatspace_local.db")
PIDFILE = "/tmp/zqm-sync.pid"
DEFAULT_INTERVAL = 30


def _script(name: str) -> str:
    return os.path.join(REPO_ROOT, "scripts", name)


def _run(name: str) -> None:
    path = _script(name)
    print("triggering", path)
    try:
        subprocess.run([sys.executable, path], check=True)
    except subprocess.CalledProcessError as exc:
        print("sync_failed", name, exc)


def _pid_write(pid: int) -> None:
    try:
        with open(PIDFILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass


def _pid_read() -> int | None:
    try:
        with open(PIDFILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return False


def _should_exit() -> bool:
    pid = _pid_read()
    if pid is None:
        return False
    return pid != os.getpid() or not _pid_exists(pid)


def daemon(interval: int = DEFAULT_INTERVAL) -> None:
    _pid_write(os.getpid())
    print("daemon_started pid=", os.getpid(), "interval=", interval, sep="")
    last_mtime = None
    if os.path.exists(DB_PATH):
        last_mtime = os.path.getmtime(DB_PATH)

    while True:
        if _should_exit():
            print("daemon_exit_requested")
            break
        try:
            current = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else None
        except Exception:
            current = None

        if current is not None and last_mtime is not None and current != last_mtime:
            print("db_changed")
            _run("sync_meili.py")
            _run("sync_chroma.py")
            last_mtime = current
        elif current is not None and last_mtime is None:
            last_mtime = current

        time.sleep(interval)


def once() -> None:
    _run("sync_meili.py")
    _run("sync_chroma.py")


def main() -> int:
    parser = argparse.ArgumentParser(description="Flatspace continuous sync daemon")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Polling interval seconds")
    parser.add_argument("--once", action="store_true", help="Run one sync cycle and exit")
    args = parser.parse_args()

    if args.once:
        once()
        return 0

    if args.daemon:
        daemon(args.interval)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
