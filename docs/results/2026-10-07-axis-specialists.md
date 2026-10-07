# Independent lateral/yaw specialists

Два specialist независимо продолжены от неизменённого `core_24650`: seed 9914,
512 envs, по 150 PPO updates и 1 843 200 transitions. Flat/Rough для каждой
ветви содержали только полный pure-axis program своей оси; retention и лестничные
banks, MDP, reward, physics и PPO оставались прежними. Остальные команды в
экспортированных policy обслуживает parent через точный hard gate.

## Запуск

- Frozen spec: `configs/24650_axis_specialists_20261007.json`, SHA-256
  `ae397ac1762969cbfa8220c51b1143549b486f529658a43b2d9e2d4765bd28ca`.
- Первый job `78a400ef84f8496ebb7be95d2bb214f7` не выполнил ни одного update:
  неоднородное число cases выявило out-of-range индекс в диагностическом
  `StairMonitor`; последующее падение PhysX было следствием CUDA assert.
- Monitor исправлен так, чтобы case id индексировался только внутри активной
  cohort bank; добавлен regression test.
- Успешный job: `509c0f16fa00462aa5679b2c69f91eb5`, exit 0.
- Checkpoints iteration 24799:
  lateral `ec502c46edf099725da8c21ea01d803e2f23ce04935831ba4e938b86c198cf79`,
  yaw `4285050a12d7ac8c3fab417077e0f89d70e32a96b2f25011906ee28bc94de36e`.
- Result SHA-256:
  `5054f4dba35288f4ba0e8407d587ed1add6decaa1db5a9cabb21b0eb5176c9a9`.

## Результат probe, 60 episodes на actor

| Actor | Success | Unsafe | Lateral response | Yaw response |
|---|---:|---:|---:|---:|
| parent 24650 | 27/60 | 0 | 0.6831 | 0.6666 |
| lateral-only | 27/60 | 0 | 0.7628 | 0.6666 |
| yaw-only | 27/60 | 0 | 0.6831 | 0.6969 |
| axis-split | 27/60 | 0 | 0.7628 | 0.6969 |

Обе оси улучшились независимо и без изменения остальных cells, saturation и
safety. Точные cell minima: lateral flat `0.6711→0.7533`, rough
`0.4007→0.6429`; yaw flat `0.5549→0.6022`, rough `0.5932→0.6569`.
Однако ни один из десяти lateral и десяти yaw episodes не пересёк success gate:
paired outcomes для всех composites — 0 wins, 0 losses, 60 ties.

## Cumulative 300 и dense checkpoint curve

Продление обеих ветвей ещё на 150 updates показало, что больший бюджет сам по
себе вреден. У lateral-300 target response снизился до `0.6463`, причём rough
response практически схлопнулся; yaw-300 сохранил небольшой прирост до `0.6946`.
Combined остался `27/60`, но lateral retention gate уже не прошёл.

- Исправленный stage-2 job: `30230b40ad754b2e88d824cf28747e14`, exit 0.
- Stage-2 result SHA-256:
  `05a325e71f75466564a01faa229eb811cea64ad80336d279c65e045b93cd1816`.
- Dense lateral curve job: `fb994975e71d4bb08b95193dc0d8d367`, exit 0.
- Curve result SHA-256:
  `44edf6bad24ace7eb6f449919ed62ceee8e0f5ebfc7d180eb8f37c1e9deed64d`.

Парная 10-эпизодная curve нужна только для выбора окна, а не для acceptance.
Лучший минимум flat/rough получен на cumulative 177 (iteration 24825):
`0.7435/0.5031`. После 202 updates метрика стала нестабильной, а после 252–300
rough снова почти исчез. Выбран checkpoint 24825, SHA-256
`d1c3e7f5db5d2aa548698b31d2fb2395d1dad56d88d55e11dc9a8230c5ba887a`.

## Mixed lateral-177 + yaw-150

Hard-gated actor использует lateral-177 только для pure `vy`, yaw-150 только
для pure `omega_z`, а parent — для нуля, `vx` и смешанных команд. На 1536
fixture/random observations подтверждена точная branch parity, max error 0,
ABI 57→16. Export SHA-256:
`62a12eaf57a61b49c0fb846af9831b50291177c6c19343d0e3715d800e9d4cd6`.

Managed job `d24133183f5f4eeeb4a08bf33dae363f`, exit 0:

