"""Committed plan inputs for behavior tests; runtime loaders verify raw provenance."""

from pathlib import Path

from run_support import read_json

ROOT = Path(__file__).resolve().parents[1]


def plan(name):
    return read_json(ROOT / "configs" / name)
