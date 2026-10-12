// Current-run UI: switch training -> evaluation, clear old data, report failures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const nodes = new Map();
function element(id) {
  if (!nodes.has(id)) nodes.set(id, {
    textContent: '', innerHTML: '', hidden: true, className: '', style: {},
    classList: {toggle() {}},
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; if (name === 'value') delete this.value; },
    insertAdjacentHTML(position, html) { this.innerHTML = position === 'afterbegin' ? html + this.innerHTML : this.innerHTML + html; },
  });
  return nodes.get(id);
}
const requested = [];
let responseJob = null, fail = false;
const context = {
  window: {}, document: {getElementById: element, addEventListener() {}, hidden: false},
  AbortSignal, setInterval() {},
  async fetch(url) {
    requested.push(url);
    if (fail) throw Error('offline');
    return {ok: true, async json() { return {job: responseJob}; }};
  },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../dashboard/dist/jobs.js'), 'utf8'), context);

const job = (id, extra = {}) => ({id, kind: id, status: 'running',
  created: '2026-10-01T08:00:00+00:00', updated: '2026-10-01T08:00:01+00:00',
  returncode: null, logs: {'stdout.log': id}, ...extra});

(async () => {
  await new Promise(setImmediate); // Initial empty refresh.
  assert.equal(element('jobEmpty').hidden, false);
  responseJob = job('training', {training_progress: {completed_updates: 0, target_updates: 300, iteration: 0}});
  await context.window.refreshJobs();
  assert.match(element('jobProgress').textContent, /0\/300 updates · iteration 0/);
  assert.match(element('jobLog').textContent, /training/);
  assert.equal(element('jobProgressTrack').value, 0);
  assert.match(element('jobProgressValue').textContent, /0 \/ 300/);

  responseJob = job('reset', {entrypoint: 'scripts/run_reset_pilot.py',
    pilot_progress: {phase: 'control', seed: 9910},
    training_progress: {status: 'running', completed_updates: 210, target_updates: 300, training_coverage: {
      retention: {envs: 45, completed_episodes: 135, min_full_episodes_per_env: 3,
        mean_completed_return: 40, curriculum_promotions: 0, curriculum_demotions: 0},
      stairs_up: {envs: 32, completed_episodes: 30, min_full_episodes_per_env: 0,
        mean_completed_return: 85, current_levels: [1, 2], reset_counts: {unsafe: 5}},
    }}});
  await context.window.refreshJobs();
  assert.match(element('jobProgress').textContent, /210\/300 updates/);
  assert.match(element('jobResult').innerHTML, /curriculum/);
  assert.equal(element('jobProgressTrack').value, 70);
  assert.match(element('jobProgressValue').textContent, /70%/);

  for (const phase of ['fixed','adaptive','another_arm']) {
    responseJob = job('schedule', {entrypoint: 'scripts/run_schedule_pilot.py',
      pilot_progress: {phase, seed: 9911},
      training_progress: {status: 'running', completed_updates: 130, target_updates: 300}});
    await context.window.refreshJobs();
    assert.match(element('jobProgress').textContent, /130\/300 updates/);
    assert.equal(element('jobProgressTrack').value, 100*130/300);
    assert.match(element('jobProgressValue').textContent, /43,3%/);
    assert.equal(element('jobMessage').hidden, true);
  }
  for (const phase of ['preflight_fixed','export_parity']) {
    responseJob.pilot_progress.phase = phase;
    await context.window.refreshJobs();
    assert.doesNotMatch(element('jobProgress').textContent, /updates/);
    assert.equal(element('jobProgressTrack').value, undefined);
  }

  responseJob = job('upstream', {entrypoint: 'scripts/run_upstream_continuation.py',
    pilot_progress: {phase: 'training', ppo_updates: 0},
    recipe_progress: {phase: 'training', seed: 9931, completed_updates: 43, target_updates: 200}});
  await context.window.refreshJobs();
  assert.match(element('jobProgress').textContent, /Обучение · seed 9931 · PPO updates 43\/200/);
  assert.equal(element('jobProgressTrack').value, 21.5);
  assert.doesNotMatch(element('jobProgress').textContent, /undefined|A\/B/);
  responseJob.pilot_progress = {phase: 'evaluate_19999_rough', ppo_updates: 200};
  responseJob.recipe_progress = {phase: 'evaluate_19999_rough', seed: 9931,
    completed_updates: 200, target_updates: 200, completed_evaluations: 1, total_evaluations: 24};
  await context.window.refreshJobs();
  assert.match(element('jobProgress').textContent, /Оценка v2 · 19999_rough/);
  assert.match(element('jobProgress').textContent, /варианты 1\/24/);
  assert.equal(element('jobProgressTrack').value, 100/24);
  assert.match(element('jobProgressLabel').textContent, /Оценка v2/);

  responseJob = job('upstream_vendor_5000', {entrypoint: 'scripts/run_upstream_5000.py',
    pilot_progress: {phase: 'training', ppo_updates: 0},
    recipe_progress: {phase: 'training', seed: 44, completed_updates: 102, target_updates: 5000}});
  await context.window.refreshJobs();
  assert.match(element('jobProgress').textContent, /Обучение · seed 44 · PPO updates 102\/5000/);
  assert.equal(element('jobProgressTrack').value, 2.04);
  assert.doesNotMatch(element('jobProgress').textContent, /undefined|A\/B/);

  responseJob = job('evaluation', {evaluation_progress: {completed: ['flat'], total_jobs: 4, active: ['rough'], failures: []}});
  await context.window.refreshJobs();
  assert.match(element('jobIdentity').textContent, /evaluation/);
  assert.match(element('jobProgress').textContent, /1\/4/);
  assert.doesNotMatch(element('jobLog').textContent, /training/);
  assert.doesNotMatch(element('jobProgress').textContent, /updates/);
  assert.doesNotMatch(element('jobResult').innerHTML, /curriculum/);
  assert.equal(element('jobProgressTrack').value, 25);
  assert.match(element('jobProgressLabel').textContent, /Оценка/);

  responseJob.pilot_progress = {phase: 'probe_parent'};
  responseJob.training_progress = {status: 'running', completed_updates: 300, target_updates: 300};
  await context.window.refreshJobs();
  assert.equal(element('jobProgressTrack').value, 25);
  assert.doesNotMatch(element('jobProgress').textContent, /updates/);

  responseJob.status = 'completed'; responseJob.returncode = 0;
  responseJob.evaluation_progress.completed = ['flat','rough','up','down'];
  await context.window.refreshJobs();
  assert.match(element('runStatus').textContent, /Завершён · exit 0/);
  assert.equal(element('jobProgressTrack').value, 100);
  fail = true;
  await context.window.refreshJobs();
  assert.match(element('jobMessage').textContent, /offline/);
  assert.equal(element('connection').textContent, 'Нет связи');
  assert.match(element('jobIdentity').textContent, /evaluation/);
  fail = false; responseJob = job('failed', {status: 'failed', returncode: 7, error: 'worker failure'});
  await context.window.refreshJobs();
  assert.match(element('runStatus').textContent, /Ошибка · exit 7/);
  assert.equal(element('jobMessage').textContent, 'worker failure');
  assert.equal(element('jobProgressTrack').hidden, true);

  responseJob = job('queued', {status: 'queued'});
  await context.window.refreshJobs();
  assert.equal(element('jobProgressTrack').value, undefined);
  assert.equal(element('jobProgressTrack').hidden, false);

  responseJob = job('cancelled', {status: 'cancelled', training_progress: {completed_updates: 75, target_updates: 300}});
  await context.window.refreshJobs();
  assert.equal(element('jobProgressTrack').value, 25);
  assert.match(element('jobProgressBar').className, /cancelled/);

  responseJob = null;
  await context.window.refreshJobs();
  assert.equal(element('jobDetail').hidden, true);
  assert.equal(element('jobEmpty').hidden, false);
  assert.equal(element('jobLog').textContent, '');
  assert.equal(element('jobMessage').hidden, true);
  assert.ok(requested.every(url => url === '/api/current'));
  if (process.argv.includes('--live')) {
    responseJob = (await (await fetch('http://127.0.0.1:8765/api/current')).json()).job;
    assert.ok(responseJob.training_progress || responseJob.recipe_progress,
      'Current run progress must be available');
    await context.window.refreshJobs();
    assert.equal(element('jobMessage').hidden, true, element('jobMessage').textContent);
    assert.doesNotMatch(element('jobProgress').textContent, /undefined/);
    console.log(`Live job ${responseJob.id}: ${element('jobProgress').textContent}; ${element('jobProgressValue').textContent}`);
  }
  console.log('Current-run dashboard UI checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
