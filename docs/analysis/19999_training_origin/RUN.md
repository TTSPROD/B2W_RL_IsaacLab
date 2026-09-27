# Main upstream B2W continuation on four GPUs
Authorized by user on 2026-09-22 after successful 4-GPU throughput test.
Container: upstream_b2w_20000_4gpu_20260922, detached, GPUs 0–3.
Task: RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0.
1024 environments/rank, 4096 total; upstream distributed PPO, rank seeds 42–45.
Parent: this session's model_100.pt from the original scratch run, SHA256
9d421439b4e85ca3a37ea64436ceaae3f0c2261c9f33134d5f0096482fe921d0.
No historical project checkpoints or benchmark checkpoints were used.
All four ranks verified exact model and optimizer tensor restoration (17 Adam states).
Restored optimizer and algorithm adaptive LR: 0.0005766503906250003.
Next iteration index: 101; 19899 additional updates; total target 20000,
final expected checkpoint model_19999.pt. Checkpoints every 100 iterations.
The external resume adapter advances the saved post-update index and restores
algorithm.learning_rate from optimizer param_groups; upstream vendor is unchanged.
Physics environments/curriculum and random streams are restarted; this is parameter/
optimizer continuation, not exact trajectory continuation of the single-GPU run.
Runtime URDF compatibility and disabled command debug visualization are as before.
Actual iterations 101–103 were verified, about 6.2–6.4 seconds/update after startup.
Original single-GPU run remains stopped. Existing unrelated workloads were not stopped.
Resume proofs: resume_rank0.json through resume_rank3.json.
