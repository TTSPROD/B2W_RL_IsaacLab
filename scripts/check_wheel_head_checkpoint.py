"""Verify that wheel-head-only training changed no other actor parameters."""

import argparse
import json

import torch


parser = argparse.ArgumentParser()
parser.add_argument("--parent", required=True)
parser.add_argument("--candidate", required=True)
args = parser.parse_args()

parent = torch.load(args.parent, map_location="cpu", weights_only=True)["model_state_dict"]
candidate = torch.load(args.candidate, map_location="cpu", weights_only=True)["model_state_dict"]
if set(parent) != set(candidate):
    raise RuntimeError("Checkpoint state keys differ")

allowed_weight = "actor.6.weight"
allowed_bias = "actor.6.bias"
unchanged = []
for key in parent:
    if key.startswith("actor.") or key == "std":
        if key == allowed_weight:
            equal = torch.equal(parent[key][:12], candidate[key][:12])
        elif key == allowed_bias:
            equal = torch.equal(parent[key][:12], candidate[key][:12])
        else:
            equal = torch.equal(parent[key], candidate[key])
        if not equal:
            raise RuntimeError(f"Forbidden actor change: {key}")
        unchanged.append(key)

wheel_weight_delta = (candidate[allowed_weight][12:] - parent[allowed_weight][12:]).abs()
wheel_bias_delta = (candidate[allowed_bias][12:] - parent[allowed_bias][12:]).abs()
result = {
    "schema": "b2w_wheel_head_checkpoint_check_v1",
    "actor_input_dim": int(candidate["actor.0.weight"].shape[1]),
    "actor_output_dim": int(candidate[allowed_weight].shape[0]),
    "unchanged_actor_tensors_checked": unchanged,
    "wheel_weight_max_abs_delta": float(wheel_weight_delta.max()),
    "wheel_bias_max_abs_delta": float(wheel_bias_delta.max()),
    "wheel_rows_changed": bool(torch.count_nonzero(wheel_weight_delta) or torch.count_nonzero(wheel_bias_delta)),
}
if result["actor_input_dim"] != 57 or result["actor_output_dim"] != 16 or not result["wheel_rows_changed"]:
    raise RuntimeError(f"Wheel-head checkpoint check failed: {result}")
print(json.dumps(result, sort_keys=True))
