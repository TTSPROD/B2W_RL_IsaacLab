# Cycle57 model3000: multi-seed MuJoCo sim2sim

Дата: **25 сентября 2026**. Решение: **diagnostic gate failed; policy не
повышается и к SDK2/sim2real не допускается**.

## Что проверялось

Проверена неизменённая политика без дополнительного груза:

- checkpoint `cycle57 A model_3000.pt`, SHA-256
  `20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`;
- TorchScript export 57 observations → 16 actions, SHA-256
  `2af4c3417216211b12ee01e5088ace421df07872cd0922fcdc5bd1655c2a36c7`;
- vendor B2W MuJoCo XML, SHA-256
  `171d4bc592e1e3eaf15179bcdf0ab5aa1fba3fb0d157fe3bfb285ba0a0316908`;
- physics/policy rates 500/50 Hz, deterministic actor, без hold adapter;
- внешний corridor yaw-controller применялся только на лестницах и не менял
  actor ABI;
- 20 фиксированных seeds `6101…6120`, одинаковые стартовые возмущения во всех
  группах: lateral ±0.10 m, yaw ±0.08 rad, leg position ±0.02 rad, leg velocity
  ±0.05 rad/s, wheel velocity ±0.20 rad/s.

До запуска был заморожен протокол
`configs/cycle57_mujoco_multiseed_v1.json`, SHA-256
`72ee7c043219a8612a0fa67aba7837298bcd41445645641819dc9de321c7b39d`.
Он требует не менее 19/20 успешных эпизодов в каждой группе, zero unsafe,
wheel-torque saturation fraction ≤0.05 и stair lateral drift ≤0.50 m. Это
диагностический gate, а не разрешение promotion.

## Результат 200 эпизодов

| Группа | Пройдено | Unsafe | Wilson 95% для success | Wheel saturation p95 / max | Lateral max |
|---|---:|---:|---:|---:|---:|
| Stand | 20/20 | 0 | 0.839–1.000 | 0.000 / 0.000 | 0.023 m |
| Forward 0.5 | 20/20 | 0 | 0.839–1.000 | 0.000 / 0.000 | 0.241 m |
| Yaw +0.5 | 20/20 | 0 | 0.839–1.000 | 0.001 / 0.001 | 0.151 m |
| Yaw −0.5 | 20/20 | 0 | 0.839–1.000 | 0.001 / 0.002 | 0.306 m |
| Nominal up 14/32 cm | **9/20** | **11** | 0.258–0.658 | **0.227 / 0.260** | 0.332 m |
| Nominal down 14/32 cm | 20/20 | 0 | 0.839–1.000 | 0.012 / 0.013 | 0.156 m |
| Steep up 16/29 cm | **5/20** | **15** | 0.112–0.469 | **0.230 / 0.238** | 0.301 m |
| Steep down 16/29 cm | 20/20 | 0 | 0.839–1.000 | 0.013 / 0.014 | 0.125 m |
| Shallow up 12/38 cm | **9/20** | **11** | 0.258–0.658 | **0.298 / 0.298** | 0.377 m |
| Shallow down 12/38 cm | 20/20 | 0 | 0.839–1.000 | 0.011 / 0.011 | 0.179 m |

Flat дал 80/80, все спуски — 60/60. Подъёмы дали только 23/60 (38.3%) и
все 37 unsafe-эпизодов. Lateral gate прошёл во всех группах, но success,
zero-unsafe и wheel-saturation gates на подъёмах провалены.

## Safety attribution

Safety измерялась на каждом physics step, а не только на частоте политики.
Из 37 аварийных остановок:

- 35 — превышение joint velocity limit 14 rad/s: `RL_calf_joint` 20,
  `FL_calf_joint` 6, `FR_calf_joint` 5, `RR_calf_joint` 4;
- превышения были небольшими по амплитуде, но систематическими: utilization
  1.0002–1.0120, среднее 1.0045, во времени 4.334–5.924 s;
- 2 — выход `RL_calf_joint` за position range на steep-up seeds 6105 и 6110:
  margin −0.0123 и −0.0132 rad около 4.79 s;
- падений и запрещённых контактов в этих автоматических прогонах не было.

Даже среди 23 завершённых подъёмов максимальная доля wheel torque saturation
составила 0.186, то есть существенно выше gate 0.05. Максимальная скорость в
финальном hold была 0.039 m/s, поэтому основной MuJoCo-блокер здесь — не поздняя
остановка, а динамика подъёма, calf limits и насыщение колёс.

## Воспроизводимость и ограничения

Итоговый JSON:
`logs/sim2sim/cycle57_model3000_multiseed_v1/report.json`, SHA-256
`112d0437405a59543fa173eafdbecf233da7c37c617743491c3c12553046b614`.
Evaluator hashes: single-run
`04803a410287b6ba8285bf4328df3fe4abe57a247a83636c03fbbc41599cdb7e`,
multi-seed
`9e80d21bfa4cd165a6c37269746550d166c6d51092ac6194eef18dc05f696c83`.

Первый orchestration attempt корректно завершил flat 80/80, но остановился до
лестниц из-за неверной классификации имени custom stair scenario. Этот запуск не
использовался как результат. После regression test полный набор 200 эпизодов был
выполнен целиком; затем тот же frozen suite повторён после добавления только
диагностических полей отчёта. Итоговые counts воспроизвелись точно.

MuJoCo source mass больше training URDF source mass на 4.750435 kg; calf
ctrlrange составляет ±300 Nm против nominal Isaac ±320 Nm. Также различаются
passive damping/contact solver. Реальные torque-speed curves, current/thermal
limits, latency, estimator noise и знаки приводов ещё не измерены. Поэтому этот
тест диагностирует transfer gap, но не доказывает поведение физического робота.

## Решение и следующий шаг

`model_3000.pt` остаётся research-only parent. SDK2 replay/dry-run и любые
испытания робота не открываются. Следующий single-factor этап — не новый PPO run,
а actuator/physics parity: сверить mass/COM/inertia, calf joint limits,
torque-speed curve, damping, contact/friction и измеряемый current/thermal
envelope. После фиксации эталонной модели повторяется **тот же** frozen 200-episode
suite. Только если transfer gap устранён и gate пройден, имеет смысл проектировать
следующий training run против directional ascent interference.
