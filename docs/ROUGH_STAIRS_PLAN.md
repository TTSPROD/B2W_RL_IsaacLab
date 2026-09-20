# Rough/Stairs: контракт57→16, обучение остановлено

**ОСТАНОВЛЕНО по уточнению пользователя20.09.2026. Actor строго57→16,
как reference. Teacher247 отклонён; дальнейшее обучение не разрешено текущим
планом. Фактически выполненные100updates seed67 сохранены только как отклонённый
эксперимент, seed68 не запускался. Активных teacher процессов нет.**

Сравнение с NVIDIA остаётся полезным, но perceptive Go2 не является основанием
менять входы нашей политики. Сохраняются57 observations,16 actions, порядок,
scales,50Hz и export/reference parity. Critic может получать privileged данные.

Следующий пересмотр должен решать Rough/Stairs внутри этого контракта:
velocity locomotion отдельно от route navigation; heading/cross-track feedback
при необходимости формирует существующие3velocity commands извне actor.
Terrain/stairs curriculum и PPO budget требуют нового согласованного протокола.
Существующие Flat anchors и результаты failed57–66 сохранены.
Новых запусков сейчас нет. Teacher247 не используется как parent или candidate.

[Фактический статус](TRAINING_PROGRESS.md),
[исторический blind план](ROUGH_STAIRS_PLAN_BLIND_ARCHIVE.md),
[отклонённое исследование](ROUGH_TEACHER_REDESIGN.md).
