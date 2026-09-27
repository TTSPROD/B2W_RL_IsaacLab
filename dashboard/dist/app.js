'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const integer = value => Number(value ?? 0).toLocaleString('ru-RU', {maximumFractionDigits:0});
const numeric = value => value == null || !Number.isFinite(value) ? '—' : Math.abs(value) > 0 && Math.abs(value) < .001 ? value.toExponential(2) : value.toLocaleString('ru-RU', {maximumFractionDigits:Math.abs(value) < 10 ? 3 : 1});
const duration = seconds => seconds == null ? '—' : `${Math.floor(seconds / 3600)} ч ${Math.floor(seconds % 3600 / 60)} мин`;
const date = iso => new Date(iso).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
let data = null, evaluation = null, currentView = 'overview', selectedRun = '', busy = false, smoothing = .6;
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
const terrainNames = {flat:'Flat',rough_04:'Rough ±4 см',boxes_10:'Блоки 5–10 см',slope_up_10:'Уклон +10°',slope_down_10:'Уклон −10°',stairs_up_06:'Лестница ↑ 6 см',stairs_down_06:'Лестница ↓ 6 см',stairs_up_12:'Лестница ↑ 12 см',stairs_down_12:'Лестница ↓ 12 см',stairs_up_18:'Лестница ↑ 18 см',stairs_down_18:'Лестница ↓ 18 см'};
const overviewTags = ['Train/mean_reward','Metrics/base_velocity/error_vel_yaw','Train/mean_episode_length','Metrics/base_velocity/error_vel_xy','Loss/value_function','Loss/surrogate','Loss/entropy','Curriculum/terrain_levels'];
const latest = tag => data?.series[tag]?.at(-1)?.[1];
const evaluationPair = () => [String($('evaluationReference').value || evaluation?.policies[0] || 19999), String(evaluation?.policies.at(-1) || 21999)];
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
 const labels={running:'Обучение идёт',completed:'Завершено',failed:'Ошибка запуска',stale:'Нет свежих данных',initializing:'Инициализация'};
 $('runStatus').className=`status ${data.status}`;
 $('runStatus').textContent=labels[data.status] || data.status;
 const [reference,candidate]=evaluationPair();
 $('pageTitle').textContent=currentView==='evaluation'?`${candidate} vs ${reference}`:`${m.parent_iteration} → ${m.parent_iteration+m.additional_updates}`;
 $('pageEyebrow').textContent=currentView==='evaluation'?'ПОСЛЕДНЯЯ ПРОВЕРКА · 27 СЕНТЯБРЯ 2026':'ЛОКАЛЬНОЕ ДООБУЧЕНИЕ';
 $('pageSubtitle').textContent=currentView==='evaluation'?'Flat / Rough / блоки / уклоны / лестницы · 14 976 эпизодов':`${m.gpu.replace('NVIDIA GeForce ','').replace('NVIDIA ','').replace(' GPU','')} · ${integer(m.num_envs)} сред · Seed ${m.seed}`;
 $('runStatus').hidden=currentView==='evaluation';
 document.querySelector('.toolbar').hidden=currentView==='evaluation';
 $('lastUpdate').textContent=currentView==='evaluation'?'Данные проверки · 27.09.2026':`Запись в логе · ${date(p.updated_utc || m.created_utc)}`;
 $('metricCount').textContent=data.scalar_count;
 const check=data.evaluation_progress;
 $('evaluationStatus').hidden=!check;
 if(check) {
  const phase=check.current?.startsWith('flat_')?`Flat · ${check.current.slice(5)}`:terrainNames[check.current]||check.current;
  $('evaluationStatus').textContent=data.latest_evaluation_ready?'Проверка 23999 завершена. Результаты доступны в разделе «Последний тест».':check.status==='completed'?'Все прогоны 23999 завершены. Выполняется проверка сохранённых трасс.':check.status==='failed'?`Проверка 23999 остановилась на ${phase}. Уже полученные результаты сохранены.`:`Проверка 23999 · завершено ${check.completed.length}/${check.total_jobs} прогонов · сейчас ${phase}`;
 }
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

