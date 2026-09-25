"""19999 operating-range screen; direct body commands, no heading feedback.

This selects commands within the vendor ranges and outside its linear deadband.
It measures a frozen actor, not the distribution of its original training rollouts.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import hashlib

import numpy as np

from locomotion57_protocol import (
    ROOT, CHECKPOINT_SHA, Case, Segment, export_path, sha256,
)

POLICIES = (19999,)
SEED_START = 8201
SEEDS = 32
CONFIG = ROOT / "configs/locomotion57_19999_operating_screen_20260925.json"
SOURCES = ("operating57_protocol.py", "eval_operating57_isaac.py",
           "locomotion57_protocol.py", "local_b2w_assets.py")


def cases_for(terrain="flat"):
    if terrain != "flat":
        raise ValueError("Fresh operating screen is Flat; other terrains require a separate protocol")
    zero = (0.0, 0.0, 0.0)
    start, stop = Segment(2, zero, "initialization"), Segment(12, zero)
    cases = [Case("stand", "flat", (Segment(12, zero),))]
    for axis, name in enumerate(("vx", "vy", "wz")):
        for speed in (.3, .5, .7, 1.0):
            for sign in (-1, 1):
                command = [0.0] * 3
                command[axis] = sign * speed
                cases.append(Case(f"{name}_{sign*speed:+.2f}", "flat",
                                  (start, Segment(30, tuple(command)), stop)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cases.append(Case(f"diagonal_{sx:+d}_{sy:+d}", "flat",
                              (start, Segment(30, (.5*sx, .5*sy, 0.0)), stop)))
            cases.append(Case(f"turning_{sx:+d}_{sy:+d}", "flat",
                              (start, Segment(30, (.5*sx, 0.0, .5*sy)), stop)))
    for axis, name in enumerate(("vx", "vy", "wz")):
        segments = [start]
        for value in (.3, .7, -.5):
            command = [0.0] * 3
            command[axis] = value
            segments.append(Segment(10, tuple(command)))
        cases.append(Case(f"transitions_{name}", "flat", tuple(segments) + (stop,)))
    return cases


def vendor_range_supported(case):
    """Range/deadband coverage only, not equality to the training distribution."""
    for segment in case.segments:
        command = np.asarray(segment.command)
        magnitude = np.linalg.norm(command[:2])
        if segment.kind not in ("constant", "initialization"):
            return False
        if np.any(np.abs(command) > 1.0) or 0 < magnitude <= .2 + 1e-8:
            return False
    return True


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def protocol_manifest():
    frozen = json.loads(CONFIG.read_text(encoding="utf-8"))
    for name, expected in frozen["source_sha256"].items():
        if sha256(ROOT / "scripts" / name) != expected:
            raise RuntimeError(f"Frozen source changed: {name}")
    if sha256(export_path()) != frozen["export_sha256"]:
        raise RuntimeError("Frozen export changed")
    checkpoint = ROOT / "policies/server/upstream_19999/upstream_model_19999.pt"
    if sha256(checkpoint) != frozen["checkpoint_sha256"]:
        raise RuntimeError("Frozen checkpoint changed")
    # JSON stores tuples as arrays.
    if json.loads(json.dumps([asdict(case) for case in cases_for()])) != frozen["cases"]:
        raise RuntimeError("Frozen schedules changed")
    return frozen


if __name__ == "__main__":
    print(f"Verified {protocol_manifest()['episodes']} operating57 episodes")
