"""Frozen inputs and exact restoration checks for the local LR experiment."""
from run_support import ROOT, read_json, sha256

PLAN_PATH = ROOT / 'configs/24650_lr_ab_20260930.json'
PLAN_SHA = '1a510dd230ee9d011d4c04b7a7b3390b2de320b0e89a64c145da5812d62ff1ff'


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


def assert_exact_state(actual, expected, path='state'):
    import torch
    if isinstance(expected, torch.Tensor):
        if not isinstance(actual, torch.Tensor) or not torch.equal(actual.detach().cpu(), expected.cpu()):
            raise ValueError(f'Restored tensor differs: {path}')
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError(f'Restored keys differ: {path}')
        for key in expected:
            assert_exact_state(actual[key], expected[key], f'{path}.{key}')
    elif isinstance(expected, (list,tuple)):
        if not isinstance(actual, (list,tuple)) or len(actual) != len(expected):
            raise ValueError(f'Restored sequence differs: {path}')
        for i,(a,e) in enumerate(zip(actual,expected)):
            assert_exact_state(a,e,f'{path}[{i}]')
    elif actual != expected:
        raise ValueError(f'Restored value differs: {path}')
