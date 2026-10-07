# Мировые практики: дообучение и тестирование low-level политик колёсно-ногих роботов

Дата обзора: 1 октября 2026. Ветка: `deepseek`.
Цель — первичные подтверждённые приёмы обучения/тестирования velocity-conditioned
low-level политик с 12+4 приводами, применимые к B2W 57→16 без раздувания actor.
Числа бюджетов и пороги ниже — наши инженерные решения; статьи не дают рецепта
для B2W массой 82.42 кг. См. итоговый [план дообучения](../DEEPSEEK_FINETUNE_PLAN.md).

## Сводная таблица источников

| Источник | Подтверждённый приём | Ограничение переноса |
|---|---|---|
| [MUJICA (arXiv 2605.13058, 2026)](https://arxiv.org/html/2605.13058v1), реальный Unitree Go2-W | Unified multi-skill proprioceptive low-level: omnidirectional + platform climb + fall recovery в одной сети; curriculum; жёсткие DC-motor constraints с зависимостью момента от скорости/положения; P3O (reward + constraint critics); 16 приводов, 50/200 Гц | History/GRU encoder, latent state, skill selector и P3O — изменение нашего ABI/метода. Их limits (Go2-W) нельзя копировать в B2W. 30k iterations у них — не наш бюджет continuation |
| [Lee et al., Science Robotics 2024 (2405.01792)](https://arxiv.org/html/2405.01792v1), ANYmal on Wheels/Swiss-Mile | LLC (12 joint position + 4 wheel velocity, 50 Hz) через privileged learning; RNN actor; отдельные leg/wheel actuator модели; разделение низкоуровневого управления и навигации; curriculum + DR; измерение gait по terrain | Perceptive/recurrent policy + HRL ≠ наш stateless blind 57 actor. Акцент на actuator modeling колёс (torque через модель тока) — для B2W нужно отдельно измерять |
| [Blind Stair Climbing, 2024 (2402.06143)](https://arxiv.org/html/2402.06143v1), Ascento/Go1/Cassie/AWoW | Position-based формулировка критична для лестниц; asymmetric actor-critic; terrain boolean в actor; curriculum «отдельная ступень → непрерывный марш»; DR: friction, случайные pushes (0–0.5 м/с ≤ каждые 3 с), 50% контрольный delay (20 мс) | Их actor получает goal inputs и terrain boolean — расширение сферы. Подтверждает: слишком высокое сцепление колеса со ступенью даёт ложный sim-навык подъёма. Наш scope — velocity-conditioned без goal |
| [CaT, 2024 (2403.18765)](https://arxiv.org/html/2403.18765v1) | Constraints как вероятностное terminate будущих наград; Solo-12 с height scans | Термин «constraint» другого типа, чем наш reset. Авторы отмечают проблемы наивных terminations |
| [Rudin et al., CoRL 2021 (2109.11978)](https://arxiv.org/abs/2109.11978) | Massively parallel PPO (тысячи envs) + terrain curriculum (game-inspired, promotion/demotion) | Основание нашего 4096-env подхода. Числа времени/GPU не переносятся на RTX4080 |
| [Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab) | Официальный workflow train → sim2sim (MuJoCo) → sim2real; отдельный deploy-контроллер; DR и curriculum | Не содержит B2W; порядок действий и разделение модулей переносятся, параметры других Unitree — нет |
| [SRU B2W deployment (IJRR 2025)](https://github.com/leggedrobotics/sru-robot-deployment/tree/main/b2w_sim) | Реальный B2W: 16 DOF, joint order [FL,FR,RL,RR]×[hip,thigh,calf,foot]; 50 Hz inference / 200 Hz publish; ONNX; joy-control как safety | Только симуляция+deployment, hardware integration исключена из пакета. Подтверждает 12+4 порядок |
| [DreamWaQ Go2W](https://github.com/ShengqianChen/DreamWaQ_Go2W) | Открытый wheel-leg train/deploy для Go2W; asymmetric critic, blind proprioception | Не источник механических параметров B2W |
| [ETH SRU README+B2W sim](https://raw.githubusercontent.com/leggedrobotics/sru-robot-deployment/main/b2w_sim/README.md) | Разделение sim/controller/navigation; policy на ONNX, joystick deadman | README прямо исключает hardware integration из пакета |

## Выводы, релевантные нашему проекту

1. **Колёсно-ногий low-level на 12+4** — устоявшийся паттерн (Lee 2024, rl_sar,
   SRU B2W): 12 leg position targets + 4 wheel velocity targets на 50 Гц.
   Наш контракт 57→16 в mainstream. Главное малораспространённое отличие — наш
   actor **stateless blind MLP без base linear velocity и без history**.

2. **Ключевой риск переноса (подтверждён у Chamorro и Lee):** колёсно-ногий
   подъём по лестнице часто ложно «учится» в симуляции через избыточное сцепление
   колеса с вертикальной гранью (kick-back/проскальзывание в реальности). Лечение:
   умеренная/friction randomization, контроль скорости на стыке, отдельная
   проверка wheel slip/contact geometry. Для B2W 82 кг это критично.

3. **Curriculum лестниц** в литературе стартует с отдельной ступени
   (single step → марш) и различает up/down и остановку на марше. Наш опыт B
   (адаптивный curriculum по уровням 0–9) дал 0 promotions — окно промоушена и
   критерий «успех» по расстоянию не совпадают с реальной задачей, поэтому
   следующий геометрический опыт должен начинаться с короткого марша.

4. **Преимущество асимметрии:** privileged critic (у нас 247, включает base
   velocity и height scan) — стандартный приём (Chamorro, MUJICA), он УЖЕ есть
   в 24650. Дальнейшие изменения actor-наблюдений (history, terrain boolean,
   latent) — отдельная ABI-линейка, не часть дообучения 57→16.

5. **DR для sim2real:** friction, случайные pushes, контрольный delay — базовый
   набор (Chamorro: 50% шаг с состоянием предыдущего такта = 20 мс delay).
   Наш анонсированный DR-слой в 24650 уже есть; менять его — отдельная гипотеза.

6. **Тестирование:** paired reset seeds, каждая ячейка отдельно, unsafe=0 не
   компенсируется tracking — согласуется с v2 протоколом и рекомендацией
   Agarwal (NeurIPS 2021) о малоразмерных выборках.

7. **Оценку делять в отдельных fresh-процессах с одинаковыми слотами**
   (установлено нашими stair replays): прежние multi-actor порядки не считать
   чистым эффектом весов.
