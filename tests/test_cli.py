"""Tests for zqm-ai-master CLI."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = ["python", "-m", "pip", "show", "-f", "zqm-ai-master"]


def _run_cli(args):
    return subprocess.run(
        [sys.executable, str(REPO / "cli.py"), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_help_renders():
    p = _run_cli(["--help"])
    assert p.returncode == 0
    assert "serve" in p.stdout
    assert "config" in p.stdout


def test_version():
    p = _run_cli(["version"])
    assert p.returncode == 0
    assert p.stdout.strip()


def test_logs_missing_file():
    p = _run_cli(["logs", "--tail", "10"])
    assert p.returncode == 2
    assert "not found" in p.stdout


def test_void_help_lists_void_commands():
    p = _run_cli(["--help"])
    assert p.returncode == 0
    for cmd in ["void-version", "council-domains", "council-history", "council-convene", "void-talk", "self-improve"]:
        assert cmd in p.stdout


def test_void_version_offline_falls_back():
    p = _run_cli(["void-version"])
    assert p.returncode == 0
    assert "request failed" in p.stdout.lower() or p.stdout.strip()
