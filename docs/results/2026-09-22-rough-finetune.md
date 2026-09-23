# Rough fine-tuning: обратные ступени

Дата: 22 сентября 2026. Локальная RTX 4080 Laptop; серверный upstream run не используется. `vendor/` не меняется.

## Выбор родителя

До обучения сравнили rough checkpoints seed 55 и 56 на новых mesh seeds 2007/2008. Каждый прогон: level 9, 512 сред × 1000 policy steps, reset roll/pitch ±0.3 рад, одинаковый seed и распределение команд.

| Checkpoint | Mesh 2007: безопасно всего / inverse | Mesh 2008: безопасно всего / inverse | Всего |
|---|---:|---:|---:|
| Rough seed 55, `model_349.pt` | 511/512; 102/102 | 506/512; 97/102 | 1017/1024 |
| Rough seed 56, `model_349.pt` | 507/512; 100/102 | 506/512; 100/102 | 1013/1024 |

Seed 55 выбран как родитель по общей безопасности и forward tracking, без утверждения статистического превосходства над 56. Parent SHA-256: `765fe2a4cd1438ca3e81c387be570473c5dd3f9db656c4f064ec7a903dd802ed`. Логи: `logs/rough_finetune_20260922/rough{55,56}_eval200{7,8}.*`.

## Зафиксированный опыт

Два варианта от одного полного parent checkpoint, каждый на training seeds 54 и 55, параллельно по 2048 сред × 50 дополнительных PPO updates × 24 шага. Контроль продолжает исходный rough curriculum. Изменение `inverse25`: доля `pyramid_stairs_inv` 0.20→0.25, `random_rough` 0.20→0.15; остальные семейства, команды, reward, PPO и reset roll/pitch ±0.1 рад сохраняются. Actor 57→16; exploration std заморожен на 0.1 после resume. Результаты сравнивать внутри пары с одинаковым числом сред и обновлений; никакие stair checkpoints не используются.

Короткие smoke для обоих вариантов и обоих seeds завершились с загрузкой parent и фиксированным std. Полные запуски и оценка фиксируются ниже после завершения.

Development rough evaluation: mesh seeds 2009/2010, level 9, 512×1000, reset tilt ±0.3 рад. Для продолжения варианта оба training seeds должны дать inverse ≥97/102 и ≥95% безопасности в каждом семействе на каждом mesh seed, общую безопасность не хуже своего парного контроля более чем на 2 п.п., RMS tracking не хуже более чем на 10% по каждой компоненте. Затем flat regression. Финальные mesh seeds 2011–2013 зарезервированы до выбора рецепта; результат по ним не использовать для подбора.

## Результаты обучения и оценки

Все четыре полных run завершились, по 50 дополнительных PPO updates и 2 457 600 переходов каждый. Пары training seeds 54/55 работали одновременно. Время обучения в одной паре: inverse25 217.94–218.56 с, control 219.16–219.28 с; старт Isaac сюда не входит. Во всех checkpoint `model_398.pt` iteration 398 и action std 0.1 во всех 16 действиях. Во время параллельных run `nvidia-smi` показывал около 11.2 из 12.3 ГБ VRAM, это снимок, не peak.

| Вариант / training seed | SHA-256 checkpoint | Rough 2009: всего / inverse | Rough 2010: всего / inverse | Сумма всего / inverse |
|---|---|---:|---:|---:|
| Parent seed 55 | `765fe2a4cd1438ca3e81c387be570473c5dd3f9db656c4f064ec7a903dd802ed` | 508/512; 100/102 | 511/512; 102/102 | **1019/1024; 202/204** |
| Control / 54 | `cb14515f32ceb9d796d9ec7df3886696290c380c103cadfca266d3ab26e18a30` | 509/512; 102/102 | 509/512; 100/102 | 1018/1024; 202/204 |
| Control / 55 | `b6c5e21d7d4a5a0081bbfa930ec86064c473292d772074d7c951a7a8b0186614` | 503/512; 99/102 | 512/512; 102/102 | 1015/1024; 201/204 |
| Inverse25 / 54 | `e5319b8fea9f3e409dfc33e1d61a96d140989bcf5dcfb1409d69d78f36962749` | 504/512; 98/102 | 509/512; 99/102 | 1013/1024; 197/204 |
| Inverse25 / 55 | `1d2334922e3e36bb21f532d52bd4c807f1bcbb1e9b04f4a6e3934a25231f0c87` | 509/512; 100/102 | 509/512; 99/102 | 1018/1024; 199/204 |

Все четыре новых checkpoint прошли порог inverse ≥97/102 и ≥95% по каждому rough семейству на обоих development mesh seeds. RMS tracking также остался в пределах 10% от parent по каждой компоненте. Но inverse25 не превзошёл парный контроль устойчиво на двух training seeds: для seed 54 общая безопасность ниже на 5/1024 и inverse на 5/204; для seed 55 общая безопасность выше на 3/1024, но inverse ниже на 2/204. Сам контроль не улучшил исходный parent на новых mesh seeds. Поэтому ни один checkpoint не принят, продление PPO и flat regression новых checkpoint не запускались; закрытые mesh seeds 2011–2013 не использованы. Основным остаётся rough seed 55 `model_349.pt` для этой линии сравнения; rough seed 54 остаётся родителем прежних stair pilots.

Логи: `logs/rough_finetune_20260922/`; checkpoints: `logs/rsl_rl/unitree_b2w_rough/2026-09-22_18-00-37_rough_inverse25_2048_20260922_seed{54,55}_full/` и `2026-09-22_18-04-46_rough_control_2048_20260922_seed{54,55}_full/`. Код эксперимента: `scripts/train_b2w.py` SHA-256 `9e7faeb2bb37f15d6aa2edc8be1b3fc209c982666b156f543deb23ab323cbfb3`; параллельный launcher `6a3cdfbf106841f53de892fb431b4886ca343e997738165d59ca5c526de22247`; evaluator launcher `c885ccf4d51065f35785fdc3d10df5b2ab12bc3226b137c2d5166bef03abd47a`.
