# Rough4096 и два процесса

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Продолжение по запросу пользователя19.09: проверить4096 и по возможности
два seeds одновременно, затем начать основную серию в лучшем измеренном режиме.

Все capacity weights discard. Fresh seeds5703(single4096),5704/5705(pair).
Каждый50 updates,warmup1; тот же frozen seed54, terrain level0, actor57/critic247,
LR1e-4,std0,1,clip0,1,drift0,25; timeout3600 с/stage. Пять первых updates
исключены из timings. До stage/pair free VRAM≥50%, во время≥5%.

Сначала single4096. До pair прогноз peak=idle+2*(single_peak-idle).
Если прогноз оставляет≥7% VRAM (5%guard+2%запас), проверяется2×4096;
иначе2×2048. Общий empty-device preflight относится ко всей паре; второй
процесс запускается после2 updates первого, чтобы не конвертировать asset
одновременно. Отказ любого worker останавливает только собственную пару.

Сравниваем single event-wall throughput и суммарные полные updates внутри
общего post-warmup интервала pair. Минимум30 с и10 полных updates/worker.
Предпочитаем больший measured throughput при сохранённых guards. Не переносим
Flat qualification на Rough. После добавления curriculum проверяем стоимость
его instrumentation до назначения R1. Seeds R1 и budgets регистрируются отдельно.
