# B2W: первичные источники и маршрут deployment

Дата проверки: 2026-09-17. Ниже разделены наблюдения по upstream и предлагаемые решения проекта. Ссылки на `main`/`master` нужны для навигации; воспроизводимые загрузки должны использовать commit SHA из vendor manifest. Сетевых подключений к роботу при подготовке документа не выполнялось.

## 1. Как использовать источники

| Источник | Роль в проекте | Граница применимости |
|---|---|---|
| [Unitree SDK2](https://github.com/unitreerobotics/unitree_sdk2) | DDS, структура команд и состояний, управление штатным motion service | SDK передаёт команды; полноценный RL runtime, ограничения и watchdog создаются отдельно |
| [Unitree ROS B2W description](https://github.com/unitreerobotics/unitree_ros/tree/master/robots/b2w_description) | URDF, геометрия, массы, инерции, имена суставов | Зафиксировать конкретную ревизию; параметры отличаются от официального MJCF |
| [Unitree MuJoCo B2W](https://github.com/unitreerobotics/unitree_mujoco/tree/main/unitree_robots/b2w) | Независимый симулятор и официальный DDS bridge | Перед sim2sim согласовать физические параметры с training asset |
| [SRU robot deployment](https://github.com/leggedrobotics/sru-robot-deployment) | Альтернативная ONNX locomotion policy, recurrent inference, ROS/Gazebo reference | Навигационная SRU policy и locomotion policy — разные уровни; не подменять ими контракт `robot_lab` |
| [LauraMQuiros/b2w-rl](https://github.com/LauraMQuiros/b2w-rl) | Дополнительный опыт с совместным управлением ногами/колёсами | Исследовательский flat-ground пример; использовать как материал для анализа |

Основной baseline проекта остаётся `rl_sar/policy/b2w/robot_lab`. Альтернативные политики проходят отдельную оценку через собственный observation/action adapter; переносить веса между несовпадающими контрактами нельзя.

## 2. Официальный низкоуровневый интерфейс

В [B2W stand example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp) используются `unitree_go::msg::dds_::LowCmd_` и `LowState_` из каталога `idl/go2`. Это корректный для данного примера namespace, несмотря на B2W в имени робота. DDS topics: `rt/lowcmd`, `rt/lowstate`. Пример публикует каждые 2000 мкс, то есть 500 Hz; это частота примера, а не установленная нами гарантия firmware. Инициализируются 20 слотов; ноги занимают 0–11, колёса 12–15. Команда содержит `q`, `dq`, `kp`, `kd`, `tau`; перед публикацией считается CRC. Пример вызывает `CheckMode`/`ReleaseMode`, чтобы исключить конкуренцию со штатным motion controller. У колёс `kp=0`, управление идёт через `dq` и `kd`. Значения `Kp=1000`, `Kd=10` относятся к демонстрационному stand routine, а не к настройке нашей политики.

[LowState_.hpp](https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/idl/go2/LowState_.hpp) содержит IMU, 20 motor states, BMS, `tick`, remote и другие поля. Отдельного поля линейной скорости корпуса в этом сообщении нет. Поэтому actor, требующий `base_lin_vel`, нуждается в проверенном estimator/odometry либо обучении другой архитектуры. Само наличие `foot_force` в IDL не подтверждает достоверность измерения контакта колеса на конкретной ревизии B2W.

Официальный [MuJoCo DDS bridge](https://github.com/unitreerobotics/unitree_mujoco/blob/main/simulate_python/unitree_sdk2py_bridge.py) реализует следующую модель смешанной команды:

`tau_total = tau_ff + kp * (q_des - q) + kd * (dq_des - dq)`.

Это удобная точка проверки эквивалентности training actuator и SDK adapter. Зафиксировать также saturation, задержку и частоту обновления: совпадение одной формулы не гарантирует одинаковую динамику.

## 3. Порядок приводов и различия assets

В официальном [MJCF](https://github.com/unitreerobotics/unitree_mujoco/blob/main/unitree_robots/b2w/b2w.xml) порядок actuator/sensor: FR hip/thigh/calf, FL hip/thigh/calf, RR hip/thigh/calf, RL hip/thigh/calf, затем FR/FL/RR/RL wheel. Это опорный порядок для DDS sim adapter, который обязательно перепроверяется на целевом железе.

Для политики с порядком `[FL,FR,RL,RR]` внутри групп hip/thigh/calf/wheel проектная перестановка будет:

```text
sdk_vector = policy_vector[[1,5,9, 0,4,8, 3,7,11, 2,6,10, 13,12,15,14]]
policy_vector = sdk_vector[[3,0,9,6, 4,1,10,7, 5,2,11,8, 13,12,15,14]]
```

Это вывод из имён, а не универсальная перестановка любого checkpoint. В каждом экспортном пакете хранить обе таблицы имён и явное соответствие. Знаки осей, IMU quaternion convention и направление качения проверяются отдельно; перестановка не исправляет неверный знак.

В [официальном URDF](https://github.com/unitreerobotics/unitree_ros/blob/master/robots/b2w_description/urdf/b2w_description.urdf) заданы:

| Сустав | Position, rad | Effort, Nm | Velocity, rad/s |
|---|---:|---:|---:|
| Hip | −0.87…0.87 | 200 | 23 |
| Thigh | −0.94…4.69 | 200 | 23 |
| Calf | −2.82…−0.43 | 320 | 14 |
| Foot / wheel | continuous | 20 | 50 |

URDF называет колёса `*_foot_joint`, MJCF — `*_wheel_joint`. В MJCF ограничение calf motor составляет ±300 Nm; масса base link равна 40.8426 kg. В URDF масса base link 35.606 kg, часть массы задана отдельными fixed links; отличаются также инерции и массы конечностей. Сравнивать только base mass некорректно: нужна сумма масс и приведённые инерции после одинакового объединения fixed links.

На [странице B2-W производителя](https://www.unitree.com/b2-w/) указаны примерно 85 kg с батареей, диаметр колеса 225 mm, максимум 50 rad/s и 40 Nm для колеса, последовательные ступени 20–25 cm. Производитель оговаривает зависимость характеристик от конфигурации. Это не означает, что training/SDK limits следует поднять с 20 до 40 Nm: сначала уточнить непрерывный/пиковый режим, hardware revision и допустимый профиль нагрузки. Успешный рекламный подъём не является приёмкой нашей политики на промышленной лестнице.

**Решение проекта:** хранить исходные URDF/MJCF отдельно и неизменными; создавать наш нормализованный asset с таблицей преобразований. Для baseline воспроизводить asset и параметры выбранного training upstream. Перед sim2sim устранить случайные различия моделей; контролируемую вариацию параметров вводить уже как тест устойчивости.

## 4. Что именно находится в SRU deployment

[README SRU](https://github.com/leggedrobotics/sru-robot-deployment) разделяет locomotion 50 Hz inference / 200 Hz output и navigation 5 Hz. Навигация выдаёт целевую скорость; она не заменяет управление 16 приводами. Инструкции real deployment требуют адаптации hardware launch, поэтому наличие README не доказывает готовность нашего экземпляра B2W к запуску.

В [header контроллера](https://github.com/leggedrobotics/sru-robot-deployment/blob/main/b2w_sim/b2w_controllers/include/b2w_controllers/b2w_controllers.hpp) зафиксированы 16 outputs, 60 observations, hidden size 256. Контроллер передаёт в ONNX два recurrent состояния `h` и `c`.

По [реализации inference](https://github.com/leggedrobotics/sru-robot-deployment/blob/main/b2w_sim/b2w_controllers/src/b2w_controllers.cpp) observation состоит из `v_base(3), omega_base(3), gravity(3), command(3), q_relative(16), dq(16), previous_action(16)`. Позиции, включая колёса, приведены к интервалу `[-2π,2π)`; это не обычное wrapping в `[-π,π)`. Скорости поступают из odometry, а gravity вычисляется через транспонированную матрицу ориентации. До первого odometry inference не стартует. Отсюда требования адаптера: проверить frame скорости, корректно вести `h/c`, сбрасывать память при новом эпизоде, воспроизвести wrapping. В нашем runtime отдельно нужны проверки возраста всех входов и NaN/Inf, которые не следует считать обеспеченными этим reference.

В [YAML SRU](https://github.com/leggedrobotics/sru-robot-deployment/blob/main/b2w_sim/b2w_controllers/config/b2w_controllers.yaml) выбран `policy/policy_force_new.onnx`; суставы сгруппированы hip/thigh/calf/foot, внутри группы FL/FR/RL/RR. Leg action scale = 0.5, wheel scale = 5.0; nominal legs = hip 0, thigh 0.4, calf −1.3. Это коэффициенты преобразования, а не доказанные абсолютные ограничения выхода сети. YAML `reorder_indices` относится к порядку входного ROS JointState; использовать его как SDK motor mapping нельзя.

**Решение проекта:** SRU оставить отдельным benchmark. Сначала проверить сам ONNX: SHA256, op types, названия и shapes inputs/outputs, recurrent reset и численную воспроизводимость. Политика с odometry не получает честного сравнения с proprioceptive actor, если в симуляции ей подать идеальную скорость, а deployment estimator не определён.

## 5. Оценка LauraMQuiros/b2w-rl

[README](https://github.com/LauraMQuiros/b2w-rl) описывает Isaac Lab v1.2.0 / Isaac Sim 4.2 и flat-ground результат. Заявленные скорость обучения и reward — данные автора без независимого воспроизведения. Видимый корень репозитория не содержит LICENSE; поэтому в vendor входит ссылка/метаданные и наш анализ, а перенос исходников отложен до подтверждения разрешения. Указанные в README 60 kg расходятся с текущей страницей B2-W производителя.

В [hybrid environment](https://github.com/LauraMQuiros/b2w-rl/blob/master/b2w_hybrid_env.py) используются plane terrain, actor observation 40D с идеальной линейной скоростью, 16 действий, масштабы 0.5 для ног и 10 для колёс, physics 200 Hz / policy 50 Hz. Предыдущего действия в observation нет. Reward за вращение колёс пропорционален абсолютной скорости колёс и команде. Наша оценка: этот reward может поощрять буксование, поэтому его нельзя считать мерой эффективности движения; нужна оценка slip и потреблённой энергии. `low_velocity_timeout` фактически не содержит таймера: завершение может наступить сразу при ненулевой команде и малой скорости. Для лестниц, где полезны остановка и перестановка ноги, такой критерий требует пересмотра.

В [robot config](https://github.com/LauraMQuiros/b2w-rl/blob/master/b2w_cfg.py) прописан абсолютный путь к USD, self-collision и contact sensors отключены; calf velocity limit 23 rad/s отличается от 14 rad/s в официальном URDF. Эти параметры не переносить в проект автоматически. Полезная идея источника — единое пространство mixed actions; готовность к rough/stairs или реальному deployment данным кодом не установлена.

## 6. Рекомендуемый набор vendor

Для каждого компонента сохранять URL, branch/tag для человека, полный commit SHA, upstream path, локальный путь, размер, SHA256, лицензию и дату. Vendor payload нельзя молча исправлять: проектные изменения хранятся отдельными patch/config файлами. Snapshot должен включать все mesh/texture dependencies выбранного asset.

| Upstream | Точные пути для загрузки | Лицензии и назначение |
|---|---|---|
| `unitreerobotics/unitree_sdk2` | `LICENSE`, `README.md`, `licenses/**`, `example/b2w/**`, `include/unitree/idl/go2/**`, `include/unitree/robot/b2/**`; для сборки весь зафиксированный SDK с `cmake/`, `include/`, `lib/`, `thirdparty/`, `CMakeLists.txt` | [BSD-3-Clause](https://github.com/unitreerobotics/unitree_sdk2/blob/main/LICENSE); сохранить также все [third-party notices](https://github.com/unitreerobotics/unitree_sdk2/tree/main/licenses) |
| `unitreerobotics/unitree_ros` | `LICENSE`, `robots/b2w_description/urdf/b2w_description.urdf`, `robots/b2w_description/meshes/**`, `robots/b2w_description/xacro/**`, `robots/b2w_description/package.xml`, `robots/b2w_description/README.md` | [BSD-3-Clause](https://github.com/unitreerobotics/unitree_ros/blob/master/LICENSE); исходная геометрия и физика |
| `unitreerobotics/unitree_mujoco` | `LICENSE`, `README.md`, `unitree_robots/b2w/**`, `simulate_python/unitree_sdk2py_bridge.py`; для рабочего симулятора весь `simulate_python/**` либо `simulate/**` со сборочными файлами | [BSD-3-Clause](https://github.com/unitreerobotics/unitree_mujoco/blob/main/LICENSE); независимый physics/DDS reference |
| `leggedrobotics/sru-robot-deployment` | `LICENSE`, `README.md`, `b2w_sim/README.md`, `b2w_sim/b2w_controllers/config/b2w_controllers.yaml`, `b2w_sim/b2w_controllers/src/b2w_controllers.cpp`, `b2w_sim/b2w_controllers/include/b2w_controllers/b2w_controllers.hpp`, `b2w_sim/b2w_controllers/policy/policy_force_new.onnx`, `b2w_sim/b2w_controllers/package.xml`, `b2w_sim/b2w_controllers/CMakeLists.txt` | [MIT](https://github.com/leggedrobotics/sru-robot-deployment/blob/main/LICENSE), также указан в package.xml. Для полной ROS сборки отдельно проверить licenses bundled ONNX Runtime и зависимостей |
| `LauraMQuiros/b2w-rl` | Только source URL, revision metadata и собственные заметки | В просмотренном корне LICENSE не найден; сам код не включать в распространяемый snapshot |

Список выше — рекомендация состава. Фактическую комплектность, размеры, наличие весов и ревизии подтверждает vendor manifest; этот документ не утверждает, что любой файл уже загружен или проверен запуском.

## 7. Этапы sim2sim → sim2real

Ниже предлагаемые engineering gates проекта, а не обещанные характеристики upstream.

1. **Policy contract.** Экспортировать модель, normalizer, порядок и единицы observation/action, частоты, history/recurrent reset, nominal pose, scales и limits. На сохранённом observation replay сравнить Python trainer и C++/ONNX runtime; заранее задать допуск float32, например absolute error ≤1e-5, либо обосновать другой для конкретного backend.
2. **Asset audit.** Проверить 16 приводов, joint order/sign, total mass/COM/inertias, пределы скорости и момента, коллизию колёс, contact offset, friction и PD. Убедиться, что training asset и sim2sim asset отличаются только документированными параметрами.
3. **Isaac → MuJoCo.** Гонять один exported checkpoint по фиксированным flat/rough/stairs сценариям и seed, записывать tracking error, падения, проскальзывание, удары корпуса, лимиты приводов и энергию. Сравнить с baseline на одинаковых командах. Разделить воспроизведение номинальной модели и stress tests по friction/mass/latency.
4. **DDS в симуляции.** Тот же deployment executable подключить к loopback DDS bridge в отдельном domain; убедиться, что сеть реального робота не задействована. Инжектировать потерю/задержку state, остановку inference, неверный shape, NaN и stale command. Проверить, что runtime переходит в заранее определённое bounded состояние, а не продолжает последний motion command бесконечно.
5. **Подготовка целевого B2W.** Зафиксировать hardware/firmware, фактические limits, battery/payload, IMU convention, network interface и процедуру передачи управления. Сначала passive logging без LowCmd и без ReleaseMode, затем численное сравнение observation и shadow inference. Окончательная схема graceful stop выбирается по документации конкретного робота: простое обнуление всех gains/torques не считать универсально безопасной остановкой.
6. **Физическая приёмка.** Отдельные испытания mapping и направления колёс на стенде с ограниченными командами, затем stand/flat с малой скоростью, rough и обычные ступени. Обязательны операторский stop/deadman, журнал timing/состояний, ограничения скорости/момента/изменения команд и исключение двух активных контроллеров. Thresholds watchdog выбираются по измеренной задержке и тестируются до свободного движения.
7. **Промышленные лестницы.** Отдельный набор измеренных геометрий и материалов: глубина проступи, высота, открытые подступенки, решётка, кромка, площадки, ширина, повороты, сцепление. Обучать подъём и спуск; проверять остановку/возобновление и переходы на площадку. Для решётки и открытых ступеней нужен явный mesh/contact model: обычный heightfield не воспроизводит отверстия и нависающую геометрию. Решение о perception policy принимается после сравнения blind baseline с ограничениями реальной площадки.

Контур на роботе: state acquisition → frame/joint adapter → observation builder → policy inference → action scaling/limits → SDK packet/CRC → publisher. Safety state machine и watchdog работают независимо от успешности policy inference. Предлагаемый стартовый бюджет — inference 50 Hz и отдельный publisher 500 Hz, с измерением p95/p99/max задержек и пропусков; конкретные частоты закрепляются после проверки baseline и firmware.
