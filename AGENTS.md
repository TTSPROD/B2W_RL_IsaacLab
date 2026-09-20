Отвечай достаточно коротко без лишней воды.

## Project boundaries
- Policy actor ABI must remain 57 observations -> 16 actions, exactly compatible with the reference. Do not expand actor inputs or train a 247-input teacher under the current plan; privileged critic observations do not change this actor contract.
- This repository is a new B2W project. Never inspect, reuse, modify, stop or remove previous B2W projects or their jobs on the server.
- Remote project directory is `/home/user/projects/B2W_RL_IsaacLab`; transfer bundles use only `/home/user/.cache/B2W_RL_IsaacLab-sync`. Keep writes inside these two dedicated paths; do not change shared drivers, global packages or other workloads.
- Read `docs/PROJECT_PLAN.md` and `docs/INFRASTRUCTURE.md` before training work. Local Windows headless Flat on RTX 4070 Ti has passed GPU smoke and throughput qualification, including two concurrent 4096-env runs. Server, rough/stairs, GUI and real-robot gates remain separate; consult dated results rather than inferring policy acceptance.
- Treat `vendor/` as immutable upstream snapshots. Record upstream commits, file hashes and licenses in `vendor/manifest.json`; implement adaptations outside vendor.
- Use `skills/github-dns-bypass/SKILL.md` when GitHub DNS fails. Preserve TLS verification and existing authorization; never force push as a DNS workaround.
- No live robot actuation is authorized by repository setup or simulator testing. Follow the staged deployment gates in the project plan.
- Do not describe a downloaded checkpoint, an unexecuted command or a planned experiment as a successfully trained/tested policy.
