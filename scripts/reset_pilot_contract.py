"""Frozen reset-only experiment; no simulator dependencies."""
from run_support import ROOT, read_json, sha256

PLAN_PATH = ROOT / 'configs/24650_reset_ab_20261001.json'
PLAN_SHA = '0b01ba76c5bbd492740117a0655f596580deeca3ed9202042ea4d363ecb19d5c'


def load_plan():
    if sha256(PLAN_PATH) != PLAN_SHA:
        raise ValueError('Frozen reset plan changed')
    plan = read_json(PLAN_PATH)
    for name, digest in plan['inputs_sha256'].items():
        if sha256(ROOT/name) != digest:
            raise ValueError('Reset pilot input changed: '+name)
    if plan['updates'] != 300 or plan['num_envs'] != 4096 or plan['seed'] != 9910:
        raise ValueError('Unexpected reset pilot budget/seed')
    return plan


def preflight_decision(control, upright):
    a, b = control['reset_diagnostics'], upright['reset_diagnostics']
    reasons = []
    if b['initial_invalid']['tilt'] or b['initial_invalid']['nonfinite'] or b['initial_invalid']['hard_joint']:
        reasons.append('invalid upright initial state')
    if a['initial_invalid']['tilt'] == 0:
        reasons.append('reset mismatch not reproduced')
    ar, br = a['early_tilt_per_env_second'], b['early_tilt_per_env_second']
    if not br <= .5*ar:
        reasons.append('early tilt rate did not fall by at least 50 percent')
    if b['stale_contact_resets']:
        reasons.append('nonzero contact buffer immediately after reset')
    for name in ('flat', 'rough', 'stairs_up', 'stairs_down'):
        group = upright['coverage'][name]
        if sum(sum(row[1:]) for row in group['segment_attempts']) < 1:
            reasons.append(name+': no non-initial phase attempts')
        # A completed >=12 s zero segment is required; success is assessed later.
        from b2w_core_stage3_sampling import build_banks
        bank = build_banks(load_plan())[name]
        zeros = [(c,p) for c,case in enumerate(bank) for p,s in enumerate(case['segments'])
                 if s['seconds'] >= 12 and not any(s['command'])]
        if not any(group['segment_completions'][c][p] for c,p in zeros):
            reasons.append(name+': no completed long zero segment')
    return {'train_allowed': not reasons, 'reasons': reasons,
            'early_tilt_rate_control': ar, 'early_tilt_rate_upright': br,
            'automatic_promotion': False}