| Экран | Parent | Mixed | Paired | Unsafe |
|---|---:|---:|---:|---:|
| 60-episode probe | 27/60 | 30/60 | 3 wins, 0 losses, 57 ties | 0/0 |
| Full v2 | 107/160 | 112/160 | 5 wins, 0 losses, 155 ties | 0/0 |

На probe lateral response `0.6831→0.6993`, yaw `0.6666→0.6969`; success-cell
regressions отсутствуют. На full v2 tracking checks выросли `60/100→65/100`,
transitions `97/100→98/100`, traversal сохранился `48/60`; stop снизился на
один эпизод `148/160→147/160`, но итоговая парная success-метрика не имеет
losses. Максимальные leg/wheel saturation не выросли (`0.0074` и `0.13824`).
Все пять gains находятся только в lateral: `flat_mu_100` +2 и `rough_02` +3.
Yaw cells остались 0/5, а `rough_10/lateral` response minimum ухудшился примерно
`0.40→0.03`; общий `response_ratio_min` снизился `0.0451→0.0314`. Поэтому это
узкий success-positive finalist, а не равномерное улучшение envelope.
Full summary SHA-256:
`4e17f158713b735e3c932990ca211e8994b94957273ef143d0a3da56809c9d48`;
result SHA-256:
`3601feccdc6190998c07c061b888609823e4535722133479963ac17d6e5312eb`.

## Решение

- Первый 150-update результат был положительным только по response; cumulative
  300 отклонён из-за lateral collapse. Dense curve локализовала полезное окно.
- Mixed lateral-177/yaw-150 дал воспроизводимый положительный success-результат
  на probe и полном v2 без paired losses, unsafe или saturation regression.
- Однако `112/160` и `all_cells_pass=false` не являются acceptance. Поэтому
  `core_24650` остаётся development candidate; mixed — simulation finalist,
  promotion, qualification и hardware approval отсутствуют.
- Следующий шаг — не продлевать эти checkpoints вслепую. Нужно закрыть всё ещё
  нулевые/слабые lateral и yaw cells отдельным коротким checkpoint search вокруг
  найденного окна, сохраняя hard gate и используя full v2 только для заранее
  выбранных finalists.

## Полный endpoint screen и robust composite

Дополнительно проверены все сохранённые lateral endpoints 150/152/177/202/226/
252/300 и yaw 150/252/300 на четырёх full-v2 flat/rough axis cells. Parallel
screen `8fd3bdf17e2a49c19b92f865f2fd362f` использовался только для shortlist:
совместный simulation load заметно меняет отдельные response minima и потому не
является acceptance evidence. Последовательный confirm
`41f5c69a71d74097aef04964070a5be5`, result SHA-256
`dd8bce16ad2484547de3cee221a7a0fca36ba2da725e07acc087fa4653c5abe3`, выбрал:

- lateral-152: `7/20` против parent `5/20`, minimum `0.4261` против `0.4007`;
- yaw-252: `1/20` против parent `0/20`, minimum `0.6391` против `0.5549`.

Их composite job `45bef36fbc494066b753dea3d080c05e` дал full v2
`107/160→108/160`, paired `1/0/159`, unsafe 0, без success-cell/saturation
regressions; export SHA-256
`5f2edfc3bce9958da6022bb28dd871f317c8d969592c1ed3d06687892b7b0b4f`.
Однако в отдельном full run `rough_10/lateral` response оказался около `0.12`,
тогда как последовательный endpoint confirm того же actor дал `0.4261` при
exact branch parity.

Третий same-seed endpoint repeat `c8caf35261854cf3a6dab9223007ffd3`
(result SHA-256 `19db9686e613eb06af469f987310363701d96989e55df3dbae313d95a1d645b5`)
точно воспроизвёл первый axis-only run, включая lateral `0.4261` и yaw metrics.
Следовательно, различие не является обычной межзапусковой недетерминированностью:
axis-only protocol меняет порядок cases и тем самым RNG/reset slot относительно
full v2. Дешёвый endpoint screen пригоден для shortlist, но не для retention
claim. Авторитетный full result robust composite остаётся `108/160`, paired 1/0,
с `rough_10/lateral≈0.12`; promotion нет. Следующий screen обязан сохранять
полный prefix/order cases либо использовать полный v2.

После исправления monitor полный managed test job
`fd1bb4eb033d441f85f8385da9974519`: 121 tests, exit 0. После mixed-run job
`aecba2fedb0f4345a34d59362fbce9d7`: 124 tests, exit 0.
