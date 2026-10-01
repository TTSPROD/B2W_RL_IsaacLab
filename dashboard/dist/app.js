'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const integer = value => Number(value ?? 0).toLocaleString('ru-RU', {maximumFractionDigits:0});
const numeric = value => value == null || !Number.isFinite(value) ? '—' : Math.abs(value) > 0 && Math.abs(value) < .001 ? value.toExponential(2) : value.toLocaleString('ru-RU', {maximumFractionDigits:Math.abs(value) < 10 ? 3 : 1});
const duration = seconds => seconds == null ? '—' : `${Math.floor(seconds / 3600)} ч ${Math.floor(seconds % 3600 / 60)} мин`;
const date = iso => new Date(iso).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
let data = null, selection = null, currentView = 'overview', selectedRun = '', busy = false, smoothing = .6, followLatest = true;
const titles = {
 'Train/mean_reward':'Средняя награда', 'Train/mean_episode_length':'Длина эпизода, шаги',
 'Train/mean_reward/time':'Средняя награда по времени', 'Train/mean_episode_length/time':'Длина эпизода по времени',
 'Metrics/base_velocity/error_vel_xy':'Ошибка линейной скорости', 'Metrics/base_velocity/error_vel_yaw':'Ошибка угловой скорости',
 'Loss/value_function':'Ошибка value function', 'Loss/surrogate':'PPO surrogate loss', 'Loss/entropy':'Энтропия policy',
 'Loss/learning_rate':'Learning rate', 'Policy/mean_noise_std':'Исследование · среднее σ',
 'Perf/total_fps':'Производительность, steps/s', 'Perf/collection time':'Сбор rollout, с', 'Perf/learning_time':'Обновление PPO, с',
 'Curriculum/terrain_levels':'Средний уровень terrain', 'Episode_Termination/time_out':'Завершение по времени',
 'Episode_Termination/terrain_out_of_bounds':'Выход за пределы terrain',
 'Focus/training_zero_windows':'Учебные окна нуля', 'Focus/training_zero_passes':'Успешный ноль · training',
 'Focus/training_stair_tile_zero_windows':'Окна нуля на stair tiles', 'Focus/training_stair_tile_zero_passes':'Успешный ноль на stair tiles',
 'Focus/scheduled_stair_stop_starts':'Запланированные остановки на лестницах',
 'Episode_Reward/lin_vel_z_l2':'Reward · вертикальная скорость', 'Episode_Reward/ang_vel_xy_l2':'Reward · угловая скорость XY',
 'Episode_Reward/joint_torques_l2':'Reward · момент суставов', 'Episode_Reward/joint_acc_l2':'Reward · ускорение суставов',
 'Episode_Reward/joint_pos_limits':'Reward · пределы суставов', 'Episode_Reward/joint_power':'Reward · мощность суставов',
 'Episode_Reward/stand_still':'Reward · неподвижность', 'Episode_Reward/joint_pos_penalty':'Reward · положение суставов',
 'Episode_Reward/joint_mirror':'Reward · симметрия', 'Episode_Reward/action_rate_l2':'Reward · изменение actions',
 'Episode_Reward/undesired_contacts':'Reward · нежелательные контакты', 'Episode_Reward/contact_forces':'Reward · контактные силы',
 'Episode_Reward/track_lin_vel_xy_exp':'Reward · tracking линейной скорости', 'Episode_Reward/track_ang_vel_z_exp':'Reward · tracking yaw',
 'Episode_Reward/feet_contact_without_cmd':'Reward · опора при нуле', 'Episode_Reward/upward':'Reward · вертикальная ориентация',
 'Episode_Reward/joint_acc_wheel_l2':'Reward · ускорение колёс'
};
const terrainNames = {flat:'Flat',flat_mu_40:'Flat μ 0.4',flat_mu_70:'Flat μ 0.7',flat_mu_100:'Flat μ 1.0',rough_02:'Rough ±2 см',rough_04:'Rough ±4 см',rough_06:'Rough ±6 см',rough_10:'Rough ±10 см',boxes_10:'Блоки 5–10 см',slope_up_10:'Уклон +10°',slope_down_10:'Уклон −10°',stairs_up_06:'Лестница ↑ 6 см',stairs_down_06:'Лестница ↓ 6 см',stairs_up_12:'Лестница ↑ 12 см',stairs_down_12:'Лестница ↓ 12 см',stairs_up_18:'Лестница ↑ 18 см',stairs_down_18:'Лестница ↓ 18 см'};
const overviewTags = ['Train/mean_reward','Metrics/base_velocity/error_vel_yaw','Train/mean_episode_length','Metrics/base_velocity/error_vel_xy','Loss/value_function','Loss/surrogate','Loss/entropy','Curriculum/terrain_levels'];
const latest = tag => data?.series[tag]?.at(-1)?.[1];
function stat(label, value, detail, extra = '') { return `<article class="stat"><div class="stat-label">${label}</div><div class="stat-number">${value}</div>${extra}<div class="stat-detail">${detail}</div></article>`; }
function row(label, value) { return `<div class="config-row"><span>${escapeHtml(label)}</span><span>${value}</span></div>`; }
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
async function getJson(url) { const response = await fetch(url, {cache:'no-store',signal:AbortSignal.timeout(15000)}); if (!response.ok) throw Error(`HTTP ${response.status}`); return response.json(); }

