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

1. Разобрать failures 24650 по четырём типам: tracking, transition, standstill,
   traversal; не менять reward до подтверждения причины.
2. Выбрать одну гипотезу с ограниченным бюджетом и независимыми selection seeds.
3. Сравнить новый кандидат с 24650 тем же компактным протоколом.
4. После simulation gate выполнить MuJoCo runtime/transport qualification.
5. Измерить hardware mapping, latency и actuator limits до locomotion на роботе.
6. Реальный запуск возможен только после отдельного явного допуска и этапов из
   [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md).

Raw evidence последней проверки сохраняется локально неизменным; live logs,
caches и runtime не добавляются в Git.
