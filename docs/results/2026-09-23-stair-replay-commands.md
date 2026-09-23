# Stair experiment: исходные команды в replay-средах

23 сентября 2026. Эксперимент использует rough seed 55 `model_349.pt`, SHA-256 `765fe2a4cd1438ca3e81c387be570473c5dd3f9db656c4f064ec7a903dd802ed`, как исследовательский parent. Закрытая rough-оценка не приняла его окончательно: см. `2026-09-23-rough-final-selection.md`.

## Гипотеза и протокол

Предыдущий stair trainer применял один профиль `vx=0.7 → brake → stop → restart` ко всем средам, включая 15% flat и 15% rough replay. Гипотеза: это стирает широкое управление `vx/vy/yaw/stand`. Новый вариант меняет только семантику replay-сред:

- flat/rough replay получает исходное распределение `vx/vy/yaw ∈ [-1, 1]`, threshold малой линейной команды и 2% stand;
- команда пересэмплируется каждые 10 с, как в rough baseline;
- stair goal, stop/restart и stair curriculum не применяются к replay-средам; для них используется исходный distance/command terrain curriculum;
- stair-среды сохраняют protocol v3, brake 1.2 м, actor 57→16, rewards, terrain mix и PPO без изменений.

Контроль сохраняет прежнюю общую stair-команду. Оба варианта: training seeds 54/55, параллельно по 2048 сред × 50 PPO updates × 24 шага; заранее выбран `model_398.pt`.

Smoke обоих вариантов прошёл. Diverse replay probe: 614 replay и 1434 stair среды; replay покрывает положительные/отрицательные `vx`, ненулевые `vy/yaw`; на stair `vy=yaw=0`. Landing 205/205 и inverse 102/102 reset probes не дали опасных состояний за первые 10 шагов.

## Ворота

1. Rough development meshes 2009/2010: inverse ≥97/102 и каждое семейство ≥95% на обоих training seeds; общая безопасность не хуже парного контроля более чем на 2 п.п.; RMS не хуже более чем на 10%.
2. При прохождении — flat regression.
3. Затем полная открытая stair suite v3: шесть строк; вариант должен улучшаться одинаково на двух training seeds и пройти проектный порог, прежде чем будет открыта новая финальная suite.

## Результаты

Все четыре полных run завершились без ошибок. Время обучения без startup: control 220.70–220.94 с, diverse replay 221.75–221.87 с. Checkpoints и hashes:

| Вариант / training seed | SHA-256 `model_398.pt` |
|---|---|
| Control / 54 | `fd8892cbd316706e2ea30f58c2b87d1159bde0d83e2ef9837c09ba6552149abd` |
| Control / 55 | `c8db647b5df88014a0993364a834c7ba2f8bdabacf47b4b1d6dea33df6aad9f6` |
| Diverse replay / 54 | `fd835961cf7f5d035fbe9358892ce5371d957603c60a547f138b6687bca39de2` |
| Diverse replay / 55 | `39528a1c3edfd531ba2f3993d7180fcc26514150f3168fa258a37749112d284f` |

Rough development gate, формат — безопасно всего / безопасно inverse:

| Вариант / training seed | Mesh 2009 | Mesh 2010 | Сумма |
|---|---:|---:|---:|
| Control / 54 | 508/512; 99/102 | 509/512; 101/102 | **1017/1024; 200/204** |
| Control / 55 | 505/512; 99/102 | 509/512; 100/102 | **1014/1024; 199/204** |
| Diverse replay / 54 | 508/512; 99/102 | 501/512; 96/102 | **1009/1024; 195/204** |
| Diverse replay / 55 | 511/512; 102/102 | 507/512; 99/102 | **1018/1024; 201/204** |

Diverse replay улучшил результат для training seed 55, но ухудшил для seed 54. На mesh 2010 seed 54 не прошёл заранее заданный inverse gate: 96/102 при пороге 97/102; это также ниже 95% безопасности семейства. Контроль прошёл rough gate на обоих training seeds. RMS tracking всех run остался в пределах 10% от parent по компонентам.

**Решение по diverse replay:** вариант отклонён по первому gate. Не выбирать удачный seed 55; flat regression и stair suite для diverse replay не запускались.

Оба control прошли rough gate, поэтому для них выполнена flat regression на seed 1003: 128/128 безопасных эпизодов у обоих, RMS `(vx, vy, yaw)` `(0.176, 0.185, 0.150)` для seed 54 и `(0.184, 0.183, 0.150)` для seed 55. После этого оба control и исходный parent оценены полной открытой suite v3 при одинаковом brake 1.2 м: 6 строк × 128 эпизодов × 900 policy steps.

| Геометрия | Parent seed 55 | Control / 54 | Control / 55 |
|---|---:|---:|---:|
| 14/32 см ↑ | 105 / 86 | 104 / 81 | 105 / 80 |
| 14/32 см ↓ | 115 / 101 | 116 / 94 | 117 / 94 |
| 16/30 см ↑ | 110 / 81 | 100 / 74 | 104 / 84 |
| 16/30 см ↓ | 117 / 100 | 116 / 99 | 117 / 100 |
| 18/27 см ↑ | 91 / 75 | 93 / 72 | 96 / 74 |
| 18/27 см ↓ | 122 / 98 | 122 / 104 | 121 / 101 |
| **Сумма passage / cycle** | **660 / 541** | **651 / 524** | **660 / 533** |

Итоговые причины неуспеха `(unsafe / incomplete / stop_failed / timeout)`: parent `86 / 39 / 102 / 0`, control/54 `92 / 37 / 115 / 0`, control/55 `89 / 38 / 108 / 0`. Ни одна строка не достигла 95% полного цикла. Control/55 локально улучшил две строки, control/54 одну, но оба хуже parent суммарно и не показывают одинакового направления на training seeds.

**Финальное решение:** ни diverse replay, ни control checkpoint не принят. Закрытые stair seeds 4101–4104 не использованы. Основным исследовательским rough parent остаётся исходный seed 55; rough stage по закрытой оценке всё ещё не закрыт. Следующая гипотеза должна менять постановку лестничного цикла или доступное actor состояние, а не продолжать прежний PPO или подбирать долю replay.

Артефакты: `logs/rsl_rl/unitree_b2w_stair/2026-09-23_09-10-41_stair_replay_diverse_replay_2048_20260923_seed{54,55}_full/`, `2026-09-23_09-14-58_stair_replay_control_2048_20260923_seed{54,55}_full/`, оценки `logs/stair_replay_20260923/`. Source hashes: `train_stair_b2w.py` `4eb9644a24c9821d80d468251f44311e85f5d7308b990c680f41142bb944e3d2`; launcher `7a0c4a145040efdf1155caa12ac91595b445d5fdf17abacf16f66f4c947201bc`; rough evaluator launcher `f69c93c21807f0c6e9b91bae306ea9d13c9508f380a924264ad976011d87c8be`.
