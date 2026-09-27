#!/bin/bash
set -uo pipefail
export OMNI_KIT_ACCEPT_EULA=Y
python -m torch.distributed.run --standalone --nnodes=1 --nproc_per_node=4 /run-output/runtime_bootstrap.py --task RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0 --headless --distributed --num_envs 1024 --max_iterations 19899 --run_name upstream_resume_4gpu --resume --load_run '^resume_parent$' --checkpoint '^model_100[.]pt$' '--kit_args=--ext-folder=/cache/exts --/app/extensions/registryEnabled=false --/app/settings/persistent=false --/app/userConfigPath=/project-tmp/home/user.config.json' env.commands.base_velocity.debug_vis=false > /run-output/console.log 2>&1
result=$?
echo "$result" > /run-output/exit_code.txt
exit "$result"
