# Rough: запрошенное продолжение 150→350

20.09.2026. После сообщения, что Rough150 не прошёл и очередь остановлена,
пользователь прямо поручил: «продолжай обучение». Этот запрос разрешает один
ограниченный диагностический этап после прежнего quality stop. Исходные
результаты остаются неизменными; прежний milestone150 остаётся failed.

Продолжаются seeds57/58 от собственных проверенных `model_149.pt` серии
`rough_tilt_correction_20260920`, с восстановлением actor, critic, optimizer
и curriculum. Каждый получает ровно200 новых updates, заканчивает на349
(350 накопленных). По4096 env последовательно;400×4096×24 =39321600 новых
transitions. Никакого повторения50/150, замены seeds или дальнейшего продления.

Настройки действующего tilt-correction recipe сохранены: true terminal при
tilt>60° дольше0,1с, LR1e-4, clip0,1, std0,1, entropy0, rollout24, yaw0,25,
upright reset±0,1, actor57/critic247. По исходному stage2 открывается cap2;
продвижение внутри cap остаётся только по safe-traversal curriculum.
Оба drift guards0,25, finite checks и export parity сохранены.

Перед запуском повторно проверяются parent hashes, optimizer/checkpoints,
исходники, полные первичные16 Rough и4 Flat отчёта. Все четыре Flat gates150
должны проходить; исключение относится только к раскрытому Rough quality fail.
Новые geometry/cases или ослабление критериев не вводятся.

После обучения —4 Flat evaluations100 и48 Rough evaluations100:
4families×3levels×2profiles×2seeds. Полный диагностический набор собирается
даже при неуспехе отдельного quality case, но не даёт новых training updates.
Flat≥99/100 и прежние RMS/relative-regression критерии; Rough≥95% отдельно
по kind/family/level/profile, прежние corridor/route/tracking требования.
Level2 curriculum проверяется отдельно. Успех final checks не переписывает
неудачу150 и не закрывает исходный development protocol или qualification.

До каждого процесса свободно≥50% VRAM, во время≥5%. Train3600с на сид,
evaluation1800с на100-case batch. Любой technical/drift/VRAM failure прекращает
очередь. Source/protocol/parent hashes фиксируются до запуска. Qualification,
Stairs, sim2real и аппаратное управление не запускаются этим координатором.
