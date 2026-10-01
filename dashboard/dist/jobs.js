'use strict';
(() => {
 let selected='', polling=false, followJob=true;
 const message=(text,error=false)=>{const box=$('jobMessage');box.textContent=text;box.hidden=!text;box.classList.toggle('error',error);};
 const states={queued:'В очереди',running:'Выполняется',stopping:'Останавливается',completed:'Завершён',failed:'Ошибка',cancelled:'Остановлен',interrupted:'Нет связи с процессом'};
 async function detail(id) {
  selected=id;const job=await getJson(`/api/job?id=${encodeURIComponent(id)}`);
  $('jobDetail').hidden=false;$('jobDetailTitle').textContent=`${job.kind} · ${states[job.status]||job.status}`;
  const progress=job.evaluation_progress;
  $('jobProgress').textContent=progress?`${job.entrypoint==='scripts/run_stair_isolation.py'?'Actor':'Рельеф'}: ${progress.completed.length}/${progress.total_jobs}. Сейчас: ${progress.active.join(', ')||'—'}. ${progress.failures.join('; ')}`:'';
  if(job.training_progress && (!job.pilot_progress||job.pilot_progress.phase.startsWith('training_'))) {const p=job.training_progress;$('jobProgress').textContent=`Обучение: ${p.completed_updates||0}/${p.target_updates||'—'} updates · iteration ${p.iteration||'—'} · ${duration(p.elapsed_seconds)}`;}
  if(job.pilot_progress) {const p=job.pilot_progress;$('jobProgress').textContent=`${p.experiment||'A/B'} · ${p.phase} · seed ${p.seed}. `+$('jobProgress').textContent;}
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
   const {jobs}=await getJson('/api/jobs');
   $('jobList').innerHTML=jobs.length?jobs.map(j=>`<div class="config-row"><button class="button" data-job="${j.id}">${escapeHtml(j.kind)} · ${escapeHtml(date(j.created))}</button><span>${escapeHtml(states[j.status]||j.status)}${j.returncode==null?'':` · exit ${j.returncode}`}</span></div>`).join(''):'Запусков пока нет.';
   $('jobList').querySelectorAll('[data-job]').forEach(b=>b.onclick=()=>{followJob=false;detail(b.dataset.job).catch(e=>message(e.message,true));});
   if((!selected||followJob)&&jobs.length)selected=jobs[0].id;
   if(selected)await detail(selected);
   if($('jobMessage').dataset.connectionError==='true'){message('');delete $('jobMessage').dataset.connectionError;}
   $('connection').textContent='Подключено локально';$('connectionDot').style.background='var(--mint)';
  }catch(e){message(e.message,true);$('jobMessage').dataset.connectionError='true';}finally{polling=false;}
 };
 setInterval(()=>{if(!document.hidden&&currentView==='jobs')window.refreshJobs();},3000);
 window.refreshJobs();
})();
