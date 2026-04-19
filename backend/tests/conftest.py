"""Shared fixtures for tests."""
import sys
from pathlib import Path

# Make the backend package importable when running `pytest` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
