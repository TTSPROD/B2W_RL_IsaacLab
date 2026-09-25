# План B2W

Актуально на 25 сентября 2026.

## Цель

Получить воспроизводимую низкоуровневую политику движения B2W и runtime для её
деплоя через Unitree SDK2. Внешний уровень подаёт body-frame `(vx, vy, omega_z)`;
policy управляет 12 суставами ног по положению и четырьмя колёсами по скорости.
ABI 57→16 и частота 50 Hz сохраняются. Целевые условия — Flat, Rough и заранее
объявленные лестницы. Для каждого условия нужна отдельная проверка.

## Текущий baseline

Серверный upstream19999 проверен в [operating57](results/2026-09-25-operating57-19999.md):
36 сценариев × 32 reset seeds, только Isaac Flat. Получено 716/1152 полных успехов
и 3 небольших нарушения compiled hard joint range заднего правого hip.
Все шесть продольных точек ±0.3/0.5/0.7 и боковые ±0.5/0.7 прошли 32/32.
Повороты и остановка после них остаются основной проблемой текущего screen.
Принятой для реального робота policy пока нет.

## Контракт оценки

Команды задаются извне по времени. Ground truth используется для измерений,
но не для коррекции курса, траектории или действий policy.
Нулевая команда требует затухания скорости и устойчивого стояния. Сохранение
абсолютной позиции и heading не требуется. Precision ±0.1 не является текущим приоритетом.

Сохранённые критерии operating57:

| Проверка | Flat development screen |
|---|---|
| Tracking | RMSE по `(vx, vy, omega_z)` ≤ `(0.20, 0.20, 0.25)` после 2 s settling |
| Отклик | Средняя скорость по заданному направлению/вращению ≥80% команды |
| Переходы | Все moving RMSE окна 1 s, заканчивающиеся после 2 s от смены команды, в допуске |
| Ноль | После 2 s удерживать `norm(vxy)≤0.10 m/s`, `abs(omega_z)≤0.10 rad/s` непрерывно 10 s |
| Safety | На каждом physics step: finite, наклон ≤60°, base/hip force ≤5 N, hard joint range с tolerance 0.001 rad |
| Решение по строке | ≥99% полных успехов и 0 unsafe; не усреднять отказ строки с успешными строками |

Это зафиксированные симуляционные критерии последнего screen. Они не подтверждают
аппаратные limits. Torque-speed, current, thermal limits и watchdog проверяются отдельно.
32/32 наблюдения не доказывают 99% надёжность. При итоговой qualification объём,
статистический критерий и независимая validation фиксируются до запуска.

## Основание sim2real-плана

Источники проверены 25 сентября 2026. Официальный
[Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab/blob/main/README.md)
использует MuJoCo sim2sim перед SDK2 sim2real. Его готовые deploy-примеры относятся
к другим моделям Unitree; инструкции для нашей B2W policy 19999 там нет.
Для B2W опорные интерфейсы — официальный
[SDK2 stand example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp)
и [Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco).

