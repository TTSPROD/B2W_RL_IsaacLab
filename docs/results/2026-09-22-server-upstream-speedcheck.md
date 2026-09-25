# Server upstream B2W speed check — 2026-09-22

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

User explicitly authorized the exception recorded in AGENTS.md. The running
`upstream_b2w_20000_20260922` container on GPU 2 was not stopped or modified.

Three fresh runs of the upstream B2W Rough task completed on GPU 0, each with
10 PPO iterations, seed 42, horizon 24, no resume and no old checkpoints.
All exited successfully. Measurements below average iterations 5–9, excluding
the first five iterations. These are short throughput tests, not policy-quality
evaluations or measurements of time to a trained policy.

| Variant | Environments | Seconds/iteration | Transitions/second |
|---|---:|---:|---:|
| Baseline | 4096 | 12.1148 | 8114 |
| CPU affinity and 8 threads | 4096 | 11.9334 | 8238 |
| CPU affinity and 8 threads | 2048 | 7.9602 | 6175 |

CPU tuning used taskset CPUs 0–7 (local to GPU 0), OMP/MKL/OpenBLAS/PXR
thread limits of 8, and Kit/TBB limits of 8. The combined change improved
measured throughput by only 1.5%; without repeats this is not strong evidence
of a useful improvement. Halving environments reduced iteration time but also
halved samples per iteration and lowered sample throughput by about 24%.
At equal sample count it would take about 31% longer than baseline.

All variants used unchanged upstream train.py and B2W PPO/reward settings,
with the same documented URDF 2.4.30 runtime compatibility adapter, offline
extension cache, and disabled command debug visualization as the main run.
The headless environment loop already skips rendering without GUI/RTX sensors.
No distributed or RTX-machine benchmark was performed; their gains remain
unmeasured. No multi-GPU speedup is claimed.

Evidence on user@10.126.161.7:
`/home/user/B2W_RL_IsaacLab_Server/logs/upstream_speedcheck_20260922/`
contains benchmark.sh, per-variant console logs, resolved parameters, exit codes,
and results.json. The benchmark container finished with exit code 0.
Main training remained running, with a fresh model_100.pt verified.

Recommendation: retain the current run. These measurements do not justify
restarting it to change CPU settings or reduce environment count. Baseline
20,000-iteration wall-time extrapolation is approximately 67 hours, conditional
on sustained throughput; quality and completion remain unverified.

## Follow-up: two GPUs

At the user's explicit request, a fresh upstream distributed PPO run completed
10 iterations on GPUs 0 and 1 with 2048 environments per rank (4096 total).
The existing training run on GPU 2 remained running and unmodified.
The same runtime adapter and headless settings were used with torchrun,
two processes, and upstream --distributed. The single-GPU container entrypoint
was replaced with a benchmark-specific shell launcher; no image or vendor
files were modified. Rank parameter synchronization appeared in the log.

Iterations 5–9 averaged 8.122 seconds (range 8.033–8.202), or 12103 transitions/s.
This is 1.49x throughput versus the earlier single-GPU baseline, with the same
total rollout size. A 20,000-iteration extrapolation is about 45.1 hours versus
67.3 hours. This short test does not establish long-run stability, identical
optimization trajectories, or policy quality. GPU-hours would increase.

The benchmark exited with code 0 and released GPU memory. Evidence:
`/home/user/B2W_RL_IsaacLab_Server/logs/upstream_speedcheck_2gpu_20260922/`
contains benchmark.sh, console.log, exit_code.txt, results.json, and configs.
Migrating the main run was not performed or authorized by this benchmark request.

## Follow-up: four GPUs and explicit stop of main training

The user requested a four-GPU test while retaining existing workloads, then
explicitly authorized stopping our main training run. Only container
upstream_b2w_20000_20260922 was stopped (reported exit 134); its latest retained
checkpoint is model_100.pt. Main training has not been resumed. Other existing
workloads were not stopped or modified.

Fresh distributed PPO on GPUs 0–3, 1024 environments per rank (4096 total),
completed all 10 iterations with exit code 0. Initial iterations contended
with the main run and had high synchronization costs; they are excluded.
Iterations 5–9, after main training was stopped, averaged 6.2346 seconds:
5.8376 collection and 0.397 learning, or 15767 transitions/s.
This is 1.94x the single-GPU baseline and 1.30x the two-GPU test. Extrapolated
20,000-iteration time is 34.64 hours, not a long-run guarantee.

During the test GPUs 1 and 3 retained 6591 MiB (about 6.44 GiB) free in a
sampled measurement; no OOM occurred. Snapshots are not guaranteed memory peaks.
The test exited and released its memory. Evidence and results.json:
`/home/user/B2W_RL_IsaacLab_Server/logs/upstream_speedcheck_4gpu_20260922/`.
No full-length four-GPU training or checkpoint migration has been launched.

## Subsequent user-authorized main continuation

The user subsequently requested launching on four GPUs. Container
upstream_b2w_20000_4gpu_20260922 now runs detached, with 1024 environments per
rank and 4096 total. It resumes only this session's original model_100.pt,
SHA256 9d421439b4e85ca3a37ea64436ceaae3f0c2261c9f33134d5f0096482fe921d0.
All four ranks passed exact model/Adam tensor checks (17 optimizer states).
The external runtime adapter restores algorithm.learning_rate to the checkpoint's
optimizer LR (0.0005766503906250003) and advances the saved post-update index
100 to 101. With 19899 further updates, the intended final index is 19999.
Vendor source remains unmodified. Environment/curriculum and RNG trajectories
are restarted; this is parameter and optimizer continuation.

Actual iterations 101–103 were verified, roughly 6.2–6.4 seconds per update
after startup. The original one-GPU run remains stopped. Completion and policy
quality are not yet verified. Server evidence, per-rank resume proofs and RUN.md:
`/home/user/B2W_RL_IsaacLab_Server/logs/upstream_b2w_20000_4gpu_20260922/`.
