---
name: isaacsim-b2w-gamepad-window
description: Launch a selected B2W policy in a visible, smooth OpenGL window with Isaac Sim physics and a USB or Bluetooth XInput gamepad on Windows. Supports flat, rough, stairs and a large mixed map; includes FPS and simulation-speed checks. For local simulated driving, not robot actuation.
---

# B2W policy viewer with gamepad

Work only in `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`. Read `AGENTS.md`, `docs/PROJECT_PLAN.md`, `docs/INFRASTRUCTURE.md`, and `docs/GUI_GAMEPAD.md` before launching or editing. Do not inspect or stop other B2W projects or jobs. This skill never authorizes commands to a real robot.

## Select what the user requested

Resolve the exact requested policy from its path, run name, or the current reports in `docs/results/`. Check that the artifact exists. Use `--checkpoint` for an RSL-RL `model_*.pt` file and `--policy` for an exported TorchScript actor. Do not substitute a fixed flat policy, a newer checkpoint, or a different seed without saying so. If the request leaves several plausible variants, ask which one before launching.

Choose the scene that corresponds to the policy and the user's requested inspection:

- `--terrain flat`: plane physics and plane drawing.
- `--terrain rough`: upstream B2W rough task. Choose an upstream `--terrain-family` (`pyramid_stairs`, `pyramid_stairs_inv`, `boxes`, `random_rough`, `hf_pyramid_slope`, or `hf_pyramid_slope_inv`), `--terrain-level` 0–9, and mesh `--seed`. One 8 m tile is generated at the midpoint difficulty of that level; it is a representative scene, not a replay of a full 10×20 training grid.
- `--terrain stair`: rough task with the project stair-flight geometry. Set `--stair-direction up|down`, `--stair-rise`, `--stair-run`, and `--stair-steps` to the requested or reported test geometry.
- `--terrain map`: use for a large shared/mixed map. All six upstream terrain families on a 10×20 grid, 80×160 m plus a 20 m flat border. Difficulty increases along the rows; spawn is on the flat apron facing the easiest row. Use `--seed` for reproducibility. This is generated geometry, not the saved terrain state of the checkpoint's training run.

The viewer draws geometry from the exact mesh imported into Isaac Sim physics. Follow view culls distant terrain chunks from drawing; collision geometry remains complete. The actor observation and action contract must be 57→16; the simulator checks this before `READY`. A raw checkpoint is loaded with the same actor architecture as the project evaluator. A matching scene is necessary for visual inspection, but a viewer run is not a held-out policy evaluation.

## Smooth playback preset

For this Windows single-robot viewer, use `--device cpu --fps 144` (the viewer defaults). CPU PhysX and actor inference avoid the overhead of many tiny GPU operations; OpenGL rendering stays on the NVIDIA GPU. This choice applies to interactive playback, not training or batch evaluation. Keep physics dt 0.005 s and policy dt 0.02 s: 200 Hz physics, 50 Hz policy. Do not change these rates or increase gamepad command magnitudes just to compensate for slow wall-clock simulation.

The working renderer caches robot links and terrain chunks on the GPU, reuses HUD labels, disables VSync, and interpolates visual poses with one policy tick of delay. A 144 FPS render loop does not mean a 144 Hz policy. The viewer supports `--device cuda:0` for explicit comparison.

Measured on 2026-09-23 with RTX 4080 Laptop, upstream 18100 and the full map: 142–144 FPS, policy about 50 Hz, real-time factor about 1.00. Before optimization the observed values were 23 FPS and policy 20 Hz (~0.40× speed). These are measurements from that session, not a guaranteed minimum on every scene or machine, nor a CPU/GPU parity evaluation.

## Launch

Connect XInput controller 0; Bluetooth works when Windows exposes the controller through XInput. Check connection rather than assuming a USB cable is needed. Build the project-local desktop launcher with `scripts/build_b2w_viewer_launcher.ps1`. From the project root, set `$modelPath` to the selected **absolute** artifact path, `$modelFlag` to `--checkpoint` or `--policy`, and `$sceneArgs` to the requested terrain arguments. Example for the large map; write one literal argument per line:

```powershell
$root = (Resolve-Path '.').Path
$modelPath = '<absolute path of the requested model>'
$modelFlag = '--checkpoint'  # or --policy for a TorchScript export
$sceneArgs = @('--terrain', 'map', '--seed', '2002', '--device', 'cpu', '--fps', '144')
if (-not (Test-Path -LiteralPath $modelPath)) { throw "Model missing: $modelPath" }
@('scripts/view_b2w_gamepad_3d.py', $modelFlag, $modelPath) + $sceneArgs |
  Set-Content -LiteralPath (Join-Path $root '.cache\b2w-viewer-args.txt') -Encoding utf8
& pwsh -NoProfile -File (Join-Path $root 'scripts\build_b2w_viewer_launcher.ps1')
```

When specifically requested, the verified upstream 18100 artifact is `artifacts/upstream/2026-09-23_model_18100/upstream_model_18100.pt` under the project root, SHA-256 `cc3ff9a993d18979c8874005565ebfc7503fc7b529e80e4eb64556912dadddf7`. It is an example selection, not a replacement for another requested model.

Launch `.cache/B2WViewerLauncher.exe` using the `computer-use` skill's `sky.launch_app` on the interactive desktop. A shell `Start-Process` can run Isaac physics while creating no window visible to the user; do not infer visibility from a running process or `STEP=` log. After launch, use `sky.list_windows()` to select the unique `B2W <terrain> | Isaac Sim physics | OpenGL 3D` window, activate it, and capture its state to confirm that the robot and matching terrain are visible. If the launcher reports no targetable window, still check `sky.list_windows()` for the child viewer and inspect `.cache/b2w-viewer-launcher.log` plus `.cache/b2w-viewer-interactive-stderr.log`.

The viewer picks a free local UDP port and launches `scripts/play_b2w_gamepad.py` through `scripts/run_local.ps1`. Check `logs/play_b2w_gamepad_opengl.log` for `READY` naming the selected model and terrain, `GAMEPAD: XInput controller 0 connected`, `TERRAIN_MESH=` for rough/stair/map, and advancing `STEP=` lines.

After warm-up, check several samples in `logs/b2w_viewer_performance.jsonl` and the simulator's `PERF` lines: actual FPS, policy Hz, real-time factor, and compute time. For the requested 100+ FPS experience, verify measured FPS ≥100 and real-time factor near 1.00; do not claim success from `--fps` alone. The HUD should show those values and gamepad commands should change while the robot moves. Diagnose render FPS and simulation speed separately. If the target is missed, report the measured limit rather than silently speeding up the policy clock.

For a restart, close only this project's viewer and verify its own simulator children exited before launching another instance. A PID in `.cache/b2w-viewer-launcher.log` can be stale: check the current process and log timestamp. Never stop all Python processes. Cleanup must live in `Viewer.close()` because calling `Window.close()` directly (such as Escape) can bypass `on_close`; preserve this invariant when editing the viewer.

Left stick drives forward/back and sideways; right stick turns. A resets to the start. M toggles map overview/follow in map mode. Drag the mouse to orbit; use the wheel to zoom. Esc or closing the window stops its own simulator child. Upstream 18100 was trained with commands ±1 m/s and ±1 rad/s; at 0.40× simulation speed even full stick appears slow. This is an external OpenGL viewport linked to Isaac Sim physics, not Kit's built-in viewport or an RTX renderer.
