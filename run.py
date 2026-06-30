"""CLI entry point for Samsung Rubicon QA automation"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from app.main import run

if __name__ == "__main__":
    run()