# Rough R1: seeds57/58, single4096

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

20.09.2026. Запрос пользователя: проверить4096 и обучать максимально быстро,
по возможности два seeds одновременно. [Capacity](results/rough_capacity_20260919.json):
single4096 wall26153 transitions/s против dual2048 aggregate21170. Пара прошла,
но медленнее;2×4096 требует по прогнозу13,13GB при12,28GB доступных.
Назначаем **по4096 env последовательно**, seeds57/58. Число env/recipe неизменно.

Один frozen actor qualified Flat seed54, новые critic247 и optimizer для каждого
seed.50 critic-only +100 PPO +200 PPO, std0,1,LR1e-4,clip0,1,entropy0,
rollout24,pure-yaw0,25,reset roll/pitch±0,1. Никаких reward/actuator изменений.
Всего максимум68812800 training transitions.50/150 — stop gates, только350
кандидат. R2 и Stairs не запускаются этой очередью. Seed replacement/продления нет.

До R1: пройденный R0, single/dual capacity и новый GPU preflight с collision
geometry/bounded physics readback на level2, safe curriculum train/resume2+2 и полный100-case прогон random level0.
Последний проверяет весь evaluator; исходный Flat actor не обязан пройти Rough quality gate.
Исторические fixture ошибки сохраняются отдельно; ни одна не была обучением R1.
Для runtime стоимости нового curriculum записываются все PPO timings stage0;
cap0 и изменившиеся CPU затраты не являются основанием менять число env в серии.

Terrain mix и геометрия из ROUGH_R0. Curriculum cap0/1/2 по stages;
каждый family (random, slopes обоих знаков, blocks) повышается/понижается
после≥100 moving episodes при≥80%/≤60% safe traversal. Direction/progress
интегрируются на каждом physics step; минимум1м и≥50% интеграла commanded speed.
Контакт>1N, tilt>60° дольше0,1с, NaN/Inf и выход base за tile±5,4м sticky.
Stand/yaw-only episodes не участвуют. Rewards/termination остаются upstream.
Counters/levels/history сохраняются в checkpoint; незавершённые episodes и RNG
симулятора сбрасываются при restart одинаково для двух seeds.

Flat regression: прежние seed54 cases2026091961/62, nominal/bounded_v1,
100 episodes;≥99/100 и RMS≤0,20/0,20/0,25 по каждому scenario. Дополнительно
рост RMS≤max(10% parent,0,01), success loss≤2pp. Parent reports повторно
проверяются по первичным rows и hashes. Это раскрытая regression, не hold-out.

Rough development cases frozen до training: geometry2026091980,
case seeds2026091981/82;4families×3levels×2profiles×100 cases.60 traverse,
20 stand,20 turn. Все стартуют на горизонтальной площадке; stand/turn сначала
проходят на Rough12с со скоростью0,3м/с, затем8с стоят/вращаются на terrain.
Traverse0,20–0,24м/с,2с settle+20с measurement, без auto-reset. Нужно≥3м,
все wheel centers в corridor x[-0,6;5,4],y[-0,9;0,9]. Slope labels относятся
к движению вдоль+x. На150 level0 threshold90% отдельно по каждому виду case;
на350 все levels и95%, RMS≤0,25/0,25/0,30. Failure всех проверяется сt=0.

Отчёты сохраняют actual USD collision-hull sampled vertical clearance и p01,
сила/звено первого контакта, terrain normals, tilt, геометрию опорного polygon,
wheel gap/edge distance/slip, energy16actuators, actuator torque/velocity saturation,
computed/applied torque clipping, joint limits, command/action clipping и p95/max
tracking. Continuous wheel positions явно исключены из position-limit теста;
effort/velocity limits берутся из actual actuator tensors, не PhysX sentinel.
Clearance — выборка поверхности hull, не точный continuous minimum; wheel slip
включает projection без контакта. Safety gate использует реальные PhysX contacts.
Эти диагностики и simulator limits не закрывают hardware torque-speed envelope.

Drift≤0,25 на текущих Rough observations и frozen4096 Flat bank; pre/post на
одних inputs. Export/live raw и processed target parity≤1e-5. Finite/source/parent
hash checks обязательны. До каждого процесса freeVRAM≥50%, во время≥5%.
Train timeout3600с/stage;100-case evaluation1800с по исходному плану.
Любой technical fail или quality gate останавливает дальнейшую очередь.
