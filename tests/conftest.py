"""Shared fixtures for unit tests."""
import sys
from pathlib import Path

# Add repo root to path so app imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
