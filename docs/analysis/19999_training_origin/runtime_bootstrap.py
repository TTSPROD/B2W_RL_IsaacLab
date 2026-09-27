import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
from isaaclab.app import AppLauncher
from isaac_compat import apply_pinned_urdf_importer_compatibility
original_init = AppLauncher.__init__
def initialize(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    print('[RUNTIME] URDF importer compatibility:', apply_pinned_urdf_importer_compatibility(), flush=True)
    import torch
    from rsl_rl.runners import OnPolicyRunner
    original_load = OnPolicyRunner.load
    def audited_load(runner, path, load_optimizer=True, map_location=None):
        expected = '9d421439b4e85ca3a37ea64436ceaae3f0c2261c9f33134d5f0096482fe921d0'
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert digest == expected, 'Unexpected parent checkpoint'
        assert load_optimizer, 'Optimizer restore required'
        parent = torch.load(path, weights_only=False, map_location='cpu')
        result = original_load(runner, path, load_optimizer=True, map_location=runner.device)
        assert runner.current_learning_iteration == parent['iter'] == 100
        for key, value in runner.alg.policy.state_dict().items():
            assert torch.equal(value.detach().cpu(), parent['model_state_dict'][key]), key
        actual = runner.alg.optimizer.state_dict()
        expected_opt = parent['optimizer_state_dict']
        assert len(actual['state']) == len(expected_opt['state']) == 17
        for key, state in expected_opt['state'].items():
            for field, value in state.items():
                restored = actual['state'][key][field]
                if torch.is_tensor(value):
                    assert torch.equal(restored.detach().cpu(), value), (key, field)
                else:
                    assert restored == value, (key, field)
        rates = [group['lr'] for group in runner.alg.optimizer.param_groups]
        assert rates == [group['lr'] for group in expected_opt['param_groups']]
        # RSL-RL saves the index AFTER that update; continue with the next index.
        runner.current_learning_iteration = parent['iter'] + 1
        # Restore the adaptive scheduler's scalar as well as optimizer param_groups.
        assert len(set(rates)) == 1
        runner.alg.learning_rate = rates[0]
        proof = dict(rank=int(os.environ.get('RANK',0)), parent_sha256=digest,
                     saved_iteration=100, next_iteration=101, additional_iterations=19899,
                     total_target_updates=20000, model_equal=True, optimizer_equal=True,
                     optimizer_state_count=17, learning_rate=runner.alg.learning_rate,
                     device=str(runner.device))
        Path(f"/run-output/resume_rank{proof['rank']}.json").write_text(json.dumps(proof,indent=2)+'\n')
        print('[RESUME AUDIT]', json.dumps(proof), flush=True)
        return result
    OnPolicyRunner.load = audited_load
AppLauncher.__init__ = initialize
script = '/vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py'
sys.path.insert(0, '/vendor/robot_lab/scripts/reinforcement_learning/rsl_rl')
sys.argv[0] = script
runpy.run_path(script, run_name='__main__')
