"""Identity checks for checkpoint exports and the pinned RL SAR reference actor."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ID = 'rl_sar'
TRAINED_PREFIXES = ('control|posture|lrcontrol|lrlow|stairfixed|stairadaptive|resetcontrol|'
                    'resetupright|scheduleadaptive|schedulefixed|microstandardorder|'
                    'microstandardbalanced|microconservativeorder|microconservativebalanced|'
                    'microcomposite|microcompositec77|microcompositec102|microcompositec150')
TRAINED_PREFIXES += '|microcompositerep150'
TRAINED_PREFIXES += '|microlateral150|microyaw150|microaxissplit150'
TRAINED_PREFIXES += '|microlateral300|microyaw300|microaxissplit300'
TRAINED_PREFIXES += '|microlateralcurve150|microlateralcurve152|microlateralcurve177'
TRAINED_PREFIXES += '|microlateralcurve202|microlateralcurve226|microlateralcurve252|microlateralcurve300'
TRAINED_PREFIXES += '|microaxismixed177y150'
TRAINED_PREFIXES += '|microyaw252'
TRAINED_PREFIXES += '|microaxismixed152y252'
TRAINED_PREFIXES += '|shortflight'
TRAINED_PATTERN = rf'(?:{TRAINED_PREFIXES})_\d+'


def policy_id(value):
    if str(value) == REFERENCE_ID:
        return REFERENCE_ID
    if re.fullmatch(TRAINED_PATTERN, str(value)):
        return str(value)
    return int(value)


def reference_identity():
    source = next(s for s in json.loads((ROOT/'vendor/manifest.json').read_text())['sources']
                  if s['name'] == REFERENCE_ID)
    name = 'policy/b2w/robot_lab/policy.pt'
    pinned = next(f for f in source['files'] if f['path'] == name)
    path = ROOT/'vendor/rl_sar'/name
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    blob = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
    if digest != pinned['sha256'] or blob != pinned['git_blob_sha1']:
        raise ValueError('Pinned RL SAR policy bytes changed')
    return {'policy_id': REFERENCE_ID, 'label': 'RL SAR · reference',
            'source_kind': 'upstream_torchscript', 'repository': source['repository'],
            'commit': source['commit'], 'source_path': path.relative_to(ROOT).as_posix(),
            'export_sha256': digest, 'git_blob_sha1': blob,
            'checkpoint_iteration': None, 'training_checkpoint_export_parity': False,
            'evaluation_adapter': 'Isaac Robot Lab observations, raw previous action and physical-target clipping; same as latest fullcycle test'}


def validate_export(policy, path, manifest):
    data = manifest.get('export_validation', manifest)
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != data['export_sha256']:
        raise ValueError('Export SHA does not match its manifest')
    if policy == REFERENCE_ID:
        expected = reference_identity()
        if any(data.get(key) != value for key, value in expected.items()):
            raise ValueError('RL SAR reference provenance mismatch')
    elif data.get('checkpoint_iteration') != (int(policy.rsplit('_', 1)[1])
            if isinstance(policy, str) and re.fullmatch(TRAINED_PATTERN, policy) else policy):
        raise ValueError('Policy ID does not match checkpoint iteration')
    return data