function chart(tag) {
 const values = (data.series[tag] || []).filter(item => item[1] != null);
 const title = titles[tag] || tag.split('/').slice(1).join(' / ');
 const head = `<div class="chart-head"><div><h3 class="chart-name">${escapeHtml(title)}</h3><span class="chart-tag">${escapeHtml(tag)}</span></div><span class="chart-value">${numeric(values.at(-1)?.[1])}</span></div>`;
 if (!values.length) return `<article class="chart-card">${head}<div class="chart-empty">Пока нет завершённых эпизодов</div></article>`;
 const smoothed = []; let last = values[0][1];
 for (const point of values) { last = last * smoothing + point[1] * (1 - smoothing); smoothed.push(last); }
 let low = Math.min(...values.map(p=>p[1])), high = Math.max(...values.map(p=>p[1]));
 const padding = (high - low) * .12 || Math.abs(high) * .06 || .1;
 low -= padding; high += padding;
 const gridElement = currentView==='metrics' ? $('allCharts') : $('overviewCharts');
 const columns = innerWidth<=590 ? 1 : 2;
 const viewWidth = Math.max(280, Math.floor((gridElement.clientWidth-(columns-1)*16)/columns-(innerWidth<=850?26:38)));
 const left=59, top=15, width=viewWidth-left-12, height=174, xmin=values[0][0], xmax=values.at(-1)[0];
 const x = step => left + (step - xmin) / (xmax - xmin || 1) * width;
 const y = value => top + height - (value - low) / (high - low) * height;
 const path = points => points.map((point,index)=>`${index?'L':'M'}${x(point[0]).toFixed(2)},${y(point[1]).toFixed(2)}`).join(' ');
 const raw = path(values), curve=path(values.map((point,index)=>[point[0],smoothed[index]]));
 const grid = [0,.5,1].map(fraction=>{const py=top+fraction*height;return `<line class="gridline" x1="${left}" x2="${left+width}" y1="${py}" y2="${py}"/><text x="${left-10}" y="${py+4}" text-anchor="end">${numeric(high-fraction*(high-low))}</text>`;}).join('');
 const ticks = [0,.5,1].map(fraction=>`<text x="${left+fraction*width}" y="214" text-anchor="${fraction===0?'start':fraction===1?'end':'middle'}">${integer(xmin+fraction*(xmax-xmin))}</text>`).join('');
 return `<article class="chart-card">${head}<svg class="chart" data-tag="${escapeHtml(tag)}" viewBox="0 0 ${viewWidth} 224" role="img" aria-label="${escapeHtml(title)}: ${values.length} точек, последнее значение ${numeric(values.at(-1)[1])}">${grid}<path class="raw" d="${raw}"/><path class="smooth" d="${curve}"/>${ticks}</svg><div class="chart-caption"><span>${tag.endsWith('/time')?'Время обучения, с':'Итерация'}</span><span>${integer(values.length)} точек · EMA ${smoothing.toFixed(2)}</span></div></article>`;
}

