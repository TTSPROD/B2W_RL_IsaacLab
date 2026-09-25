# Что находится в vendor

Проверено 25 сентября 2026: **1463 файла, 6 закреплённых источников**.
Это выбранные upstream snapshots; наличие файла не означает установленную
зависимость или проверенную сборку. Полные commit IDs, Git blob SHA-1, SHA-256,
размеры и licenses каждого файла — в [manifest](../vendor/manifest.json).

| Каталог | Commit | Файлов / MiB | Роль |
|---|---|---:|---|
| `unitree_sdk2` | `07493e4b5b46` | 879 / 82.24 | Официальный C++ SDK, DDS/IDL, libraries, hardware examples |
| `robot_lab` | `09f6a9dfdf48` | 248 / 81.64 | Isaac Lab extension v2.3.2, MDP/PPO configs, training scripts и B2W asset |
| `rl_sar` | `376d42c9b128` | 101 / 1.58 | C++ inference/control framework, B2W FSM, reference config/policy |
| `unitree_ros` | `ccfc6fd8430a` | 6 / 0.03 | Официальное ROS1/catkin описание B2W для сверки модели |
| `unitree_mujoco` | `1eb6642e3f3f` | 75 / 39.07 | B2W models/scenes, C++ и Python SDK2 simulator bridges |
| `unitree_ros2` | `668d1ec5a05d` | 154 / 2.26 | Unitree ROS2 v0.3.0: messages, C++ examples, DDS setup scripts |

## SDK2: интерфейс к моторам и штатным сервисам

В `unitree_sdk2/include/` находятся channel publisher/subscriber, IDL `LowCmd_` /
`LowState_`, robot clients, включая B2 MotionSwitcher/SportClient. В
`lib/{x86_64,aarch64}/` — `libunitree_sdk2.a`; в `thirdparty/lib/` — CycloneDDS
`libddsc.so`, `libddscxx.so`. В `thirdparty/include/` — DDS headers, в `licenses/` —
third-party licenses. Это Linux libraries, не готовый Windows runtime.

Основные примеры:

- [b2w_stand_example.cpp](../vendor/unitree_sdk2/example/b2w/b2w_stand_example.cpp): low-level motor commands, CRC, LowState и передача управления через MotionSwitcher.
- [b2w_sport_client.cpp](../vendor/unitree_sdk2/example/b2w/b2w_sport_client.cpp): вызовы штатного high-level Sport service. Он не исполняет нашу learned policy.
- [CMake SDK](../vendor/unitree_sdk2/CMakeLists.txt) и [upstream README](../vendor/unitree_sdk2/README.md): сборка/подключение SDK.

Четыре `.so.0` сохранены как текст symlink target согласно `upstream_mode=120000`.
Перед Linux build восстановить ссылки в отдельной build-копии. Готового firmware
контроллера B2W и проектного policy→SDK2 runtime в этом SDK нет.

## robot_lab: обучение и исходная модель

[unitree.py](../vendor/robot_lab/source/robot_lab/robot_lab/assets/unitree.py) задаёт
asset/actuators. B2W task находится в
`source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/`:
`flat_env_cfg.py`, `rough_env_cfg.py`, `agents/rsl_rl_ppo_cfg.py`, `agents/cusrl_ppo_cfg.py`.
Общие MDP observations/rewards/actions находятся в дереве tasks.

Сохранены upstream `scripts/reinforcement_learning/{rsl_rl,cusrl,skrl}/` и
[B2W URDF](../vendor/robot_lab/source/robot_lab/data/Robots/unitree/b2w_description/urdf/b2w_description.urdf)
со всеми его meshes. Isaac Sim, Isaac Lab runtime и trainer packages устанавливаются
отдельно; проектное локальное окружение описано в [INFRASTRUCTURE](INFRASTRUCTURE.md).
Upstream scripts остаются эталоном, их наличие не означает разрешённый новый run.

## rl_sar: inference и state machine

- [rl_sdk.cpp](../vendor/rl_sar/src/rl_sar/library/core/rl_sdk/rl_sdk.cpp): observations/actions, преобразование выходов и общий control framework.
- [fsm_b2w.hpp](../vendor/rl_sar/src/rl_sar/fsm_robot/fsm_b2w.hpp): Passive/GetUp/GetDown/RLLocomotion и переходы состояний.
- [B2W config](../vendor/rl_sar/policy/b2w/robot_lab/config.yaml), `policy/b2w/base.yaml` и `policy.pt`: upstream reference 57→16, scales/gains/mapping. Этот vendor policy — исходный reference, не серверный кандидат 19999 и не текущая оценка.
- `src/rl_sar/src/rl_sim*.cpp`, `rl_real_*.cpp`, `src/robot_joint_controller/{ros,ros2}/`, `src/robot_msgs/`: simulator interfaces, drivers других моделей, ROS controller plugins и сообщения.