Реальные испытания похожего интерфейса — 12 leg position + 4 wheel velocity targets,
50 Hz — описаны у Lee et al.,
[Science Robotics, 2024](https://arxiv.org/html/2405.01792v1).
Их колёсно-ногий робот, рекуррентная perceptive policy и приводы отличаются от B2W.
Применима методика проверки и моделирования приводов; их сеть, gains и результаты
не подтверждают нашу policy. Из [Tan et al., 2018](https://arxiv.org/html/1804.10332),
с физическими испытаниями Minitaur, берём system identification, учёт actuator
dynamics/latency и randomization измеренных неопределённостей.

Ниже — инженерная адаптация первичных источников под наш контракт. Условия
переходов являются требованиями проекта, а не сертификацией Unitree. Конкретные
hardware limits, допустимая задержка и fault behavior требуют измерений.
Детали — в [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md), фактический состав исходников —
в [VENDOR_INVENTORY](VENDOR_INVENTORY.md).

## Этапы и условия перехода

| Этап | Работа | Проверяемый результат / условие перехода |
|---|---|---|
| S0. Зафиксировать кандидат | 19999 checkpoint/export SHA, observations, scales/clips, previous action, targets, gains и 50 Hz; отдельно hardware mapping | Версионированный deployment manifest; export parity уже сохранена, аппаратные поля остаются открытыми |
| S1. Offline runtime | Один observation adapter, deterministic actor, mapper, state machine и watchdog; replay без сети | Совпадение observation/action/targets с эталоном, включая clipping и reset; invalid inputs блокируют policy; отчёт parity |
| S2. Runtime через DDS в MuJoCo | Тот же executable получает LowState и отправляет LowCmd через официальный bridge; timing и fault injection | Изолированный sim domain/interface, проверенные mapping/CRC/timing и все fault cases; это отдельная проверка от качества locomotion |
| S3. Измерить B2W | Сначала read-only telemetry; затем отдельно разрешённая идентификация на страховке/стенде без locomotion policy | Firmware/motor map, frames, delays, response приводов, saturations, доступные current/thermal limits; калиброванная модель с интервалами неопределённости |
| S4. Qualification в симуляции | Исправить yaw/stop 19999; проверить кандидат в Isaac/MuJoCo с моделью S3, задержками и объявленными вариациями | Независимая validation диапазона: tracking, transitions, continuous zero, safety и приводы. Для первого hardware этапа — отдельно принятый Flat поддиапазон; текущий screen его ещё не квалифицирует |
| S5. Первый policy запуск на роботе | После допуска: передача управления, поддерживаемая поза, policy с нулём, постепенная нагрузка на опору | Проверенные stand/stop и аварийная процедура на целевом B2W; нет неожиданных targets, violations, stale state или насыщения |
| S6. Ограниченный Flat | Профили из принятого S4 поддиапазона: прямой/боковой ход, yaw, реверс, остановка; расширять по одному фактору | Реальные скорости и нагрузка записаны; каждый профиль проходит заранее объявленные tracking/zero/actuator критерии без навигационной коррекции |
| S7. Условия эксплуатации | Отдельно Rough, измеренные склоны/лестницы, затем продолжительность и payload | Для каждого условия свой проверенный диапазон; release привязан к policy SHA, runtime, firmware и конфигурации робота |

S1–S2 можно выполнять до финальной qualification. S3 требует разрешения на
подключение/стендовые команды и не требует запускать непринятую policy.
S5 зависит от S1–S4 и явного допуска. Новое покрытие сначала проверяется в
симуляции. Симуляция не заменяет измерений аппаратных ограничений.

## Ближайшая очередь

1. По сохранённым трассам 19999 локализовать побочную скорость при yaw и остаточное
   движение после нуля; проверить ABI и измерения до изменения rewards.
2. Реализовать S0–S1, затем собрать SDK2/MuJoCo bridge для S2 на отдельном Linux
   runtime. Его исходники и ROS2 interfaces уже закреплены в vendor; сборка и
   transport qualification ещё не выполнены. ROS2 нужен для интеграции/telemetry
   при выбранной ROS-архитектуре, прямой SDK2 loop может работать без него.
3. Подготовить S3: перечень измерений, приборы, допустимые воздействия и abort limits.
   Не подбирать физику ради прохождения screen.
4. Только при подтверждённой необходимости — один ограниченный эксперимент на
   19999: гипотеза, control, seeds, бюджет, stop/regression criteria. Измеренный
   sim2real gap определяет изменения actuator model и DR. Новое обучение и server
   job требуют отдельного решения.

Upstream10000 повторно не оценивать и не обучать. Изменение документации не
разрешает actuation. Абсолютный heading, corridor, waypoint и выбор момента
торможения остаются во внешнем уровне и не становятся gates policy.
