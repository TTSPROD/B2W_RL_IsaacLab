# Rough/Stairs: пересмотр подхода по Isaac Lab, 20.09.2026

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

**ОСТАНОВЛЕНО по уточнению пользователя20.09.2026. Actor строго57→16,
как reference. Teacher247 отклонён; дальнейшее обучение не разрешено текущим
планом. Фактически выполненные100updates seed67 сохранены только как отклонённый
эксперимент, seed68 не запускался. Активных teacher процессов нет.**

Ниже исторический отклонённый протокол; не команда к запуску.

Это новый архитектурный опыт, а не продолжение failed65/66 и не однофакторная
абляция. Прежние результаты, thresholds, checkpoints и vendor сохраняются.
Статус выполнения — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md).

## Что отличается от NVIDIA

Проверены Isaac Lab main `b0542fe2d45bf91c4e1d9ef6952b9c709c80b4e8`
и установленный v2.3.2 `37ddf626871758333d6ed89cf64ad702aef127d0`.
Runtime остаётся v2.3.2 / Sim5.1 / RSL-RL3.1.2; main не устанавливается.

| Механизм | NVIDIA Go2 Rough | Наши завершённые серии | Новое решение |
|---|---|---|---|
| Actor | Скорость корпуса, proprioception и height scan | Blind57; velocity/187 rays только у critic247 | Отдельный sim teacher247: прежние57 + velocity3 + rays187 |
| Задача | Body velocity locomotion; heading command превращается в yaw velocity | Open-loop body commands и требование мирового corridor всех колёс | Locomotion отдельно; маршрут требует внешнего feedback controller |
| Рельеф | Rough mix, включая40% pyramid stairs up/down | Самодельный Rough без stairs, затем отдельный gate | Сначала прежний level0 для технического сравнения; затем широкие ступени в mix |
| PPO | 1500 updates Go2, std1, adaptive LR1e-3, clip0.2, entropy0.01 | 50 frozen +100+200, std0.1 fixed, LR1e-4, clip0.1, entropy0; drift stop0.25 | Короткая проверка нового teacher, затем отдельно зарегистрированный достаточный бюджет |
| Curriculum | Per-environment distance-based terrain levels | Общий family80/60% с corridor failures | Разделить difficulty sampling и независимую safety/quality оценку |
| Контакты | Go2 base contact terminal; undesired-contact reward отключён | B2W non-wheel safety contract | Не копировать Go2 контактную семантику на B2W; wheel-only contract сохраняется |

Go2 имеет12 ноговых actions, B2W —12 position +4 wheel velocity. Не переносим
его motor scales, массу, torque penalties и air-time reward буквально.
235 входов Go2 и247 teacher B2W — разные robot contracts.

Источники: [Go2 configuration](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/go2/rough_env_cfg.py),
[velocity observations/commands](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/velocity_env_cfg.py),
[Go2 PPO](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/go2/agents/rsl_rl_ppo_cfg.py),
[terrain mix](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab/isaaclab/terrains/config/rough.py).

## Почему перестаём расширять corridor

В wide65/66 все1036 первых отказов — corridor, curriculum обоих остался level0.
Actor не видит x/y, world heading, route error, фактическую скорость корпуса
или terrain. World-position terminal сам по себе эту информацию ему не даёт.
Это подтверждённое несоответствие контрактов; доля его вклада в каждый отказ
не установлена парной абляцией. Добавление lin_vel также не заменяет navigation.

Большой critic не передаёт свои наблюдения actor во время inference.
Сохранение хорошего Flat навыка не доказывает возможность выучить ступени
при жёстком ограничении actor drift и почти неизменной exploration.
Поэтому новые наблюдения, MDP и PPO оформлены как новая ветка и не выдаются
за доказательство единственной причины прежних неудач.

## Исполнимый первый этап T0

- `scripts/b2w_locomotion_teacher.py`: отдельный teacher ABI247→16,
  первые57 в прежнем порядке/scales, затем clean velocity3(scale2) и height187.
  Critic получает clean247. Teacher использует истинные simulator данные;
  экспорт несовместим с blind57 deployment.
- Flat54 actor переносится с нулевыми новыми190 колонками первого слоя.
  Все остальные веса копируются точно. CPU/live parity проверяется до PPO;
  critic/optimizer создаются заново. Старые anchors не изменяются.
- Прежние12m level0 tiles с30% Flat,30% random,20% slopes,20% blocks;
  никаких route/corridor terminals. Upright reset и zero initial velocities,
  штатный heading feedback, moderate velocity commands, без pushes/forces.
  Запрещённый non-wheel contact и наклон завершают training episode;
  граница tile — timeout, не скрытая навигационная цель.
- B2W actions/reward weights сохраняются, tracking std возвращён к upstream0.5.
  Native PPO24 steps,512/256/128 ELU, clip0.2, entropy0.01, adaptive LR1e-3,
  desiredKL0.01,5epochs/4minibatches. В critic warmup LR1e-3 fixed:
  KL замороженного actor равен0 и не должен разгонять adaptive LR.
  Начальный std0.3 обучаемый после warmup.
  Это умереннее std1 NVIDIA, но уже не fixed0.1.