function comparison(name,a,b,denominator) {
 return `<div class="comparison"><span>${escapeHtml(name)}</span><div class="pair-bars">${[a,b].map(value=>`<div class="compare-line"><div class="compare-track"><span style="width:${100*value/denominator}%"></span></div><b>${integer(value)}/${integer(denominator)}</b></div>`).join('')}</div></div>`;
}
function renderEvaluation() {
 if (!evaluation) return;
 const [reference,candidate]=evaluationPair(),a=evaluation.overall[reference],b=evaluation.overall[candidate];
 const improved=evaluation.rows.filter(r=>r.policies[candidate].success>r.policies[reference].success).length;
 const regressed=evaluation.rows.filter(r=>r.policies[candidate].success<r.policies[reference].success).length;
 const lost=evaluation.rows.filter(r=>r.policies[reference].success===r.policies[reference].episodes&&r.policies[candidate].success<r.policies[reference].success).length;
 $('evaluationNotice').textContent=`${candidate}: ${regressed} строк с регрессом к ${reference}, unsafe ${b.unsafe}. Общая сумма не компенсирует отказы отдельных сценариев. Это development screen фиксированного checkpoint.`;
 $('evaluationSource').textContent=Number(reference)===evaluation.retained_reference_policy?'Контроль — сохранённый тест':'Обе policies проверены свежими прогонами';
 $('beforePolicy').textContent=reference;$('afterPolicy').textContent=candidate;$('unsafePolicies').textContent=`Unsafe ${reference} → ${candidate}`;
 document.querySelectorAll('#evaluation .legend .baseline').forEach(el=>el.textContent=reference);
 document.querySelectorAll('#evaluation .legend .candidate').forEach(el=>el.textContent=candidate);
 $('evalStats').innerHTML=stat('Полный успех / 7 488',`${integer(a.success)} <small>→</small> ${integer(b.success)}`,`Фиксированные policies ${reference} и ${candidate}`)+stat('Строк улучшилось',improved,'Из 234 сценариев')+stat('Строк ухудшилось',`<span class="negative">${regressed}</span>`,`${lost} потерянных строк 32/32`)+stat('Unsafe',`${a.unsafe} <small>→</small> ${b.unsafe}`,'Нарушения hard joint range');
 $('terrainComparison').innerHTML=Object.entries(evaluation.terrains).map(([key,value])=>comparison(terrainNames[key]||key,value[reference].success,value[candidate].success,value[reference].episodes)).join('');
 $('stairComparison').innerHTML=`<div class="legend" style="margin-bottom:18px"><span class="baseline">${reference}</span><span class="candidate">${candidate}</span></div>`+Object.entries(evaluation.terrains).filter(([key])=>key.startsWith('stairs')).map(([key,value])=>comparison(terrainNames[key],value[reference].exposed_zero_success,value[candidate].exposed_zero_success,value[reference].stair_stop_windows)).join('');
 $('safetySummary').innerHTML=row('Wheel speed peak, rad/s',`${numeric(a.max_wheel_speed_rad_s)} → ${numeric(b.max_wheel_speed_rad_s)}`)+row('Макс. доля torque saturation',`${numeric(a.max_wheel_saturation_fraction*100)}% → ${numeric(b.max_wheel_saturation_fraction*100)}%`)+row('Мин. hard joint margin, rad',`${a.min_hard_joint_margin_rad.toFixed(6)} → ${b.min_hard_joint_margin_rad.toFixed(6)}`);
 renderEvalRows();
}
function renderEvalRows() {
 if (!evaluation) return;
 const [reference,candidate]=evaluationPair();
 const terrain=$('terrainFilter').value,result=$('resultFilter').value,query=$('caseSearch').value.toLowerCase();
 const rows=evaluation.rows.map(item=>{const a=item.policies[reference],b=item.policies[candidate];return {...item,delta:b.success-a.success,lost_perfect:a.success===a.episodes&&b.success<a.success};}).filter(item=>(!terrain||item.terrain===terrain)&&item.case.toLowerCase().includes(query)&&(!result||result==='regressed'&&item.delta<0||result==='improved'&&item.delta>0||result==='lost'&&item.lost_perfect));
 $('evalRows').innerHTML=rows.map(item=>{const a=item.policies[reference],b=item.policies[candidate];return `<tr><td>${escapeHtml(item.case)}<small>${escapeHtml(terrainNames[item.terrain]||item.terrain)}${item.lost_perfect?' · потеря 32/32':''}</small></td><td>${a.success}/${a.episodes}</td><td>${b.success}/${b.episodes}</td><td class="${item.delta>0?'positive':item.delta<0?'negative':'neutral'}">${item.delta>0?'+':''}${item.delta}</td><td class="${b.unsafe?'negative':'neutral'}">${a.unsafe} → ${b.unsafe}</td></tr>`;}).join('') || '<tr><td colspan="5">Нет сценариев для выбранных фильтров.</td></tr>';
}
function render() {
 renderHeading();
 if (currentView==='overview') renderOverview();
 if (currentView==='metrics') renderMetrics();
 if (currentView==='checkpoints') renderCheckpoints();
 if (currentView==='evaluation') renderEvaluation();
}
async function loadRun() {
 if (!selectedRun || busy) return;
 busy=true; $('refresh').disabled=true;
 const requestedRun=selectedRun;
 try {
  const result=await getJson(`/api/run?id=${encodeURIComponent(requestedRun)}`);
  if (requestedRun!==selectedRun) return;
  data=result;
  if (data.latest_evaluation_ready && evaluation?.policies.at(-1)!==23999) {
   evaluation=null;
   if(currentView==='evaluation')await changeView('evaluation');
  }
  const previous=$('metricGroup').value,groups=[...new Set(Object.keys(data.series).map(tag=>tag.split('/')[0]))];
  $('metricGroup').innerHTML='<option value="">Все группы</option>'+groups.map(group=>`<option>${escapeHtml(group)}</option>`).join('');
  if (groups.includes(previous)) $('metricGroup').value=previous;
  $('connection').textContent=data.status==='stale'?'Логи не обновляются':'Подключено локально';
  $('connectionDot').style.background=data.status==='stale'?'var(--amber)':'var(--mint)';
  showError('');render();
 } catch(error) { showError('Не удалось обновить данные. Последний полученный снимок сохранён. Проверьте локальный сервер и нажмите «Обновить».'); $('connection').textContent='Нет соединения'; $('connectionDot').style.background='var(--red)'; }
 finally { busy=false; $('refresh').disabled=false; if (requestedRun!==selectedRun) loadRun(); }
}
async function changeView(view) {
 currentView=view;history.replaceState(null,'',`#${view}`);
 document.querySelectorAll('.view').forEach(section=>section.hidden=section.id!==view);
 document.querySelectorAll('.nav').forEach(button=>{button.classList.toggle('active',button.dataset.view===view);button.setAttribute('aria-current',button.dataset.view===view?'page':'false');});
 $('tooltip').hidden=true;
 if (view==='evaluation' && !evaluation) {
  try { evaluation=await getJson('/api/evaluation'); $('evaluationReference').innerHTML=evaluation.reference_options.map(p=>`<option value="${p}">${p}${p===evaluation.retained_reference_policy?' · сохранённый контроль':''}</option>`).join('');$('evaluationReference').value=String(evaluation.policies[0]);$('terrainFilter').innerHTML='<option value="">Все геометрии</option>'+Object.keys(evaluation.terrains).map(key=>`<option value="${escapeHtml(key)}">${escapeHtml(terrainNames[key]||key)}</option>`).join(''); }
  catch(error) { showError('Не удалось прочитать результаты последнего теста. Откройте раздел ещё раз.'); }
 }
 if (data) render();
}

