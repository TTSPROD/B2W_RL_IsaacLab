# Зафиксированные upstream-материалы

Снимки выбраны для B2W и сохраняют исходные пути и байты. Источник, commit, license, размер, Git blob SHA-1 и SHA-256 каждого файла — в `manifest.json`. Полные upstream README сохранены как часть источников; их упоминания других роботов/отсутствующих файлов не означают включение всех upstream assets.

| Каталог | Что включено | Назначение |
|---|---|---|
| unitree_sdk2 | SDK sources/headers, библиотеки x86_64/aarch64, examples, third-party licenses | Официальный low-level API, B2W sample и будущая сборка adapter |
| robot_lab | v2.3.2 extension code, scripts, B2W URDF и все его meshes | Training reference и эталон исходного robot asset; assets других роботов исключены |
| rl_sar | B2W policy.pt + configs, runtime sources и submodule declarations | Policy ABI, inference/control и sim2sim reference; submodule binaries отдельно не загружены |
| unitree_ros | Официальный B2W URDF, README, ROS1 package metadata и LICENSE | Сравнение с training asset без дублирования тяжёлых meshes |
| unitree_mujoco | B2W XML/scenes/meshes, C++/Python SDK2 bridges, examples и licenses | Sim2sim transport reference; исходники докачаны на прежнем commit |
| unitree_ros2 | Полные пакеты сообщений, C++ examples (включая B2W), setup scripts и LICENSE | ROS2/DDS integration; middleware и build dependencies устанавливаются отдельно |

Состав расширен 25 сентября 2026 по указанию пользователя. Исходные байты
сохранённых upstream-файлов не менялись. Подробная карта файлов, отсутствующих
зависимостей и роли каждого компонента — [VENDOR_INVENTORY](../docs/VENDOR_INVENTORY.md).

LauraMQuiros/b2w-rl исследован, но исходники не перепубликуются: LICENSE при просмотренной ревизии не найден. Commit записан как reference-only. Isaac Sim binaries не распространяются; Isaac Lab и NVIDIA runtime устанавливаются отдельно по выбранной версии и условиям NVIDIA.

Эти материалы — reference snapshot, не готовый собранный runtime. Перед `pip install`, CMake или запуском проверить зависимости/asset references. Никакой вендорский setup/build script при скачивании не исполняется. Не загружать pickle/checkpoint как доверенный произвольный код вне изолированного evaluation окружения.

Четыре SDK symlink-файла `thirdparty/lib/{aarch64,x86_64}/*.so.0` сохранены переносимо как текст цели ссылки; `upstream_mode=120000` указан в manifest. В отдельном Linux build tree восстановить эти symlinks перед запуском связанного SDK runtime; immutable vendor при этом не менять. Это не копии ELF libraries. Исполняемые биты upstream также отражены в manifest, но Windows snapshot не обещает их сохранение.

## Проверка и восстановление

```bash
python scripts/vendor_materials.py verify
# Restore missing/changed files using the locked hashes and GitHub DNS workaround:
python scripts/vendor_materials.py restore
```

Обновлять upstream только отдельным review: новый commit → проверка лицензий/контракта → новые hashes → regression tests. `fetch` предназначен для первоначальной сборки manifest и отказывается перезаписывать существующий lock.

Лицензии: Unitree — BSD-3-Clause; robot_lab/rl_sar — Apache-2.0. Проверять также вложенные `LICENSE`/`licenses` и notices third-party компонентов. Верхнеуровневая лицензия одного upstream не перелицензирует остальные проекты и новый код владельца.