function renderHeading() {
 if (!data) return;
 const p=data.progress, m=data.manifest;
 const labels={running:'Обучение идёт',completed:'Завершено',failed:'Ошибка запуска',cancelled:'Остановлено',stale:'Нет свежих данных',initializing:'Инициализация'};
 $('runStatus').className=`status ${data.status}`;
 $('runStatus').textContent=labels[data.status] || data.status;
 const isSelection=currentView==='selection';
 $('pageTitle').textContent=isSelection?'Оценка checkpoint’ов':`${m.parent_iteration} → ${m.parent_iteration+m.additional_updates}`;
 $('pageEyebrow').textContent=isSelection?'CORE LOCOMOTION · LIVE':'ЛОКАЛЬНОЕ ДООБУЧЕНИЕ';
 $('pageSubtitle').textContent=isSelection?`${selection?.selection_name||'Текущий selection'} · ${integer(selection?.policies?.length)} policy · ${integer(selection?.seeds)} paired seeds · ${integer(selection?.episodes_total)} эпизодов`:`${m.gpu.replace('NVIDIA GeForce ','').replace('NVIDIA ','').replace(' GPU','')} · ${integer(m.num_envs)} сред · Seed ${m.seed}`;
 if(isSelection){const selectionLabels={completed:'Оценка завершена',running:'Оценка идёт',failed:'Ошибка оценки',cancelled:'Остановлено',stopped:'Остановлено'};$('runStatus').className=`status ${selection?.status||'initializing'}`;$('runStatus').textContent=selectionLabels[selection?.status]||'Ожидание данных';}
 $('runStatus').hidden=false;
 document.querySelector('.toolbar').hidden=isSelection;
 $('lastUpdate').textContent=isSelection?`Монитор · ${selection?.updated_utc?date(selection.updated_utc):'—'}`:`Запись в логе · ${date(p.updated_utc || m.created_utc)}`;
 $('metricCount').textContent=data.scalar_count;
 $('trainingQueueStatus').hidden=true;
 $('evaluationStatus').hidden=true;
}

function renderOverview() {
 const p=data.progress,m=data.manifest,done=p.completed_updates,total=p.target_updates,percent=100*done/total;
 const eta=data.eta_seconds;
 const etaClock=eta == null?'Оценка появится при активном обучении':`Примерно до ${new Date(Date.now()+eta*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}`;
 $('stats').innerHTML=stat('Выполнено updates',`${integer(done)} <small>/ ${integer(total)}</small>`,`${percent.toFixed(1)}% бюджета · индекс ${integer(p.iteration)}`,`<div class="progress-track" role="progressbar" aria-valuenow="${done}" aria-valuemin="0" aria-valuemax="${total}" aria-label="Прогресс обучения"><span style="width:${Math.min(percent,100)}%"></span></div>`)
  +stat('Средняя награда',numeric(latest('Train/mean_reward')),'Последняя запись TensorBoard')
  +stat(data.status==='completed'?'Длительность':'Осталось примерно',duration(data.status==='completed'?p.elapsed_seconds:eta),data.status==='completed'?'Бюджет завершён':etaClock)
  +stat('Скорость обучения',`${numeric(p.iteration_seconds)} <small>с / update</small>`,`${integer(latest('Perf/total_fps'))} steps/s · ${duration(p.elapsed_seconds)} прошло`);
 $('overviewCharts').innerHTML=overviewTags.map(chart).join('');
 const commands=p.commands_sampled || {},maximum=Math.max(...Object.values(commands),1);
 const commandNames={zero:'Ноль',yaw:'Yaw',forward:'Продольная',lateral:'Боковая',diagonal:'Диагональная',mixed:'Смешанная',turning:'С поворотом',original_vendor:'Upstream'};
 $('commands').innerHTML=Object.entries(commands).map(([name,count])=>`<div class="command-row"><span>${commandNames[name]||escapeHtml(name)}</span><div class="command-bar"><i style="width:${100*count/maximum}%;${name==='original_vendor'?'background:var(--blue)':''}"></i></div><span>${integer(count)}</span></div>`).join('');
 $('configuration').innerHTML=row('Learning rate / предел',`${numeric(p.learning_rate)} / ${numeric(m.lr_cap)}`)+row('Rollout на среду',`${m.rollout_steps} steps`)+row('Собрано transitions',integer(done*m.num_envs*m.rollout_steps))+row('Исходные / прямые команды',`${integer(m.original_vendor_cohort_envs ?? 0)} / ${integer(m.direct_command_cohort_envs ?? m.num_envs)} сред`)+row('Ноль · training',`${integer(p.training_zero_passes)} / ${integer(p.training_zero_windows)} окон`)+row('Ноль на stair tiles · training',`${integer(p.training_stair_tile_zero_passes)} / ${integer(p.training_stair_tile_zero_windows)} окон`)+row('Сохранение','Промежуточные + финальный');
}

