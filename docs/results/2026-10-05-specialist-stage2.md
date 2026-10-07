# Balanced specialist stage 2

Job `ade3807809c94923878b53a669e6d8a2` завершён 05.10.2026 с exit 0.
От checkpoint standard/balanced cumulative +25 выполнено ещё 125 PPO updates
на 512 envs, seed 9912: 1 536 000 новых transitions. Использован неизменённый
pinned Robot Lab `train.py`, стандартные OnPolicyRunner/PPO, fixed LR 1e-5,
5 epochs × 4 minibatches. Runner/Adam/checkpoint iterations проверены.

Из одного непрерывного run выбраны фактически доступные checkpoints около
заранее заданных бюджетов: cumulative +77, +102 и +150. Для каждого собран
command-gated TorchScript `57→16`: specialist обслуживает только чистые lateral/yaw,
parent 24650 — zero, longitudinal и mixed commands. Каждый export прошёл exact
branch parity на 1024 observations с max error 0.0.

## 60-episode selection probe

| Composite | Success | Unsafe | Wins/losses vs parent | Lateral response | Yaw response |
|---|---:|---:|---:|---:|---:|
| parent 24650 | 27/60 | 0 | — | 0.6831 | 0.6666 |
| cumulative 77 | 27/60 | 0 | 0/0 | 0.6735 | 0.6895 |
| cumulative 102 | 27/60 | 0 | 0/0 | 0.6859 | 0.6797 |
| cumulative 150 | **28/60** | 0 | **1/0** | 0.6885 | 0.6838 |

Cumulative-150 впервые дал рост дискретного success: один новый успешный slot
`flat_mu_100/lateral`, без потери parent success slots, без unsafe и без изменения
max saturation. По frozen правилу только он допущен к full screen.

## Полный matched screen

Parent и composite-150 проверены по v2 в 320 fresh episodes суммарно:
8 terrain variants, 32 cells, одинаковые case/reset slots, один actor на процесс.

| Метрика | 24650 | Composite-150 | Δ |
|---|---:|---:|---:|
| Success | 107/160 | **109/160** | **+2** |
| Unsafe | 0 | 0 | 0 |
| Tracking checks | 60/100 | **62/100** | +2 |
| Transition checks | 97/100 | **98/100** | +1 |
| Stop checks | 148/160 | 147/160 | −1 |
| Traversal checks | 48/60 | 48/60 | 0 |
| Max leg saturation | 0.0074 | 0.0074 | 0 |
| Max wheel saturation | 0.1382 | 0.1382 | 0 |

Paired outcomes: **2 wins / 0 losses / 158 ties**. Новые successes:

- `flat_mu_100/lateral`, seed 73002;
- `rough_02/lateral`, seed 73004.

В `rough_10/lateral` success остался 0/5: transition checks улучшились 3→4,
но stop checks снизились 5→4. Mixed cells, longitudinal и все stair success
не изменились. Общий full-screen gate и all-cells gate не пройдены;
`microcompositec150_24798` — **положительный finalist**, но не принятая policy.
`core_24650` остаётся development candidate до независимого training-seed repeat.

Следующий необходимый шаг перед любым решением о candidate replacement — повторить
balanced specialist с нуля от 24650 на seed 9913 до cumulative 150 и применить
тот же заранее замороженный 60-episode probe/full-screen gate. Не подбирать новый
checkpoint по validation и не запускать hardware.

Raw evidence:

- result: `logs/dashboard/jobs/ade3807809c94923878b53a669e6d8a2/result.json`,
  SHA-256 `9ab34515fc9578e654f415944338bfd24a0925ddebf4863bfaeb281ea1e36ee5`;
- full-screen summary SHA-256
  `219ec354508463bda90cb8e27b8b50ff53ba15114c9dfbfd058317a6ed795316`;
- composite-150 export SHA-256
  `e22462d8f45ddfe437a8de369c3295923ad0c86c07193ed7903af08f313d7e5d`;
- specialist checkpoint SHA-256
  `f87a1b1ad55b7fb73359c7b4833d0cda7b0f521e4aab337b2713064088180314`.
