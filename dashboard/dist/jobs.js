'use strict';
(() => {
 let polling=false;
 const $ = id => document.getElementById(id);
 const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const duration = seconds => seconds == null ? '—' : `${Math.floor(seconds / 3600)} ч ${Math.floor(seconds % 3600 / 60)} мин`;
 const date = iso => new Date(iso).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
 async function getJson(url) {
  const response = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(15000)});
  if (!response.ok) throw Error(`HTTP ${response.status}`);
  return response.json();
 }
 const message=(text,error=false)=>{const box=$('jobMessage');box.textContent=text;box.hidden=!text;box.classList.toggle('error',error);};
 const states={queued:'В очереди',running:'Выполняется',stopping:'Останавливается',completed:'Завершён',failed:'Ошибка',cancelled:'Остановлен',interrupted:'Нет связи с процессом'};
 function progressBar(job, trainingPhase) {
  let done, total, label='Выполнение';
  if(job.training_progress && trainingPhase) {
   done=job.training_progress.completed_updates;total=job.training_progress.target_updates;
   label=job.pilot_progress?'Обучение текущего плеча · updates':'Обучение · updates';
  } else if(job.evaluation_progress) {
   done=job.evaluation_progress.completed?.length;total=job.evaluation_progress.total_jobs;
   label='Оценка · завершённые прогоны';
  }
  const track=$('jobProgressTrack');
  $('jobProgressBar').className=`job-progress ${job.status}`;
  $('jobProgressLabel').textContent=label;
  track.setAttribute('aria-label',label);
  if(Number.isFinite(done) && Number.isFinite(total) && total>0) {
   done=Math.max(0,Math.min(done,total));
   const percent=100*done/total;
   track.value=percent;
   const text=`${done} / ${total} · ${percent.toLocaleString('ru-RU',{maximumFractionDigits:1})}%`;
   $('jobProgressValue').textContent=text;track.setAttribute('aria-valuetext',text);
  } else if(job.status==='completed') {
   track.value=100;$('jobProgressValue').textContent='100%';
   track.setAttribute('aria-valuetext','Завершён');
  } else {
   track.removeAttribute('value');
   const text=['queued','running','stopping'].includes(job.status)?'Ожидание данных о прогрессе':'Прогресс не измерен';
   $('jobProgressValue').textContent=text;track.setAttribute('aria-valuetext',text);
   // A stopped job must not look like an ongoing indeterminate operation.
   track.hidden=!['queued','running','stopping'].includes(job.status);
   return;
  }
  track.hidden=false;
 }
 function detail(job) {
  $('jobDetail').hidden=false;$('jobDetailTitle').textContent=`${job.kind} · ${states[job.status]||job.status}`;
  $('jobEmpty').hidden=true;
  $('runStatus').textContent=(states[job.status]||job.status)+(job.returncode==null?'':` · exit ${job.returncode}`);
  $('runStatus').className=`status ${job.status}`;
  $('jobIdentity').textContent=`${job.id} · начало ${date(job.created)}`;
  $('lastUpdate').textContent=`Запись статуса · ${date(job.updated)}`;
  document.title=`B2W · ${states[job.status]||job.status}`;
  const progress=job.evaluation_progress;
  $('jobProgress').textContent=progress?`${job.entrypoint==='scripts/run_stair_isolation.py'?'Actor':'Рельеф'}: ${progress.completed.length}/${progress.total_jobs}. Сейчас: ${progress.active.join(', ')||'—'}. ${progress.failures.join('; ')}`:'';
  const phase=job.pilot_progress?.phase||'';
  // Pilot arms may have arbitrary names (fixed, adaptive, control, ...).
  // The saved training state identifies a live learner; workflow phases keep
  // old learner counters from replacing preflight, export or evaluation.
  const otherPhase=/^(preflight|audit_|probe_|paired_probe|baseline_probe|full_screen|export_parity|completed|failed|cancelled)/.test(phase);
  const trainingPhase=!job.pilot_progress || phase.startsWith('training_') ||
   (['running','initializing'].includes(job.training_progress?.status) && !otherPhase);
  if(job.training_progress && trainingPhase) {const p=job.training_progress;$('jobProgress').textContent=`Обучение: ${p.completed_updates??0}/${p.target_updates??'—'} updates · iteration ${p.iteration??'—'} · ${duration(p.elapsed_seconds)}`;}
  progressBar(job,trainingPhase);
  if(job.pilot_progress) {const p=job.pilot_progress;$('jobProgress').textContent=`${p.experiment||'A/B'} · ${p.phase} · seed ${p.seed}. `+$('jobProgress').textContent;}
  if(!['queued','running','stopping'].includes(job.status))$('jobProgress').textContent=`${states[job.status]||job.status}. `+$('jobProgress').textContent;
  $('jobLog').textContent=Object.entries(job.logs).map(([name,text])=>`${name}\n${text}`).join('\n\n');
  $('jobResult').innerHTML='';
  if(job.summary) {
   const s=job.summary;
   $('jobResult').innerHTML=`<p>Рекомендация development candidate: <strong>${escapeHtml(s.candidate_recommendation)}</strong>. Hardware-допуска нет.</p><div class="table-wrap"><table><thead><tr><th>Policy</th><th>Успех</th><th>Unsafe</th><th>Все условия</th><th>Tracking</th><th>Переходы</th><th>Остановка</th><th>Лестницы</th></tr></thead><tbody>${s.ranking.map(p=>{const r=s.overall[p],c=r.checks;return `<tr><td>${escapeHtml(p)}</td><td>${r.success}/${r.episodes}</td><td>${r.unsafe}</td><td>${s.all_cells_pass[p]?'PASS':'FAIL'}</td>${['tracking','transitions','stop','traversal'].map(k=>`<td>${c[k].passed}/${c[k].trials}</td>`).join('')}</tr>`;}).join('')}</tbody></table></div><details><summary>Результаты по рельефу и командным программам</summary><pre style="white-space:pre-wrap">${escapeHtml(JSON.stringify(s.cells,null,2))}</pre></details>`;
  }
  if(job.pilot_progress?.decision){const d=job.pilot_progress.decision;$('jobResult').insertAdjacentHTML('afterbegin',`<p><strong>Решение A/B:</strong> ${d.selected?'Финалист для дальнейшей проверки: '+escapeHtml(d.selected):'Критерии продвижения не выполнены. Сохраняется core_24650.'}</p><details><summary>Причины решения A/B</summary><pre style="white-space:pre-wrap">${escapeHtml(JSON.stringify(d.decisions,null,2))}</pre></details>`);}
  if(job.summary?.plan?.diagnostic_only&&!job.pilot_progress){$('jobResult').querySelector('p').textContent='Диагностический повтор: проверка воспроизводимости, без выбора policy. Текущий development candidate — core_24650.';}
  if(job.pilot_progress&&job.summary){const notice=$('jobResult').querySelector('p');if(notice&&!job.pilot_progress.decision)notice.textContent='Сравнительный рейтинг пилота. Текущий development candidate остаётся core_24650 до отдельного решения.';const notices=$('jobResult').querySelectorAll('p');for(const p of notices){if(p.textContent.startsWith('Рекомендация development candidate:'))p.textContent='Текущий development candidate: core_24650. Рейтинг пилота не меняет его автоматически.';}}
  if(job.summary?.partial){$('jobResult').insertAdjacentHTML('afterbegin','<p>Промежуточные данные: сравнение ещё не завершено.</p>');}
  if(job.training_progress?.training_coverage?.stairs_up?.current_levels){const c=job.training_progress.training_coverage;$('jobResult').insertAdjacentHTML('beforeend',`<details open><summary>Safety и curriculum</summary><p>Повышений: ${c.retention.curriculum_promotions}; понижений: ${c.retention.curriculum_demotions}. Аварии обучения не равны результату evaluation.</p><pre style="white-space:pre-wrap">${escapeHtml(JSON.stringify(Object.fromEntries(Object.entries(c).map(([k,v])=>[k,{resets:v.reset_counts,levels:v.current_levels,attempts_by_level:v.level_attempts,segment_attempts:v.segment_attempts,completed_segments:v.segment_completions}])),null,2))}</pre></details>`);}
 if(job.training_progress?.training_coverage){const c=job.training_progress.training_coverage;$('jobResult').insertAdjacentHTML('beforeend',`<details open><summary>Покрытие обучения по группам рельефа</summary><div class="table-wrap"><table><thead><tr><th>Группа</th><th>Среды</th><th>Завершённые эпизоды</th><th>Минимум полных эпизодов / среду</th><th>Средний return</th></tr></thead><tbody>${Object.entries(c).map(([name,r])=>`<tr><td>${escapeHtml(name)}</td><td>${r.envs}</td><td>${r.completed_episodes}</td><td>${r.min_full_episodes_per_env}</td><td>${r.mean_completed_return==null?'—':r.mean_completed_return.toFixed(3)}</td></tr>`).join('')}</tbody></table></div><p>Training returns не являются acceptance policy.</p></details>`);}
 }
 window.refreshJobs=async()=>{
  if(polling)return;polling=true;
  try {
   const {job}=await getJson('/api/current');
   if(job)detail(job);
   else {
    $('jobDetail').hidden=true;$('jobEmpty').hidden=false;
    $('jobProgress').textContent='';$('jobResult').innerHTML='';$('jobLog').textContent='';
    $('jobIdentity').textContent='Ожидание нового запуска';$('runStatus').textContent='Нет запуска';
    $('runStatus').className='status';document.title='B2W · Текущий запуск';
    $('lastUpdate').textContent='Ожидание данных';
   }
   message(job?.error||'',Boolean(job?.error));
   $('connection').textContent='Подключено локально';$('connectionDot').style.background='var(--mint)';
  }catch(e){message(`Не удалось обновить статус: ${e.message}. Показаны последние полученные данные.`,true);$('connection').textContent='Нет связи';$('connectionDot').style.background='var(--red)';}finally{polling=false;}
 };
 $('refresh').onclick=window.refreshJobs;
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)window.refreshJobs();});
 setInterval(()=>{if(!document.hidden)window.refreshJobs();},3000);
 window.refreshJobs();
})();
