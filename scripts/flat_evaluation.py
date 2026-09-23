"""Reproducible held-out Flat cases and acceptance statistics (no simulator import)."""
import math
import random

SCENARIOS = [
    ('stand', (0., 0., 0.)), ('forward', (.5, 0., 0.)),
    ('backward', (-.5, 0., 0.)), ('lateral', (0., .3, 0.)),
    ('yaw_positive', (0., 0., .5)), ('yaw_negative', (0., 0., -.5)),
    ('forward_stop', (.5, 0., 0.)), ('backward_stop', (-.5, 0., 0.)),
]


def make_cases(count, seed, heldout=False):
    rng = random.Random(seed)
    cases = []
    for i in range(count):
        name, fixed = SCENARIOS[i % len(SCENARIOS)]
        command = list(fixed)
        if heldout:
            if command[0]:
                command[0] = math.copysign(rng.uniform(.2, .5), command[0])
            if command[1]:
                command[1] = rng.choice([-1, 1]) * rng.uniform(.15, .3)
            if command[2]:
                command[2] = math.copysign(rng.uniform(.2, .5), command[2])
        cases.append({'env': i, 'scenario': name, 'command': command,
                      'initial_yaw_rad': rng.uniform(-math.pi, math.pi) if heldout else 0.,
                      'leg_position_offset_rad': [rng.uniform(-.025, .025) if heldout else 0. for _ in range(12)]})
    return cases


def wilson(successes, count):
    if count <= 0 or not 0 <= successes <= count:
        raise ValueError('Invalid success counts')
    z = 1.959963984540054
    p = successes / count
    denominator = 1 + z*z/count
    center = (p + z*z/(2*count))/denominator
    half = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count))/denominator
    return [max(0., center-half), min(1., center+half)]


def summarize(results):
    def group(rows):
        n = len(rows)
        successes = sum(row['no_fall_or_body_contact'] for row in rows)
        errors = [row['rms_vx_vy_yaw'] for row in rows]
        # All episodes included, including failures: never select only survivors.
        rms = [math.sqrt(sum(row[k]**2 for row in errors)/n) for k in range(3)]
        ordered = [sorted(row[k] for row in errors) for k in range(3)]
        p95 = [axis[math.ceil(.95*n)-1] for axis in ordered]
        maximum = [axis[-1] for axis in ordered]
        return {'episodes': n, 'no_fall_count': successes, 'no_fall_fraction': successes/n,
                'no_fall_wilson95': wilson(successes, n),
                'tracking_pass_count': sum(row['tracking_threshold_met'] for row in rows),
                'pooled_rms_vx_vy_yaw': rms, 'episode_rms_p95': p95, 'episode_rms_max': maximum}
    all_cases = group(results)
    by_scenario = {name: group([r for r in results if r['scenario'] == name])
                   for name, _ in SCENARIOS if any(r['scenario'] == name for r in results)}
    all_cases['by_scenario'] = by_scenario
    all_cases['all_scenario_tracking_met'] = all(
        g['pooled_rms_vx_vy_yaw'][0] <= .2 and g['pooled_rms_vx_vy_yaw'][1] <= .2
        and g['pooled_rms_vx_vy_yaw'][2] <= .25 for g in by_scenario.values())
    all_cases['single_policy_flat_thresholds_met'] = (
        len(results) >= 100 and all_cases['no_fall_fraction'] >= .99
        and all_cases['all_scenario_tracking_met'])
    all_cases['three_training_seed_acceptance_complete'] = False
    all_cases['confidence_note'] = 'Wilson interval is descriptive within this fixed case suite; physical-domain randomization and training-seed variability are not included.'
    return all_cases
