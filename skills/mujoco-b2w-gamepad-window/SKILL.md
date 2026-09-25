---
name: mujoco-b2w-gamepad-window
description: Select a trained B2W checkpoint and a MuJoCo map, then launch and verify a visible Windows XInput gamepad session with training-relevant velocity limits. Simulator only.
---

# B2W gamepad — MuJoCo

Find the active B2W_RL_IsaacLab checkout by `AGENTS.md` and `policies/manifest.json`;
never assume a username, drive or fixed checkout path. Read `AGENTS.md`,
`docs/GAMEPAD_VIEWERS.md` and `docs/MUJOCO_GAMEPAD.md` from that root.
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
| Flat | `-Terrain flat` |
| Ascending stairs | `-Terrain stair_up` — 6 steps, rise 0.14 m, run 0.32 m |
| Descending stairs | `-Terrain stair_down` — same geometry |
| Custom/rough/mixed map | `-Terrain scene -Xml <absolute complete B2W XML>` |

There is no built-in `rough` or `map` generator in this viewer. Do not silently
substitute a plane for a requested custom map. A custom scene must preserve
`base_link`, the 16-actuator/32 joint-sensor order, `nq=23,nv=22,nu=16`, and a
physics timestep dividing 0.02 s. Ground is `floor`, extra map collisions use
`terrain_` names. Spawn is `(0,0,0.65)`; provide a compatible clear starting area.
Compose derived scenes outside immutable vendor if necessary.

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
$viewerArgs = @{ Terrain='flat'; Policy=$policy; GamepadIndex=0; MaxForward=1.0; MaxLateral=1.0; MaxYaw=1.0 }
& ./scripts/run_mujoco_gamepad.ps1 @viewerArgs -SmokeSteps 25 -Log logs/mujoco_gamepad/smoke.jsonl
if ($LASTEXITCODE) { throw 'MuJoCo smoke failed' }
& ./scripts/run_mujoco_gamepad.ps1 @viewerArgs
```

Select the connected XInput index 0–3. Bluetooth is valid if exposed through XInput.
For an agent-started persistent window, invoke that launcher through `Start-Process`
with `-WindowStyle Normal`, the project working directory and separate stdout/stderr
logs. Quote paths with spaces. Never hide the requested viewer. Inspect the visible
window when native tools are available; otherwise confirm its title/process,
`session_start` SHA/command_limits, connected gamepad and advancing telemetry,
and disclose that no visual inspection was possible. Do not infer visibility from PID alone.
If the user cannot see a running viewer, account for sandbox desktop isolation:
launch the same command on the interactive desktop using the environment's execution
permission, verify visible/foreground window state, and close only the old session.

## 5. Controls and completion

Hold **LB** to drive; left stick controls vx/vy, right stick yaw. Releasing LB,
**B**, or disconnect requests zero. After B/reconnect release LB once to re-arm.
**A** resets, **X** toggles camera, Esc closes. Zero is a command, not guaranteed
instant physical braking. Physics safety events may reset the manual simulator.

Report selected checkpoint, map, actual limits and connection/window status.
Logs and command traces stay in `logs/mujoco_gamepad/`, outside Git. This is manual
inspection, not qualification. On restart close only the identified session;
never stop unrelated Python processes or the other simulator.
