"""Time-only command banks for the 24650 pure-axis exposure experiment."""
from __future__ import annotations


ZERO = [0.0, 0.0, 0.0]


def _segment(command, seconds, mode):
    return {"command": list(command), "seconds": float(seconds), "mode": int(mode)}


def _axis_case(name, weight, axis):
    segments = [_segment(ZERO, 2, 0)]
    for sign in (1.0, -1.0):
        for speed, seconds in ((0.3, 6), (0.7, 6), (1.0, 8)):
            command = [0.0, 0.0, 0.0]
            command[axis] = sign * speed
            segments.append(_segment(command, seconds, (2, 3, 1)[axis]))
        segments.append(_segment(ZERO, 12, 0))
    return {"case": name, "weight": float(weight), "segments": segments}


def _mixed_case(weight):
    return {"case": "mixed", "weight": float(weight), "segments": [
        _segment(ZERO, 2, 0),
        _segment([0.5, 0.5, 0.0], 8, 4),
        _segment([0.5, 0.0, 0.5], 8, 5),
        _segment(ZERO, 12, 0),
        _segment([-0.5, -0.5, 0.0], 8, 4),
        _segment([-0.5, 0.0, -0.5], 8, 5),
        _segment(ZERO, 12, 0),
    ]}


def _stand_case(weight):
    return {"case": "stand", "weight": float(weight),
            "segments": [_segment(ZERO, 60, 0)]}


def _stair_case(name, weight):
    speed = float(name.rsplit("_", 1)[1])
    if name.startswith("traverse"):
        segments = [_segment(ZERO, 2, 0), _segment([speed, 0, 0], 20, 2),
                    _segment(ZERO, 12, 0)]
    else:
        first = 5 if speed == 0.3 else 4
        second = 20 if speed == 0.3 else 16
        segments = [_segment(ZERO, 2, 0), _segment([speed, 0, 0], first, 2),
                    _segment(ZERO, 12, 0), _segment([speed, 0, 0], second, 2),
                    _segment(ZERO, 12, 0)]
    return {"case": name, "weight": float(weight), "segments": segments}


def build_banks(plan):
    """Expand the reviewed plan into tensor-bank compatible schedules."""
    banks = {}
    for name, declarations in plan["banks"].items():
        cases = []
        for item in declarations:
            case = item["case"]
            if case in ("longitudinal", "lateral", "yaw"):
                cases.append(_axis_case(case, item["weight"], item["axis"]))
            elif case == "mixed":
                cases.append(_mixed_case(item["weight"]))
            elif case == "stand":
                cases.append(_stand_case(item["weight"]))
            elif case.startswith(("traverse_", "stop_restart_")):
                cases.append(_stair_case(case, item["weight"]))
            else:
                raise ValueError(f"Unknown core stage-3 case: {case}")
        banks[name] = cases
    return banks
