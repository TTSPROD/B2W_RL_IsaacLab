# Sim2sim2real для B2W: что опубликовано Unitree и что принято проектом

Актуально на 12 октября 2026. Этот документ задаёт порядок S2 для текущего
development candidate `core_24650`. Он не разрешает управление роботом.

## Проверяемые сведения Unitree

1. [Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab#deploy)
   описывает последовательность: обучение в Isaac Lab, затем проверка обученной
   policy в MuJoCo (`unitree_mujoco`), затем sim2real. В примере G1 одна и та же
   программа `g1_ctrl` работает сначала с симулятором, затем с
   `--network eth0` на роботе. В опубликованном списке поддерживаемых задач RL Lab
   названы Go2, H1 и G1-29dof; готового B2W training/deploy recipe там нет.
2. [Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco)
   публикует B2W как выбираемую модель и C++ SDK2 bridge. В конфигурации
   симулятора Unitree рекомендует отдельный от реального робота DDS domain
   (пример: 1) и локальный интерфейс `lo`. Для B2W используется семейство
   сообщений `unitree_go`.
3. Закреплённый [B2W MJCF](../vendor/unitree_mujoco/unitree_robots/b2w/b2w.xml)
   задаёт, в частности, joint `damping="1"` и `armature="0.1"`.
   Закреплённый [C++ bridge](../vendor/unitree_mujoco/simulate/src/unitree_sdk2_bridge.h)
   вычисляет усилие из `LowCmd` как
   `tau + kp * (q_des - q) + kd * (dq_des - dq)`. Это опубликованное поведение
   данной модели/bridge, а не доказанная характеристика приводов физического B2W.

В просмотренных материалах Unitree **нет требования** приравнивать массу,
`armature`, `damping` или actuator law MuJoCo к resolved PhysX перед sim2real.
Это вывод об отсутствии такого предписания в указанных открытых материалах,
а не утверждение, что различия физики безопасны или несущественны.

## Проектное решение для S2

Применяем опубликованный порядок Unitree к B2W: замороженный actor и один
проектный SDK2 `PolicyRuntime`/mapper проходят offline contract, затем
независимый DDS sim2sim через **неизменённые** pinned B2W MJCF и C++ bridge,
после чего рассматриваются аппаратные этапы S3–S7 по
[SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md). Неизменность модели и bridge выбрана
проектом, чтобы результат имел однозначное происхождение; Unitree не
формулирует её как универсальный acceptance gate.

В S2 фиксировать export/checkpoint SHA, vendor revision, бинарный hash,
joint order/signs/units, observation/action scales и previous raw action,
50 Hz policy / 200 Hz physics, LowState→actor→LowCmd и timing. Проверять
полные программы tracking, смен команд, непрерывного нуля, устойчивость,
actual-state/PD-reference guard, DDS loss/reorder/disconnect/recovery и
приводные ограничения. Зафиксировать nominal и заявленные variation/reset
условия до оценки. Совпадение transport и прохождение части команд
не равны qualification.

Изменённые DC law, `armature=0` и будущие passive-dynamics варианты
остаются **контрфактической диагностикой**. Они могут локализовать причину
расхождения Isaac/MuJoCo, но их success не засчитывается как результат
официальной B2W MuJoCo-модели. Ранее предложенный следующий шаг
`damping=0` отозван как обязательный этап S2. Исправления собственных
ошибок runtime, измерения и safety-guard допускаются отдельно, с новым
manifest и повторным запуском на неизменённой модели Unitree.

Текущие результаты: original bridge прошёл software/DDS и fault checks;
ранний полный Flat replay с жёстким project desired-target guard остановил
четыре motion-программы. Исправленный actual-state/PD-reference guard и timing
получили 2/5 tracking successes в replay, но этот replay использовал
изменённую DC actuator law и потому **не закрывает S2 на исходном bridge**.
Live Isaac дал 3/5 в другом движке, один seed; это диагностика расхождения.
Ни один из этих результатов не подтверждает B2W hardware envelope.

## Следующая проверка

1. Заморозить software runtime и отдельно протоколировать оба профиля guard:
   прежний strict desired-target reject и обоснованный simulator-only
   actual-state/PD-reference вариант. Аппаратные bounds остаются неизвестными.
2. Повторить полный согласованный Flat command/zero protocol и DDS fault/timing
   checks на **исходных** B2W MJCF и C++ bridge Unitree с тем же actor, mapper,
   gains, reset seeds и явно записанным guard profile. Сохранить raw evidence
   и executed hashes, не переносить результаты с DC variant.
3. Разобрать failures по tracking, переходам, нулю, actual safety и приводам.
   Только после этого решать, нужен ли отдельный training/MDP фактор. Любое
   новое обучение выполняется по [PROJECT_PLAN](PROJECT_PLAN.md) и
   [CORE_LOCOMOTION_EVALUATION](CORE_LOCOMOTION_EVALUATION.md).
4. S3–S4: на целевом B2W отдельно проверить motor order/signs/units,
   firmware/LowState, актуальные ограничения приводов и задержки.
   Реальное управление — только после отдельного допуска и этапов S5–S7.

История опытов и их исходные предложения сохранены в
[индексе результатов](results/README.md); текущую очередность задаёт
[PROJECT_PLAN](PROJECT_PLAN.md).