function renderMetrics() {
 const query=$('metricSearch').value.toLowerCase(),group=$('metricGroup').value;
 const tags=Object.keys(data.series).filter(tag=>(!group || tag.startsWith(`${group}/`)) && `${tag} ${titles[tag]||''}`.toLowerCase().includes(query));
 $('allCharts').innerHTML=tags.map(chart).join(''); $('metricsEmpty').hidden=tags.length>0;
}

function renderCheckpoints() {
 const m=data.manifest;
 $('checkpointCount').textContent=`${data.checkpoints.length} файлов`;
 $('checkpointRows').innerHTML=data.checkpoints.map(point=>`<tr><td><strong>${escapeHtml(point.name)}</strong></td><td>${integer(point.iteration-m.parent_iteration)}</td><td>${(point.bytes/1024/1024).toFixed(2)} MB</td><td>${date(point.modified_utc)}</td><td><span class="tag">${point.parent?'Восстановленный parent':point.iteration===m.parent_iteration+m.additional_updates?'Финальный':'Промежуточный'}</span></td></tr>`).join('');
 $('provenance').innerHTML=row('Parent SHA-256',`<code>${escapeHtml(m.parent_sha256)}</code>`)+row('Веса parent',m.parent_state_exact?'Восстановлены точно':'Нет записи проверки')+row('Начальный индекс',integer(m.first_update_index))+row('Плановый финальный индекс',integer(m.parent_iteration+m.additional_updates))+row('Torch / RSL-RL',`${escapeHtml(m.torch)} / ${escapeHtml(m.rsl_rl)}`)+row('Seed',m.seed)+row('ABI',`${m.actor_observations} → ${m.actions} · ${m.policy_hz} Hz`);
}

function renderSelection() {
 if(!selection?.available){$('selectionNotice').textContent='Selection ещё не подготовлен.';return;}
 $('selectionTitle').textContent=selection.selection_title||'Оценка policy';
 const done=selection.completed.length,total=selection.variants_total,percent=100*done/total;
 const running=selection.status==='running', failed=selection.status==='failed', stopped=['stopped','cancelled','interrupted'].includes(selection.status);
 $('selectionNotice').className=`alert${failed?' error':''}`;
 $('selectionNotice').textContent=failed?'Оценка остановлена с ошибкой. Готовые batch сохранены.':stopped?'Оценка прервана. Готовые результаты сохранены; незавершённый прогон не учитывается.':running?'Оценка выполняется. Показаны только завершённые прогоны; пока покрытие policies различается, их общий успех сравнивать рано.':'Оценка завершена. Результаты не меняют кандидата автоматически и не дают допуска к реальному роботу.';
 const timeValue=running?(selection.eta_seconds==null?duration(selection.batch_elapsed_seconds):duration(selection.eta_seconds)):duration(selection.elapsed_seconds);
 const timeDetail=running?(selection.eta_seconds==null?'Длительность текущего прогона':'Расчётный ETA по готовым batch'):'Полная длительность оценки';
 $('selectionStats').innerHTML=stat('Условия',`${done} <small>/ ${total}</small>`,`${percent.toFixed(1)}%`, `<div class="progress-track"><span style="width:${percent}%"></span></div>`)+stat('Эпизоды',`${integer(selection.episodes_recorded)} <small>/ ${integer(selection.episodes_total)}</small>`,'Атомарно сохранённые результаты')+stat('Policy',integer(selection.policies.length),selection.policies.map(p=>selection.policy_labels?.[p]||p).join(' · '))+stat(running?'Осталось / batch':'Длительность',timeValue,timeDetail);
 const completed=new Set(selection.completed),active=new Map(selection.active.map(item=>[item.terrain,item]));
 $('selectionVariants').innerHTML=selection.variants.map(name=>{const item=active.get(name),state=completed.has(name)?'done':item?'active':'pending';let detail='ожидание';if(completed.has(name))detail='готово';else if(item)detail=item.step==null?`идёт · ${duration(item.elapsed_seconds)}`:`${integer(item.step)}/${integer(item.total)} · alive ${integer(item.alive)}/${integer(item.envs)}`;return `<article class="variant-pill ${state}"><span>${escapeHtml(selection.variant_labels?.[name]||terrainNames[name]||name)}</span><strong>${detail}</strong></article>`;}).join('');
 $('selectionUpdated').textContent=selection.updated_utc?`Прогресс записан ${date(selection.updated_utc)}`:'—';
 $('selectionRanking').innerHTML=selection.ranking.map((policy,index)=>{const value=selection.overall[policy],fraction=value.episodes?100*value.success/value.episodes:0;const note=selection.ranking_is_order?(value.episodes===selection.episodes_per_policy?'готово':value.episodes?'неполные данные':'ожидание'):(selection.status==='completed'&&index===0?'лидер':'предварительно');return `<tr><td>${index+1}</td><td><strong>${escapeHtml(selection.policy_labels?.[policy]||policy)}</strong><small>${escapeHtml(policy)} · ${note}</small></td><td>${integer(value.episodes)}</td><td>${integer(value.success)}</td><td>${value.episodes?fraction.toFixed(1)+'%':'—'}</td><td class="${value.unsafe?'negative':'neutral'}">${integer(value.unsafe)}</td></tr>`;}).join('');
 const cell=(policy,group)=>{const value=selection.conditions[group][policy];return value.episodes?`${value.success}/${value.episodes}<small>unsafe ${value.unsafe}</small>`:'—';};
 const decision=selection.decision;
 $('selectionDecision').hidden=!decision;
 if(decision) $('selectionDecision').textContent=decision.selected?`Результат: ${decision.selected} требует дальнейшего подтверждения. Кандидат остаётся core_24650.`:'Критерии продвижения не выполнены. Кандидат остаётся core_24650.';
 $('selectionConditions').innerHTML=selection.ranking.map(policy=>`<tr><td><strong>${escapeHtml(selection.policy_labels?.[policy]||policy)}</strong></td><td>${cell(policy,'flat')}</td><td>${cell(policy,'rough')}</td><td>${cell(policy,'stairs_up')}</td><td>${cell(policy,'stairs_down')}</td></tr>`).join('');
}

