"""Frozen contract for the evidence-driven 2x2 stage-1 micro sweep."""
from run_support import ROOT, read_json, sha256

SPEC_PATH = ROOT / "configs/24650_micro_sweep_20261005.json"
SPEC_SHA = "484d3ea97b0f5906d804bf65ac3b45e7ac48108ae6809063f6e38571eb0ec032"
ARMS = ("standard_order", "standard_balanced", "conservative_order", "conservative_balanced")


def load_spec():
    if sha256(SPEC_PATH) != SPEC_SHA:
        raise ValueError("Frozen micro-sweep specification changed")
    spec = read_json(SPEC_PATH)
    inputs = (
        (spec["basis"]["gradient_audit"], spec["basis"]["gradient_audit_sha256"]),
        (spec["parent"]["checkpoint"], spec["parent"]["sha256"]),
        ("policies/local/core_24650/agent.yaml", spec["parent"]["agent_sha256"]),
        ("policies/local/core_24650/env.yaml", spec["parent"]["env_sha256"]),
        (spec["common"]["standard_train"], spec["common"]["standard_train_sha256"]),
    )
    for relative, expected in inputs:
        if sha256(ROOT / relative) != expected:
            raise ValueError("Frozen micro-sweep input changed: " + relative)
    if tuple(spec["variants"]) != ARMS:
        raise ValueError("Unexpected micro-sweep variants/order")
    stage = spec["stage1"]
    if (stage["seed"], stage["num_envs"], stage["updates"], stage["steps_per_update"]) != (9912, 512, 25, 24):
        raise ValueError("Unexpected stage-1 budget")
    return spec