- Discard smoke:64env,2+2updates, warmup1; проверить optimizer resume,
  изменение actor/critic, finite losses, scan/actions, checkpoint/export.
- Затем два свежих seeds67/68 **последовательно**,1024env,100updates каждый:
  25critic-only +75PPO. Бюджет4,915,200 transitions, smoke ещё6,144.
  После smoke проверяются resource guards;1024 выбран как первый bounded pilot,
  прежняя4096 capacity не выдаётся за квалификацию нового ABI/task.
- GPU headroom до stage≥50%, во время≥5%, timeout3600s/stage;
  source/config/parent hashes и внешние exit codes обязательны.
  Технический fail останавливает очередь; новые попытки получают новые output.
  Никакого автопродления после100 или автоматического запуска mixed stairs.

На100 не требуем прежнего world-route95% pass и не объявляем Rough pass.
Публикуем learning curves, velocity errors, episode length, contact/tilt resets,
terrain exposure, trainable std и действительное использование новых входов.
Короткий deterministic replay — диагностический, с явной auto-reset семантикой;
он не заменяет независимые100-case оценки без reset.

## T1: locomotion на Rough и широких ступенях

После T0 и отдельного native mixed terrain smoke: общая velocity задача включает
широкие pyramid stairs вверх/вниз с riser0.05–0.18m, tread0.35m, platform≥3m.
Это обучение контакту с перепадом, не приёмка обычной лестницы.
Проверить collision mesh, фактические risers, направления, spawn/finish,
height scan, boundary и curriculum promotion/demotion. Promotion после
запрещённого контакта не допускается; random rough difficulty проверять по mesh:
upstream uniform noise range не обязан зависеть от difficulty.

До запуска зарегистрировать два seeds, pilot timing, поэтапный бюджет до1500
updates/seed и development evaluations после250/750/1500. Это ориентир Go2,
а не обещание сходимости B2W; такой бюджет в T0 не запускается.
Остановка по NaN/runtime/ресурсам, collapse survival и заранее зафиксированному
отсутствию прогресса на development metrics. Reward в одиночку не критерий.

Новый locomotion evaluator: фиксированные body/heading команды, каждый terrain
family×level×physics profile, без требования удержать невидимый коридор;
sticky physics-rate safety, tracking RMS, падения, contact/slip/energy,
progress относительно команды и подтверждённый контакт с рельефом.
Нахождение на spawn pad не считается прохождением terrain. Точный корпус cases
и пороги фиксируются до T1. До этого evaluator и T1 не считаются готовыми.
Flat safety/absolute/relative regression остаётся обязательной для принятия
любого результата; adapter teacher observations и его parity проверяются отдельно.

## S: straight stairs и deployment

Straight stairs evaluator сохраняет прежние требования: up/down отдельно,
0.05–0.18m,100cases/level/profile,≥95/100, все колёса на целевой площадке,
2s остановки, запрет обхода, wheel-only contacts и physics-rate sticky failure.
World-z Flat gate на ступени не переносится. Прежние route reports остаются
непройденными; новый locomotion score не переименовывается в их pass.

Команды для узкого марша генерирует отдельный контроллер по измеренным
cross-track/heading/remaining-distance errors; down/up скорость ограничивается
геометрией. Его inputs, saturation и stop logic становятся частью system
contract. Симуляционный oracle controller должен быть явно обозначен.
Нужны fixtures курса, бокового ухода, торможения, обеих сторон ступеней;
затем2development и3qualification seeds, Flat/Rough regression.

Для blind deployment нужен отдельный history/velocity estimator student,
teacher→student imitation/distillation и проверка потери качества. Если нужна
terrain perception на роботе, её сенсорный контракт квалифицируется отдельно.
Teacher247 нельзя загружать в существующий57-input SDK/gamepad export.
MuJoCo и hardware gates остаются отдельными; actuation не разрешён.

## Что ещё полезно в isaaclab_tasks

Шаблоны ANYmal/Go2 показывают разделение robot-specific tuning и общей MDP.
Navigation показывает иерархию: high-level position command → low-level velocity
policy. Distillation/RSL-RL и perceptive задачи полезны как каркас teacher/student;
API main нельзя переносить без проверки доступности в pinned runtime.
Manipulation/Mimic/direct tasks не являются готовым B2W stairs решением.
Ссылки и детали дополнительного аудита добавляются рядом с итогом T0.

Проверенные дополнительные примеры:
[Navigation ANYmal](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_tasks/isaaclab_tasks/manager_based/navigation/config/anymal_c/navigation_env_cfg.py)
(внешний pose controller; high-level в10раз медленнее locomotion),
[Distillation ANYmal](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/anymal_d/agents/rsl_rl_distillation_cfg.py)
(каркас Flat student/teacher, не готовый B2W perceptive→blind рецепт),
[ANYmal symmetry](https://github.com/isaac-sim/IsaacLab/blob/b0542fe2d45bf91c4e1d9ef6952b9c709c80b4e8/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/mdp/symmetry/anymal.py)
(потребует отдельной16-action B2W permutation и отражения height grid).
Эти дополнительные механизмы в T0 не включены.
Четыре ключевых Go2 файла (robot cfg, velocity cfg, terrain mix, PPO) при
HTTP-сравнении совпали между проверенными main и v2.3.2. Обновлять runtime не нужно.
