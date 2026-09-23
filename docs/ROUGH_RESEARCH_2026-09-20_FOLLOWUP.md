# Rough: уточнение после corridor63/64

Проверено 20.09.2026 по первичным источникам и локальным результатам.
Дополнение к [предыдущему исследованию](ROUGH_RESEARCH_2026-09-20.md);
прежние результаты и решения остаются историческими записями.
Внешние реализации в рамках этой проверки не запускались.

## Последний результат и следующий вопрос

[Corridor63/64](results/rough_corridor_training_20260920.json) остановлен
на150 updates со статусом `stopped_quality_gate`. Все четыре Flat suites
сохранили100/100 без падений и абсолютные пороги, но только одна прошла
относительную regression к anchor54. Следовательно, новый запуск нельзя
считать сохранением прежнего Flat качества.

Опыт одновременно добавил два воздействия: sticky wheel crossing как
отказ curriculum и ранний true terminal эпизода. Ранний terminal меняет
горизонт доходности, bootstrap и распределение посещаемых состояний.
Поэтому его эффект следует отделить от исправления curriculum.
Это гипотеза о причине ухудшения, а не установленный результат.

В [логе seed63](../logs/rough/rough_corridor_training_20260920/s63_to150/console.log)
на последней итерации mean reward составляет+173.90; episode terms:
`upward` +6.2563, linear tracking +1.2953, yaw tracking +0.6781.
Гипотеза, что агент завершает эпизоды ради избегания в целом отрицательной
награды, этими данными не подтверждается. Эти средние также не объясняют
индивидуальные advantages у границы corridor.

## Что подтверждают проверенные источники

- [Официальный Unitree RL Lab: Go2 config](https://raw.githubusercontent.com/unitreerobotics/unitree_rl_lab/main/source/unitree_rl_lab/unitree_rl_lab/tasks/locomotion/robots/go2/velocity_env_cfg.py).
  Actor использует angular velocity, gravity, commands, joints и previous
  action; linear velocity доступна critic. История наблюдений закомментирована.
  В проверенной версии активен flat terrain; rough/stairs примеры
  закомментированы. Слепой actor сам по себе не является ошибкой, но этот
  пример не подтверждает приёмку B2W Rough. Tracking kernel использует
  std0.5; перенос конкретного std или contact rewards требует отдельного опыта.

- [Unitree PPO config](https://raw.githubusercontent.com/unitreerobotics/unitree_rl_lab/main/source/unitree_rl_lab/unitree_rl_lab/tasks/locomotion/agents/rsl_rl_ppo_cfg.py).
  Используются rollout24, MLP512/256/128, PPO clip0.2, пять epochs,
  четыре minibatches, adaptive learning rate, desired KL0.01,
  gamma0.99 и lambda0.95. Это исходный рецепт, а не основание заменять
  уже измеренные настройки fine-tuning B2W или увеличивать бюджет вслепую.

- [Unitree command curriculum](https://raw.githubusercontent.com/unitreerobotics/unitree_rl_lab/main/source/unitree_rl_lab/unitree_rl_lab/tasks/locomotion/mdp/curriculums.py).
  Диапазон команд расширяется на0.1 после достижения среднего tracking
  reward выше80% его максимума. Сложность увеличивают по качеству решения;
  сам факт завершения training iterations не служит критерием продвижения.

- [Isaac Lab terrain curriculum](https://raw.githubusercontent.com/isaac-sim/IsaacLab/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/mdp/curriculums.py).
  Стандартное повышение уровня зависит от пройденной дистанции; понижение —
  от недобора половины ожидаемого пути. Нарушения нашего узкого corridor
  эта функция не проверяет. Поэтому wheel-aware failure остаётся необходимой
  частью локального curriculum, даже если ранний terminal отключён.

- [Lee et al., Science Robotics2024](https://arxiv.org/html/2405.01792v1),
  Low-level Policy Details, Filtering Terrain Parameters, Privileged Training.
  Для колёсно-ногого робота применены12 position actions и4 wheel velocities,
  privileged teacher и recurrent student с шумными измерениями и height map.
  Terrain отбирается по проходимости; tracking error используется как часть
  оценки успеха. Navigation выдаёт commands отдельному locomotion controller.
  Это поддерживает разделение tracking и corridor success, а не обещает
  автоматическое решение corridor нашим memoryless actor57.

- [Isaac Lab feet_slide](https://raw.githubusercontent.com/isaac-sim/IsaacLab/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/mdp/rewards.py).
  Штраф использует линейную скорость foot body при контакте. Прямое применение
  к центрам вращающихся колёс штрафовало бы нормальное качение; это вывод из
  формулы, а не опубликованный B2W эксперимент. Для B2W нужны отдельные
  определения rolling/slip, поэтому gait/feet rewards Go2 не копируются.

Ссылки на `main` отражают просмотренную20.09.2026 версию, не обещают
неизменность upstream. Локальный `vendor/` не менялся.

## Конечное решение по запросу пользователя: широкий учебный corridor65/66

Пользователь предложил расширить corridor. До запуска новой работы выбран
[отдельный опыт](ROUGH_WIDE_CORRIDOR.md): только учебная lateral half-width
увеличивается с0,9 до1,8м. Продольные границы x[−0,6;5,4] не меняются;
true wheel terminal, sticky crossing telemetry и запрет curriculum promotion
при нарушении новой границы сохраняются. Ширина3,6м помещается внутри tile12×12.

Сохраняются actor57/actions16, precision tracking, route sampler, tilt terminal,
Flat replay, qualified anchor54 и замороженные evaluation gates. Evaluation
по-прежнему требует y∈[−0,9;0,9]. Поэтому увеличение тренировочного пространства
не позволяет объявить успехом большее отклонение маршрута при приёмке.

Цель — проверить, даст ли более длинная траектория обучения больше примеров
stand/turn после approach, не удаляя механизм true terminal. Это гипотеза
о распределении обучающих данных: расширение также уменьшает давление на
точность бокового движения и само по себе не гарантирует прохождение узкой
проверки. Не меняются одновременно reward weights, observation ABI или commands.

Ранее рассмотренная абляция с удалением только terminal (curriculum-only)
не запускалась и заменена этим решением до simulator preflight.
Исторические61/62 и63/64 имеют другие seeds, поэтому сравнение не является
парным причинным экспериментом. Оба новых seeds показываются целиком;
возврат к качеству61/62 без прохождения Rough gates будет диагностическим
улучшением, а не приёмкой политики.

Если новый опыт не решит проблему, следующий анализ разделяет signed yaw bias,
body-frame lateral slip и накопленное отклонение мирового маршрута.
Privileged actor с добавленной linear velocity и последующая distillation
history estimator остаются отдельной архитектурной веткой. Добавление трёх
скоростей не сообщает actor абсолютный heading или расстояние до corridor;
такой teacher требует новой проверки наблюдений, экспорта и sim2sim.
Реальный робот и аппаратная приёмка этим исследованием не разрешаются.
