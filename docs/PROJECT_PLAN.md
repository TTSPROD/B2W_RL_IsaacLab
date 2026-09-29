# План B2W

## Цель

Получить устойчивую низкоуровневую policy Unitree B2W для Flat, Rough и Stairs
в пределах обученного диапазона скоростей. Внешний уровень отвечает за маршрут,
waypoint, абсолютный heading и момент смены команды. Нулевая команда означает
остановку и устойчивость без возврата к прежней позиции или курсу.

## Текущая точка

Активный кандидат — [core_24650](results/2026-09-28-core-selection-24650.md).
Он выбран unsafe-first paired screen, но общий gate не прошёл. Автоматическая
promotion отключена; hardware-approved policy нет.

## Acceptance contract

На каждом заранее объявленном условии проверяются:

- tracking `(vx, vy, omega_z)` после settling;
- отклик и переходы команд;
- непрерывный ноль не менее 10 s;
- traversal лестницы с физическим exposure;
- finite state/action, наклон, контакты и hard joint ranges;
- приводы отдельно от кинематической успешности.

Навигационные метрики не являются gates. Среднее по условиям не компенсирует
unsafe или провал отдельного рабочего режима.

## Следующая работа

1. Разбор failures 24650 по четырём типам выполнен
   ([trace diagnostics](results/2026-09-29-stage3-trace-diagnostics.md)):
   доминирующий дефект — недоход pure-axis команд 0.3, причина подтверждена
   как reward-баланс; stage-3 exposure-гипотеза опровергнута.
2. Одна гипотеза с ограниченным бюджетом: сузить kernel трекинга малых
   величин (lateral + yaw, focused_std ~0.15 в [0.2, 0.6]) от 24650,
   100 updates, selection seeds 69001–69005.
3. Сравнить новый кандидат с 24650 тем же компактным протоколом; regression
   gates: 0.7/1.0, mixed, stand, нулевые окна, лестницы.
4. Отдельно решить принадлежность медленного подъёма (0.3 m/s на 0.12–0.18 м)
   и удержания на крутых ступенях acceptance-envelope — там есть физическая
   сатурация момента колёс.
5. После simulation gate выполнить MuJoCo runtime/transport qualification.
6. Измерить hardware mapping, latency и actuator limits до locomotion на роботе.
7. Реальный запуск возможен только после отдельного явного допуска и этапов из
   [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md).

Raw evidence последней проверки сохраняется локально неизменным; live logs,
caches и runtime не добавляются в Git.
