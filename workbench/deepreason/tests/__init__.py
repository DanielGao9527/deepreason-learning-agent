"""Test package bootstrap for direct unittest module invocations."""

from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
src_path = str(SRC_ROOT)
if src_path not in sys.path:
    sys.path.insert(0, src_path)
