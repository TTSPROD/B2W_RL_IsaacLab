"""Frozen inputs and exact restoration checks for the DeepSeek F1 short-flight experiment."""
from run_support import ROOT, read_json, sha256
from state_contract import assert_exact_state

PLAN_PATH = ROOT / 'configs/24650_short_flight_20261001.json'
PLAN_SHA = '99d391dabbc0b07c6e5e2fe4bfc83d6fcf105a44fecb8ae67b5558806c03a554'


def load_plan():
    if sha256(PLAN_PATH) != PLAN_SHA:
        raise ValueError('Frozen F1 plan changed')
    plan = read_json(PLAN_PATH)
    parent = ROOT / plan['parent_checkpoint']
    inputs = [(parent, plan['parent_sha256']),
              (parent.parent/'env.yaml', plan['parent_env_sha256']),
              (parent.parent/'agent.yaml', plan['parent_agent_sha256'])]
    inputs += [(ROOT/plan[key],plan[key+'_sha256']) for key in
               ('basis_report','basis_summary','parent_bank_source')]
    for path, digest in inputs:
        if sha256(path) != digest:
            raise ValueError(f'Frozen F1 input changed: {path}')
    return plan
