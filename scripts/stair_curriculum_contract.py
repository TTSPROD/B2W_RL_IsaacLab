"""Frozen inputs and exact restoration checks for the local stair curriculum experiment."""
from run_support import ROOT, read_json, sha256
from state_contract import assert_exact_state

PLAN_PATH = ROOT / 'configs/24650_stair_curriculum_ab_20260930.json'
PLAN_SHA = 'aea63ffcbcdb07c452a8d45cad8da84fa2c09e65ab1ee44614da63e91ffe7548'


def load_plan():
    if sha256(PLAN_PATH) != PLAN_SHA:
        raise ValueError('Frozen LR plan changed')
    plan = read_json(PLAN_PATH)
    parent = ROOT / plan['parent_checkpoint']
    inputs = [(parent, plan['parent_sha256']),
              (parent.parent/'env.yaml', plan['parent_env_sha256']),
              (parent.parent/'agent.yaml', plan['parent_agent_sha256'])]
    inputs += [(ROOT/plan[key],plan[key+'_sha256']) for key in
               ('basis_report','basis_summary','parent_bank_source')]
    for path, digest in inputs:
        if sha256(path) != digest:
            raise ValueError(f'Frozen LR input changed: {path}')
    return plan