function render() {
 if(currentView==='jobs') return;
 renderHeading();
 if (currentView==='overview') renderOverview();
 if (currentView==='metrics') renderMetrics();
 if (currentView==='checkpoints') renderCheckpoints();
 if (currentView==='selection') renderSelection();
}
function syncRuns(runs) {
 if (!runs.length) throw Error('No runs');
 if (!selectedRun || followLatest) selectedRun=runs[0].id;
 $('runSelect').innerHTML=runs.map(run=>`<option value="${escapeHtml(run.id)}">${run.parent} → ${run.target} · ${escapeHtml(run.name.split('_')[0])} ${escapeHtml(run.name.split('_')[1].replaceAll('-',':'))}</option>`).join('');
 $('runSelect').value=selectedRun;
}
async function loadRun() {
 if(currentView==='jobs') { if(window.refreshJobs) await window.refreshJobs(); return; }
 if(currentView==='selection') {
  try {await loadSelection();renderSelection();showError('');$('connection').textContent='Подключено локально';$('connectionDot').style.background='var(--mint)';}
  catch(error) {showError('Не удалось прочитать сравнение. Повторите обновление.');}
  return;
 }
 if (!selectedRun || busy) return;
 busy=true; $('refresh').disabled=true;
 let requestedRun=selectedRun;
 try {
  syncRuns((await getJson('/api/runs')).runs);
  requestedRun=selectedRun;
  const result=await getJson(`/api/run?id=${encodeURIComponent(requestedRun)}`);
  if (requestedRun!==selectedRun) return;
  data=result;
  if(currentView==='selection') await loadSelection();
  const previous=$('metricGroup').value,groups=[...new Set(Object.keys(data.series).map(tag=>tag.split('/')[0]))];
  $('metricGroup').innerHTML='<option value="">Все группы</option>'+groups.map(group=>`<option>${escapeHtml(group)}</option>`).join('');
  if (groups.includes(previous)) $('metricGroup').value=previous;
  $('connection').textContent=data.status==='stale'?'Логи не обновляются':'Подключено локально';
  $('connectionDot').style.background=data.status==='stale'?'var(--amber)':'var(--mint)';
  showError(data.metrics_warning||'');render();
 } catch(error) { showError('Не удалось обновить данные. Последний полученный снимок сохранён. Проверьте локальный сервер и нажмите «Обновить».'); $('connection').textContent='Нет соединения'; $('connectionDot').style.background='var(--red)'; }
 finally { busy=false; $('refresh').disabled=false; if (requestedRun!==selectedRun) loadRun(); }
}
async function changeView(view) {
 currentView=view;history.replaceState(null,'',`#${view}`);
 document.querySelectorAll('.view').forEach(section=>section.hidden=section.id!==view);
 document.querySelectorAll('.nav').forEach(button=>{button.classList.toggle('active',button.dataset.view===view);button.setAttribute('aria-current',button.dataset.view===view?'page':'false');});
 $('tooltip').hidden=true;
 document.querySelector('.page-heading').hidden=['jobs','selection'].includes(view);
 document.querySelector('.toolbar').hidden=['jobs','selection'].includes(view);
 if(view==='jobs') {showError(''); if(window.refreshJobs) await window.refreshJobs(); return;}
 if (view==='selection') {
  try { await loadSelection(); }
  catch(error) { showError('Не удалось прочитать checkpoint selection. Evaluation продолжает работать независимо от dashboard.'); }
 }
 if(view==='selection') {renderSelection();return;}
 await loadRun();
}

