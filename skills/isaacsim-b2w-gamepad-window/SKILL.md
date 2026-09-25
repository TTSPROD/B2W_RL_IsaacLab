---
name: isaacsim-b2w-gamepad-window
description: Select a trained B2W checkpoint and an Isaac Sim map, then launch and verify a visible Windows XInput gamepad session with training-relevant velocity limits. Simulator only.
---

# B2W gamepad — Isaac Sim

Find the active B2W_RL_IsaacLab checkout by `AGENTS.md` and `policies/manifest.json`;
never assume a username, drive or fixed checkout path. Read `AGENTS.md`,
`docs/GAMEPAD_VIEWERS.md` and `docs/ISAAC_GAMEPAD.md` from that root.
Use the project copy of this skill when it differs from the installed copy.
This workflow opens no DDS or real-robot connection.

## 1. Choose checkpoint

Use the requested path, run, iteration or SHA. For "latest/current", resolve
`active_candidate` in `policies/manifest.json`; currently it is server upstream19999.
Do not choose by file modification time or compare iteration numbers across runs.
If several distinct artifacts still match, clarify the selection. Do not run
upstream10000, as required by project instructions.

Both viewers consume the same validated TorchScript export. For 19999 reuse
`policies/server/upstream_19999/export/policy.pt` after checking its manifest's
checkpoint/export SHA. For another raw checkpoint, use the existing guarded exporter:

```powershell
$checkpoint = (Resolve-Path 'policies/server/SELECTED/checkpoint.pt').Path
$report = 'logs/gamepad_exports/UNIQUE_SELECTION/report.json'
& ./scripts/run_local.ps1 scripts/check_policy_contract.py --training-checkpoint $checkpoint --report $report
if ($LASTEXITCODE) { throw 'Export failed' }
$policy = (Resolve-Path (Join-Path (Split-Path $report) 'policy-contract-export/policy.pt')).Path
```

Replace the selection/example paths with the actual artifact and a new report
directory. Preserve the exporter guards and require semantic ABI 57→16, 12 leg
position + 4 wheel velocity targets, 50 Hz. Record both SHAs; shape alone is insufficient.

## 2. Choose map

Use the user's requested map; otherwise use `flat` and state that choice.

| Selection | Launcher arguments |
|---|---|
| Flat | `-Terrain flat` — locally generated plane |
| Ascending stairs | `-Terrain stair_up` — 6 steps, rise 0.14 m, run 0.32 m |
| Descending stairs | `-Terrain stair_down` — same geometry |
| One rough tile | `-Terrain rough -TerrainFamily random_rough -TerrainLevel 0..9 -Seed <seed>` |
| Large mixed map | `-Terrain map -Seed <seed>` — upstream 10×20 grid with flat apron |

Rough families: `pyramid_stairs`, `pyramid_stairs_inv`, `boxes`, `random_rough`,
`hf_pyramid_slope`, `hf_pyramid_slope_inv`. One rough tile represents the midpoint
of the selected level. The mixed map spans 80×160 m plus a 20 m border and increases
difficulty by row. These are generated maps, not saved training terrain state.
Arbitrary MuJoCo XML is not an Isaac map. Do not silently substitute a different
surface. The viewer draws the exact terrain mesh sent to Isaac physics.

## 3. Choose training-relevant commands

Read the selected run's `env.yaml`, `commands.base_velocity.ranges`; do not use
evaluation pass rates as training limits. For upstream19999 set **MaxForward=1.0,
MaxLateral=1.0, MaxYaw=1.0**: vx/vy ±1 m/s, yaw ±1 rad/s, independently per axis.
Use lower limits when requested. Do not silently retain the obsolete 0.7/0.4/0.5
preset, apply a vector-norm cap, or change the 50 Hz policy clock. Training range
does not imply successful tracking across that range.

## 4. Verify and launch

Use one explicit argument set for smoke and interactive launch. Example for current Flat:

```powershell
$policy = (Resolve-Path 'policies/server/upstream_19999/export/policy.pt').Path
$viewerArgs = @{ Terrain='flat'; Policy=$policy; GamepadIndex=0; MaxForward=1.0; MaxLateral=1.0; MaxYaw=1.0; Device='cpu' }
& ./scripts/run_isaac_gamepad.ps1 @viewerArgs -SmokeSteps 25
if ($LASTEXITCODE) { throw 'Isaac smoke failed' }
& ./scripts/run_isaac_gamepad.ps1 @viewerArgs -Fps 144
```

Select the connected XInput index 0–3. Bluetooth is valid if exposed through XInput.
The renderer is an external OpenGL window, with Isaac Sim physics in its own child
process. CPU physics/inference is the interactive default; physics stays 200 Hz
and actor 50 Hz. No old desktop executable or computer-use launcher is required.

For an agent-started persistent window, invoke the launcher through `Start-Process`
with `-WindowStyle Normal`, the project working directory and separate stdout/stderr
logs. Quote paths with spaces. Inspect `B2W <terrain> | Isaac Sim physics | OpenGL 3D`
when native tools are available. Otherwise confirm its window title/process,
`READY` model/terrain, `COMMAND_LIMITS`, gamepad connection and advancing telemetry;
disclose that no visual inspection was possible. PID or requested FPS alone is insufficient.
If the user cannot see a running viewer, account for sandbox desktop isolation:
launch the same command on the interactive desktop using the environment's execution
permission, verify visible/foreground window state, and close only the old session.
Check `logs/b2w_viewer_performance.jsonl` and physics `PERF` for measured FPS/policy Hz
and real-time factor; do not claim historical machine performance as current evidence.

## 5. Controls and completion

Hold **LB** to drive; left stick controls vx/vy, right stick yaw. Releasing LB,
**B**, or disconnect requests zero. After B/reconnect release LB once to re-arm.
**A** resets; drag/wheel control the camera, **M** toggles map overview, Esc closes.
Zero is a command, not guaranteed instant physical braking. The upstream environment
may reset after a termination; this viewer does not implement MuJoCo safety qualification.

Report selected checkpoint, map, actual limits and connection/window status.
Physics logs: `logs/play_b2w_gamepad_opengl.log`; performance: `logs/b2w_viewer_performance.jsonl`.
This is manual inspection, not qualification. Closing the viewer must stop only its
own simulator child; retain cleanup in `Viewer.close()` for the Esc path. On restart
never stop unrelated Python processes or the other simulator.
