# Independent balanced-specialist repeat

Job `3499b81d1d99477bb90c3b3ca5dcc162` завершён 07.10.2026 с exit 0.
Balanced specialist обучен заново от неизменённого `core_24650`, seed 9913,
150 PPO updates, 512 envs, 1 843 200 transitions. Checkpoint seed 9912 не
загружался. Использованы pinned Robot Lab `train.py`, стандартные
OnPolicyRunner/PPO, fixed LR 1e-5, 5 epochs × 4 minibatches.

Final checkpoint iteration 24799, 3000 Adam updates/parameter, finite state,
export parity и command-gated branch parity на 1024 observations проверены.

## Frozen 60-episode repeat gate

| Метрика | Parent 24650 | Repeat composite-150 | Δ |
|---|---:|---:|---:|
| Success | 27/60 | 27/60 | 0 |
| Unsafe | 0 | 0 | 0 |
| Paired wins/losses | — | 0/0 | — |
| Lateral response | 0.6831 | 0.6625 | −0.0206 |
| Yaw response | 0.6666 | 0.6984 | +0.0318 |
| Max wheel saturation | 0.1275 | 0.1275 | 0 |
| Max leg saturation | 0.0074 | 0.0074 | 0 |

Все binary outcomes/cells совпали, однако lateral response вышел ниже
предварительно замороженного parent tolerance. Probe gate не пройден;
conditional full screen не запускался. Положительный результат seed 9912
`107/160→109/160` не воспроизведён независимой training trajectory.

## Решение

- Не продлевать общий lateral+yaw specialist и не продвигать composite-150.
- `core_24650` остаётся development candidate.
- Следующий измеренный фактор — разделить lateral-only и yaw-only specialists:
  seed 9913 улучшил yaw одновременно с ухудшением lateral, что согласуется
  с ранее измеренным gradient conflict между command phases.
- До нового обучения заморозить budgets и axis-specific sampling; проверить
  каждый specialist только на своей pure-axis ветви, оставив остальные команды
  побитово на parent.
- Full validation, sim2sim acceptance и hardware не запускать по этому actor.

Raw evidence:

- result SHA-256 `5444797352c41211223c24312f60c896b7ae06930e83d6a43c59f63d885c4c99`;
- repeat composite export SHA-256
  `74e2f152b97649e6ddc9d87ff67f9e228024f1f46becfdf83ac517bfaf735127`;
- checkpoint SHA-256
  `2bb33e0078a41dcc2f8e3bb64868756934462380b08952f23d380d53ed600f24`.
