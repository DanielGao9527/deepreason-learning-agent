"""Test bootstrap for running unittest directly against the src layout."""

from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
src_path = str(SRC_ROOT)
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def test_bootstrap_import_path() -> None:
    assert src_path in sys.path
