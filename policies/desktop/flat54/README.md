# Настольная линия: Flat seed54

Извлечён из ранее опубликованного `logs/transfer/b2w_flat54_handoff_20260921.tar.gz`, commit20002fa. Проверены SHA архива и каждого исходного bundle member. Полная исходная provenance — `source_bundle_manifest.json`; новые пути и hashes — `manifest.json`.

- `model_349.pt` — полный resumable checkpoint, SHA `3eeb00963e528f6b31607a0188691f123b9ba533288a58c931c98ef790cab4fc`.
- `policy.pt` — экспортированный TorchScript actor57→16, SHA `f3509a695591ca5235c0a68df7051379ffa315df6dc4515481db4209aa8f8cee`.
- `agent.yaml`, `env.yaml`, `export_manifest.json`, `nominal.json`, `bounded_v1.json` — исходные конфиги и свидетельства проверки.

**Квалифицирован только для Flat по своему симуляционному протоколу; не принят для Rough/Stairs и не разрешён для реального робота.** Это не внешний rl_sar reference. История и ограничения: [настольные результаты](../../../docs/TRAINING_PROGRESS.md), [общая карта трёх линий](../../../docs/TRAINING_STATUS.md).