Специализированного `rl_real_b2w.cpp` нет. Submodule declarations сохранены в
[.gitmodules](../vendor/rl_sar/.gitmodules), их содержимое автоматически не загружалось.
Runtime libraries вроде LibTorch/ONNX и build dependencies отдельно не поставлены
этим snapshot. Различия clipping/history с Isaac разобраны в [контракте](POLICY_CONTRACT.md).

## unitree_ros и unitree_ros2: разные компоненты

`unitree_ros` содержит только README/LICENSE/.gitmodules и B2W
[URDF](../vendor/unitree_ros/robots/b2w_description/urdf/b2w_description.urdf), README,
[package.xml](../vendor/unitree_ros/robots/b2w_description/package.xml).
Это ROS1/catkin metadata: meshes, launch files и ROS-драйвер здесь не сохранены.
Полный комплект B2W meshes уже есть в `robot_lab`.

`unitree_ros2` докачан из официального Unitree repository:

- `cyclonedds_ws/src/unitree/{unitree_go,unitree_api,unitree_hg}/`: полный набор `.msg`, `package.xml`, CMake. Для B2W используется семейство `unitree_go`; `unitree_api` описывает RPC requests/responses. `unitree_hg` сохранён как зависимость полного upstream example package.
- [LowCmd.msg](../vendor/unitree_ros2/cyclonedds_ws/src/unitree/unitree_go/msg/LowCmd.msg), [LowState.msg](../vendor/unitree_ros2/cyclonedds_ws/src/unitree/unitree_go/msg/LowState.msg): ROS2 представление low-level DDS данных.
- [B2W stand](../vendor/unitree_ros2/example/src/src/b2w/b2w_stand_example.cpp), [B2W sport](../vendor/unitree_ros2/example/src/src/b2w/b2w_sport_client.cpp), [read_low_state](../vendor/unitree_ros2/example/src/src/read_low_state.cpp), common CRC/clients и остальные sources: полный example package для сохранения CMake dependencies.
- `setup.sh`, `setup_local.sh`, `setup_default.sh`, `cyclonedds_ws/src/cyclonedds.xml`: upstream DDS environment examples. В setup scripts есть исходные Foxy/home paths; адаптировать вне vendor, не source вслепую.

Сам дистрибутив ROS2, `rmw_cyclonedds_cpp`, colcon, rosidl generators, Eigen и
rosbag2 не включены. Название `cyclonedds_ws` не означает наличие исходников всего
CycloneDDS. ROS2 интеграция B2W policy и round-trip SDK2↔ROS2 ещё не проверены.
Официальные требования: [Unitree ROS2 README](https://github.com/unitreerobotics/unitree_ros2).

## unitree_mujoco: модель и simulator bridge

- [b2w.xml](../vendor/unitree_mujoco/unitree_robots/b2w/b2w.xml), `scene.xml`, `scene_terrain.xml`, heightmaps и meshes: B2W model assets.
- [unitree_sdk2_bridge.h](../vendor/unitree_mujoco/simulate/src/unitree_sdk2_bridge.h), `main.cc`, [CMake](../vendor/unitree_mujoco/simulate/CMakeLists.txt), [config](../vendor/unitree_mujoco/simulate/config.yaml): C++ simulator и DDS bridge; также joystick/lodepng sources с licenses.
- [unitree_sdk2py_bridge.py](../vendor/unitree_mujoco/simulate_python/unitree_sdk2py_bridge.py), `unitree_mujoco.py`, `config.py`: Python-вариант.
- `example/{cpp,python,ros2}/`: upstream stand-примеры для Go2, не B2W policy runtime. `readme.md`, `readme_zh.md`, `doc/`: upstream инструкции и схемы.

Добавлены 33 файла на **том же commit**; ранее сохранённые B2W XML/meshes не менялись.
По [upstream build instructions](../vendor/unitree_mujoco/readme.md) C++ сборка требует
отдельный MuJoCo release с headers/libs/simulate sources (в примере 3.3.6), GLFW,
Boost, yaml-cpp, fmt и установленный SDK2. Это не автоматически эквивалентно
локальному Python MuJoCo 3.14.0. Для Python bridge отдельно нужен `unitree_sdk2_python`.
Engine binaries и middleware не докачивались в source snapshot. По умолчанию
upstream config выбирает Go2: B2W/domain/interface задавать проектной конфигурацией
вне vendor. Сборка и DDS smoke test остаются этапом S2.

## Проверка и дальнейшее использование

```powershell
python scripts/vendor_materials.py verify
```

Докачанные файлы проверены по pinned Git tree/blob и SHA-256; сохранённые файлы
прочих snapshots не изменены. Новые adaptations, build outputs и runtime config
должны находиться вне vendor. Порядок интеграции — [PROJECT_PLAN](PROJECT_PLAN.md)
и [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md).