document.querySelectorAll('.nav').forEach(button=>button.addEventListener('click',()=>changeView(button.dataset.view)));
document.querySelector('.brand').addEventListener('click',event=>{event.preventDefault();changeView('overview');});
$('refresh').addEventListener('click',loadRun);
$('runSelect').addEventListener('change',()=>{selectedRun=$('runSelect').value;loadRun();});
$('smooth').addEventListener('input',()=>{smoothing=Number($('smooth').value);$('smoothValue').textContent=smoothing.toFixed(2);if(data)render();});
['metricSearch','metricGroup'].forEach(id=>$(id).addEventListener('input',()=>{if(data)renderMetrics();}));
['terrainFilter','resultFilter','caseSearch'].forEach(id=>$(id).addEventListener('input',renderEvalRows));
$('evaluationReference').addEventListener('change',()=>{renderHeading();renderEvaluation();});
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
  const result=await getJson('/api/runs');if(!result.runs.length)throw Error('No runs');
  $('runSelect').innerHTML=result.runs.map(run=>`<option value="${escapeHtml(run.id)}">${run.parent} → ${run.target} · ${escapeHtml(run.name.split('_')[0])} ${escapeHtml(run.name.split('_')[1].replaceAll('-',':'))}</option>`).join('');
  selectedRun=result.runs[0].id;
  const initial=location.hash.slice(1);if(['overview','metrics','evaluation','checkpoints'].includes(initial))await changeView(initial);
  await loadRun();
 } catch(error) {showError('Не найдены данные обучения или локальный сервер недоступен. Перезагрузите страницу после запуска сервера.');$('connection').textContent='Данные недоступны';$('connectionDot').style.background='var(--amber)';}
}
init();