async function loadSelection() { selection=await getJson('/api/selection?source='+encodeURIComponent($('selectionSource').value)); }

document.querySelectorAll('.nav').forEach(button=>button.addEventListener('click',()=>changeView(button.dataset.view)));
document.querySelector('.brand').addEventListener('click',event=>{event.preventDefault();changeView('overview');});
$('refresh').addEventListener('click',loadRun);
$('selectionSource').addEventListener('change',loadRun);
$('refreshSelection').addEventListener('click',loadRun);
$('runSelect').addEventListener('change',()=>{followLatest=false;selectedRun=$('runSelect').value;loadRun();});
$('smooth').addEventListener('input',()=>{smoothing=Number($('smooth').value);$('smoothValue').textContent=smoothing.toFixed(2);if(data)render();});
['metricSearch','metricGroup'].forEach(id=>$(id).addEventListener('input',()=>{if(data)renderMetrics();}));
document.addEventListener('pointermove',event=>{
 const svg=event.target.closest('svg.chart');
 if (!svg || !data) { $('tooltip').hidden=true;return; }
 const points=(data.series[svg.dataset.tag]||[]).filter(point=>point[1]!=null);if(!points.length)return;
 const box=svg.getBoundingClientRect(),svgWidth=svg.viewBox.baseVal.width;
 const fraction=Math.max(0,Math.min(1,((event.clientX-box.left)/box.width*svgWidth-59)/(svgWidth-71)));
 const step=points[0][0]+fraction*(points.at(-1)[0]-points[0][0]);
 let lo=0,hi=points.length-1;while(lo<hi){const middle=Math.floor((lo+hi)/2);if(points[middle][0]<step)lo=middle+1;else hi=middle;}
 if(lo>0 && Math.abs(points[lo-1][0]-step)<Math.abs(points[lo][0]-step))lo--;
 const point=points[lo],tip=$('tooltip');tip.innerHTML=`${escapeHtml(titles[svg.dataset.tag]||svg.dataset.tag)}<br><strong>${Number(point[1].toPrecision(8))}</strong><small>${svg.dataset.tag.endsWith('/time')?'Время, с':'Итерация'} ${integer(point[0])} · исходное значение</small>`;tip.hidden=false;
 tip.style.left=`${Math.max(8,Math.min(event.clientX+15,innerWidth-tip.offsetWidth-12))}px`;tip.style.top=`${Math.max(8,Math.min(event.clientY+15,innerHeight-tip.offsetHeight-12))}px`;
});
window.addEventListener('blur',()=>$('tooltip').hidden=true);
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(data)render();},150);});
setInterval(()=>{if($('autoRefresh').checked&&!document.hidden)loadRun();},10000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$('autoRefresh').checked)loadRun();});
async function init() {
 try {
  const result=await getJson('/api/runs');
  if(result.runs.length) syncRuns(result.runs);
  const initial=location.hash.slice(1);await changeView(['jobs','overview','metrics','selection','checkpoints'].includes(initial)?initial:'jobs');
  await loadRun();
 } catch(error) {showError('Не найдены данные обучения или локальный сервер недоступен. Перезагрузите страницу после запуска сервера.');$('connection').textContent='Данные недоступны';$('connectionDot').style.background='var(--amber)';}
}
init();
