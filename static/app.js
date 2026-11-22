'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const missing = n => n == null || Number(n) < 0;
const number = n => missing(n) ? 'Unavailable' : Number(n).toLocaleString();
const money = n => missing(n) ? 'Unavailable' : '$' + Number(n).toLocaleString();
const percent = v => (v * 100).toFixed(1) + '%';
const minutes = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
const clock = total => {
  const value = typeof total === 'string' ? minutes(total) : total;
  const h = Math.floor(value / 60), m = value % 60;
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
};
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const SCREENS = {
  coordinate: 'Coordination studio',
  research: 'Research atlas',
  learning: 'Learning lab',
  simulation: 'Simulator & local model',
  sources: 'Sources & boundaries',
};
const OUTCOME_LABELS = {
  on_time: 'On time', late: 'Late', declined: 'Declined',
  provider_withdrawal: 'Provider withdrew', funding_failure: 'Funding failed',
};
const outcomeLabel = key => OUTCOME_LABELS[key] || key;

let currentPlan = null;
let noticeTimer;
let searchToken = 0;

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'The request failed.');
  return data;
}

function notify(message, error = false) {
  clearTimeout(noticeTimer);
  if (error) {
    $('notice').hidden = true;
    $('alert-text').textContent = message;
    $('alert').hidden = false;
    return;
  }
  $('alert').hidden = true;
  $('notice').textContent = message;
  $('notice').hidden = false;
  noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 9000);
}

async function busy(button, task) {
  if (button.disabled) return;
  button.disabled = true;
  try { await task(); } catch (e) { notify(e.message, true); }
  finally { button.disabled = false; }
}

function navigate(moveFocus = true) {
  const hash = location.hash.slice(1);
  const key = Object.hasOwn(SCREENS, hash) ? hash : 'coordinate';
  document.querySelectorAll('.screen').forEach(s => { s.hidden = s.id !== key; });
  document.querySelectorAll('[data-nav]').forEach(a => {
    const active = a.dataset.nav === key;
    a.classList.toggle('active', active);
    if (active) { a.setAttribute('aria-current', 'page'); a.scrollIntoView({block: 'nearest', inline: 'nearest'}); }
    else a.removeAttribute('aria-current');
  });
  document.title = `${SCREENS[key]} · FirstStep`;
  if (moveFocus) { window.scrollTo(0, 0); document.querySelector(`#${key} h1`).focus({preventScroll: true}); }
  if (key === 'research') searchResearch().catch(e => notify(e.message, true));
  if (key === 'learning') refreshLearning().catch(e => notify(e.message, true));
  if (key === 'simulation') refreshModel().catch(e => notify(e.message, true));
}

function timetable(plan) {
  const s = plan.selected, c = plan.case;
  const pickup = minutes(c.shift_end) + s.care.pickup_minutes;
  const margin = minutes(c.shift_start) - minutes(s.ride.arrival);
  const spare = minutes(s.care.closes) - pickup;
  const required = plan.policy.arrival_buffer_minutes;
  const stops = [
    [s.care.opens, `${s.care.name} opens`, 'Drop-off starts', 'care', 'care'],
    [s.ride.departure, `${s.ride.name} departs`, 'After drop-off', 'ride', 'ride'],
    [s.ride.arrival, 'Arrive at work', `${margin} min before the shift, ${required} min required`, 'ride', 'idle'],
    [c.shift_start, 'Shift starts', '', 'work', 'work'],
    [c.shift_end, 'Shift ends', '', 'work', 'care'],
    [pickup, 'Pick up child', `${s.care.pickup_minutes} min after the shift`, 'care', 'idle'],
    [s.care.closes, `${s.care.name} closes`, `${spare} min to spare`, 'care', 'idle'],
  ];
  return `<ol class="timetable" aria-label="First-day timetable">${stops.map(([time, title, note, stop, leg], i) => `<li class="${stop} i${i}"><time>${clock(time)}</time><span class="node ${leg === 'idle' ? 'idle' : leg}" aria-hidden="true"></span><div class="stop">${esc(title)}${note ? `<small>${esc(note)}</small>` : ''}</div></li>`).join('')}</ol>`;
}

function renderPlan(plan) {
  currentPlan = plan;
  sessionStorage.setItem('firststep.plan', plan.id);
  const labels = {prepared: 'Ready for consent', blocked: 'Needs another resource', committed: 'Demo confirmed', failed: 'Disruption recorded', completed: 'Demo completed'};
  const tones = {prepared: '', blocked: 'warn', committed: 'ok', failed: 'warn', completed: 'ok'};
  $('plan-badge').textContent = labels[plan.status];
  $('plan-badge').className = `tag ${tones[plan.status]}`.trim();
  $('steps').innerHTML = `<ol class="trail">${plan.steps.map((s, i) => `<li class="${esc(s.state)}"><span class="mark">${s.state === 'verified' ? icon('check') : i + 1}</span><span>${esc(s.label)}</span></li>`).join('')}</ol>`;
  const rejects = `<details><summary>Why other combinations were excluded (${plan.rejected.length})</summary><ul>${plan.rejected.map(r => `<li><strong>${esc(r.care.name)} + ${esc(r.ride.name)}</strong><br>${r.reasons.map(esc).join(' ')}</li>`).join('')}</ul></details>`;
  if (!plan.feasible) {
    $('plan-content').innerHTML = `<div class="callout"><strong>No feasible arrangement yet.</strong><p>${esc(plan.explanation)}</p><p>Review the rejected combinations below to see the specific budget, schedule, age, or availability constraint.</p></div>${rejects}`;
    return;
  }
  const s = plan.selected;
  $('plan-content').innerHTML = `
    <div class="plan-summary"><h3>${esc(plan.case.name)}’s first-day plan</h3><p>${clock(plan.case.shift_start)} to ${clock(plan.case.shift_end)} shift · Policy v${plan.policy.version}</p></div>
    <div class="plan-body">
      ${timetable(plan)}
      <div>
        <dl class="costs">
          <div><dt>${esc(s.care.name)}</dt><dd>${money(s.care.weekly)}</dd></div>
          <div><dt>${esc(s.ride.name)}</dt><dd>${money(s.ride.weekly)}</dd></div>
          <div class="total"><dt>Per week</dt><dd>${money(s.weekly)}</dd></div>
        </dl>
        <p class="costs-note">${money(plan.case.weekly_budget - s.weekly)} under the weekly budget. ${money(s.deposit)} deposit fits the ${money(plan.case.bridge_budget)} bridge budget, conditional on the complete demo arrangement.</p>
      </div>
    </div>
    <p class="plan-note">${esc(plan.explanation)}</p>
    ${plan.status === 'prepared' ? '<label class="consent"><input type="checkbox" id="consent">I understand this is a simulation and consent to confirming the demo arrangement.</label><button id="confirm-button" class="button primary">Confirm demo arrangement</button>' : ''}
    ${plan.status === 'committed' ? '<div class="actions"><button class="button secondary" id="complete-button">Record on-time start</button><button class="button secondary" id="delay-button">Record 15-minute delay</button><button class="button danger" id="withdraw-button">Simulate provider withdrawal</button></div>' : ''}
    ${plan.status === 'failed' ? '<div class="callout">A disruption was recorded. Visit the Learning lab to evaluate a better arrival policy, or create a new plan.</div>' : ''}
    ${plan.status === 'completed' ? '<p class="plan-note">On-time start recorded for this synthetic case. No real employment outcome is claimed.</p>' : ''}
    ${rejects}<details><summary>Feasible alternatives (${plan.alternatives.length})</summary><ul>${plan.alternatives.map(a => `<li>${esc(a.care.name)} + ${esc(a.ride.name)} · ${money(a.weekly)}/week</li>`).join('') || '<li>No additional combination meets every constraint.</li>'}</ul></details>`;
  if ($('confirm-button')) $('confirm-button').onclick = () => busy($('confirm-button'), async () => {
    if (!$('consent').checked) { $('consent').focus(); throw new Error('Please confirm that you consent to this simulated arrangement.'); }
    renderPlan(await api(`/api/plans/${plan.id}/confirm`, {consent: true}));
    notify('Demo arrangement confirmed. No external bookings were made.');
  });
  for (const [id, kind] of [['withdraw-button', 'provider_withdrawal'], ['delay-button', 'transport_delay'], ['complete-button', 'on_time']]) {
    if ($(id)) $(id).onclick = () => busy($(id), async () => {
      const data = await api(`/api/plans/${plan.id}/outcome`, {kind, delay_minutes: 15});
      renderPlan(data.replacement || data.plan);
      notify(data.replacement ? 'The withdrawn offer was excluded. A replacement plan was checked against every constraint.' : kind === 'transport_delay' ? 'Delay recorded. The Learning lab can now evaluate a candidate policy.' : 'Synthetic on-time start recorded.');
    });
  }
}

function estimate(n, moe, currency = false) {
  const format = currency ? money : number;
  return `${format(n)}${!missing(n) && !missing(moe) ? `<span class="sub">± ${format(moe)}</span>` : ''}`;
}

async function searchResearch() {
  const token = ++searchToken;
  const q = $('research-search').value, kind = $('research-kind').value;
  $('research-results').innerHTML = '<p class="muted">Loading records…</p>';
  try {
    if (kind === 'providers') {
      const data = await api('/api/research/providers?q=' + encodeURIComponent(q));
      if (token !== searchToken) return;
      $('research-context').textContent = `${data.matches.toLocaleString()} matching source-listed licensed centers · showing up to 50 · file date May 25, 2025`;
      $('research-results').innerHTML = data.rows.length ? `<table><thead><tr><th>Center</th><th>Location</th><th>Licensed capacity</th><th>Contact</th></tr></thead><tbody>${data.rows.map(r => `<tr><td>${esc(r.facility_name)}<span class="sub">${esc(r.facility_type)} · ${esc(r.facility_number)}</span></td><td>${esc(r.facility_address)}<span class="sub">${esc(r.facility_city)}, CA ${esc(r.facility_zip)}</span></td><td>${esc(r.facility_capacity)}<span class="sub">Not vacancies</span></td><td>${esc(r.facility_telephone_number)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty"><h3>No matching centers</h3><p>Try a California county, city, or provider name.</p></div>';
    } else {
      const data = await api('/api/research/areas?q=' + encodeURIComponent(q) + '&level=' + kind);
      if (token !== searchToken) return;
      $('research-context').textContent = `${data.rows.length} ${data.rows.length === 1 ? 'result' : 'results'} shown (up to 30) ·${data.period} · ${data.full_database ? 'Full research database connected' : 'Bundled county extract; install the full database for tract and block-group searches'}`;
      $('research-results').innerHTML = data.rows.length ? `<table><thead><tr><th>Area</th><th>Population</th><th>Children under 6</th><th>Median household income</th><th>Households without vehicle</th></tr></thead><tbody>${data.rows.map(r => `<tr><td>${esc(r.name)}<span class="sub">${esc(r.geo_id)}</span></td><td>${estimate(r.population_estimate, r.population_moe)}</td><td>${number(r.own_children_under6)}<span class="sub">Own children in families</span></td><td>${estimate(r.median_household_income_2024_dollars, r.income_moe, true)}</td><td>${estimate(r.households_no_vehicle, r.households_no_vehicle_moe)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty"><h3>No matching areas</h3><p>Try a county name. Tract and block-group searches require the full database.</p></div>';
    }
  } catch (e) {
    if (token !== searchToken) return;
    $('research-results').innerHTML = '<div class="empty"><h3>Search failed</h3><p>Check the local data files, then search again.</p></div>';
    throw e;
  }
}

function renderEvaluation(result) {
  $('learning-results').hidden = false;
  const rows = [['On time', 'on_time'], ['Late', 'late'], ['Declined', 'declined']];
  const broader = result.broader_check;
  $('learning-results').innerHTML = `
    <div class="panel-head"><h2>${result.promoted ? 'Candidate adopted' : 'Current policy retained'}</h2><span class="tag ${result.promoted ? 'ok' : 'warn'}">Policy checks</span></div>
    <p class="muted">${esc(result.reason)}</p>
    <div class="compare"><table><thead><tr><th>Five-scenario suite</th><th>Current</th><th>Candidate</th></tr></thead><tbody>${rows.map(([label, key]) => `<tr><td>${label}</td><td>${result.baseline[key]}</td><td>${result.candidate[key]}</td></tr>`).join('')}</tbody></table></div>
    ${broader ? `<div class="compare"><table><thead><tr><th>Paired check, ${number(broader.config.cases)} households</th><th>Current</th><th>Candidate</th></tr></thead><tbody><tr><td>On-time starts</td><td>${number(broader.baseline.on_time)}</td><td>${number(broader.candidate.on_time)}</td></tr><tr><td>Late</td><td>${number(broader.baseline.late)}</td><td>${number(broader.candidate.late)}</td></tr><tr><td>Declined</td><td>${number(broader.baseline.declined)}</td><td>${number(broader.candidate.declined)}</td></tr></tbody></table></div>` : ''}
    <p class="hint">${esc(result.scope)}</p>
    <details><summary>Inspect all five scenario outcomes</summary><div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Current policy</th><th>Candidate</th></tr></thead><tbody>${result.baseline.results.map((r, i) => `<tr><td>${esc(r.id.replaceAll('_', ' '))}</td><td>${esc(outcomeLabel(r.outcome))}</td><td>${esc(outcomeLabel(result.candidate.results[i].outcome))}</td></tr>`).join('')}</tbody></table></div></details>`;
}

async function refreshEvents() {
  const events = await api('/api/events');
  $('event-list').innerHTML = events.length ? events.map(e => `<div class="event"><div>${esc(e.kind.replaceAll('_', ' '))}<span class="sub">${e.plan_id ? 'Demo plan ' + esc(e.plan_id.slice(0, 8)) : 'Scheduling policy'} · event ${e.id}</span></div><small>${esc(new Date(e.at).toLocaleTimeString())}</small></div>`).join('') : '<p class="muted">No events yet. Create a plan in the Coordination studio.</p>';
}

async function refreshLearning() {
  const l = await api('/api/learning');
  $('policy-buffer').textContent = l.policy.arrival_buffer_minutes;
  $('buffer-stat').textContent = l.policy.arrival_buffer_minutes + ' min';
  $('policy-version').textContent = 'Version ' + l.policy.version;
  $('learning-evidence').textContent = `${l.observed_delays.length} demo transport delay${l.observed_delays.length === 1 ? '' : 's'} recorded${l.observed_delays.length ? ' · largest observed delay: ' + Math.max(...l.observed_delays) + ' minutes' : ''}.`;
  $('learn-button').disabled = !l.observed_delays.length;
  if (l.latest) renderEvaluation(l.latest);
  await refreshEvents();
}

function simulationConfig() {
  const data = Object.fromEntries(new FormData($('simulation-form')));
  for (const k of Object.keys(data)) data[k] = Number(data[k]);
  for (const k of ['delay_probability', 'withdrawal_probability', 'funding_failure_probability']) data[k] /= 100;
  return data;
}

function studioCase() {
  const data = Object.fromEntries(new FormData($('case-form')));
  for (const k of ['child_age', 'weekly_budget', 'bridge_budget']) data[k] = Number(data[k]);
  return data;
}

function renderSimulation(r) {
  $('simulation-results').hidden = false;
  const summary = (name, key) => `<div><h3>${name}, ${r.config[key + '_buffer']}-minute buffer</h3><strong>${percent(r[key].on_time_rate)}</strong><span>${number(r[key].on_time)} of ${number(r.config.cases)} households on time, counting declines · ${number(r[key].feasible)} feasible plans</span></div>`;
  const points = v => (v * 100).toFixed(1);
  const cost = v => v === null ? 'Unavailable' : '$' + v.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const prediction = v => v === null ? 'Unscored' : percent(v);
  $('simulation-results').innerHTML = `
    <div class="panel-head"><h2>Two policies. The same synthetic world.</h2><span class="tag">Seed ${r.config.seed}</span></div>
    <div class="delta">${summary('Baseline', 'baseline')}${summary('Candidate', 'candidate')}</div>
    <p class="muted">Candidate difference: <strong>${r.on_time_rate_difference >= 0 ? '+' : ''}${points(r.on_time_rate_difference)} percentage points</strong>. Approximate 95% Monte Carlo interval: ${points(r.paired_95pct_interval[0])} to ${points(r.paired_95pct_interval[1])} points.</p>
    <p class="hint">${esc(r.interval_scope)}</p>
    <div class="compare"><table><thead><tr><th>Outcome</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>${[['On-time start', 'on_time'], ['Late arrival', 'late'], ['Provider withdrew', 'provider_withdrawal'], ['Funding failed', 'funding_failure'], ['No feasible plan', 'declined']].map(([label, key]) => `<tr><td>${label}</td><td>${number(r.baseline[key])}</td><td>${number(r.candidate[key])}</td></tr>`).join('')}<tr><td>Mean weekly cost of feasible plans</td><td>${cost(r.baseline.mean_feasible_weekly_cost)}</td><td>${cost(r.candidate.mean_feasible_weekly_cost)}</td></tr></tbody></table></div>
    <p class="hint">Paired outcomes: ${r.paired.improved} improved to on time, ${r.paired.worsened} lost an on-time result, ${r.paired.unchanged} unchanged in on-time status. Costs are planned costs, not measured spending.</p>
    <details><summary>Inspect the first ${r.samples.length} paired cases</summary><div class="table-wrap"><table><thead><tr><th>Household</th><th>Baseline</th><th>Candidate</th><th>Predicted on-time probability</th></tr></thead><tbody>${r.samples.map(s => `<tr><td>${esc(s.case.name)}<span class="sub">${money(s.case.weekly_budget)}/week · ${clock(s.case.shift_start)} start · delay ${s.delay_minutes} min</span></td><td>${esc(outcomeLabel(s.baseline.outcome))}</td><td>${esc(outcomeLabel(s.candidate.outcome))}</td><td>${prediction(s.baseline.prediction)} / ${prediction(s.candidate.prediction)}<span class="sub">Baseline / candidate · synthetic estimates</span></td></tr>`).join('')}</tbody></table></div></details>
    <details><summary>Inspect simulator assumptions</summary><ul>${r.assumptions.map(s => `<li>${esc(s)}</li>`).join('')}</ul></details>`;
}

function renderModel(m) {
  const e = m.evaluation, b = m.baseline_evaluation;
  $('model-summary').innerHTML = `<p class="muted">${number(m.training.train_rows)} training plans · ${number(m.training.test_rows)} separate test plans. Both sets are synthetic feasible plans.</p><div class="model-stats"><div><strong>${e.brier.toFixed(3)}</strong><span>Test Brier loss</span></div><div><strong>${b.brier.toFixed(3)}</strong><span>Constant baseline loss</span></div><div><strong>${e.auroc === null ? 'N/A' : e.auroc.toFixed(3)}</strong><span>Test AUROC</span></div></div><p class="hint">Lower Brier loss is better. AUROC measures ranking. Test accuracy: ${percent(e.accuracy)}; constant-baseline accuracy: ${percent(b.accuracy)}. Trained ${esc(new Date(m.trained_at).toLocaleString())}.</p>`;
  $('model-calibration').hidden = false;
  $('model-calibration').innerHTML = `<div class="panel-head"><h2>Held-out calibration</h2><span class="tag">Same generator, different seed</span></div><p class="muted">Predicted probabilities compared with observed synthetic outcomes in each populated bin. Small bins are noisy.</p><div class="compare"><table><thead><tr><th>Prediction range</th><th>Test cases</th><th>Mean prediction</th><th>Observed on-time rate</th></tr></thead><tbody>${e.calibration.map(c => `<tr><td>${percent(c.lower)} to ${percent(c.upper)}</td><td>${number(c.count)}</td><td>${percent(c.predicted)}</td><td>${percent(c.observed)}</td></tr>`).join('')}</tbody></table></div><details><summary>Inspect learned weights and training procedure</summary><p>Batch gradient descent · ${m.training.epochs} epochs · L2 ${m.training.l2}. Normalization statistics are fit only on training data. Train seed ${m.training.train_seed}; test seed ${m.training.test_seed}.</p><div class="compare"><table><thead><tr><th>Feature</th><th>Standardized coefficient</th></tr></thead><tbody>${m.feature_names.map((f, i) => `<tr><td>${esc(f.replaceAll('_', ' '))}</td><td>${m.weights[i].toFixed(4)}</td></tr>`).join('')}</tbody></table></div><p>Intercept: ${m.intercept.toFixed(4)}. Coefficients describe this generator, not causal effects in real families.</p></details>`;
}

async function refreshModel() {
  renderModel((await api('/api/model')).model);
  const sim = await api('/api/simulator');
  if (sim.latest) renderSimulation(sim.latest);
}

document.querySelector('.skip').addEventListener('click', e => { e.preventDefault(); $('main').focus(); });
$('alert-close').onclick = () => { $('alert').hidden = true; };
$('case-form').addEventListener('submit', e => {
  e.preventDefault();
  busy($('plan-button'), async () => {
    const fields = studioCase();
    renderPlan(await api('/api/plans', fields));
    if (matchMedia('(max-width: 960px)').matches) document.querySelector('.plan-panel').scrollIntoView();
    notify(currentPlan.feasible ? 'A complete demo plan meets the current constraints.' : 'No complete plan fits. Review the blockers in the plan.');
  });
});
$('research-button').onclick = () => busy($('research-button'), searchResearch);
$('research-search').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); searchResearch().catch(err => notify(err.message, true)); } });
$('research-kind').onchange = () => searchResearch().catch(e => notify(e.message, true));
$('learn-button').onclick = () => busy($('learn-button'), async () => {
  const data = await api('/api/learning/run', {});
  await refreshLearning();
  renderEvaluation(data.result);
  notify(data.result.reason);
});
$('refresh-events').onclick = () => busy($('refresh-events'), refreshEvents);
$('simulation-form').addEventListener('submit', e => {
  e.preventDefault();
  busy($('simulation-button'), async () => {
    renderSimulation(await api('/api/simulator/run', simulationConfig()));
    notify('Paired synthetic simulation completed. The active planning policy was not changed.');
  });
});
$('train-model-button').onclick = () => busy($('train-model-button'), async () => {
  const button = $('train-model-button'), original = button.textContent;
  button.textContent = 'Training locally…';
  try {
    renderModel((await api('/api/model/train', {train_count: 4000, test_count: 1000, seed: 20261122})).model);
    notify('Local model trained and saved. Metrics use a separate synthetic test set.');
  } finally { button.textContent = original; }
});
$('score-model-button').onclick = () => busy($('score-model-button'), async () => {
  const r = await api('/api/model/predict', {case: studioCase(), context: simulationConfig()});
  $('model-prediction').innerHTML = `<div class="callout neutral"><strong>${r.prediction.probability === null ? 'Not scored' : percent(r.prediction.probability) + ' synthetic on-time probability'}</strong><p>${esc(r.prediction.reason)}</p></div>`;
});
window.addEventListener('hashchange', () => navigate());

api('/api/bootstrap').then(data => {
  $('geo-count').textContent = number(data.stats.geographies);
  $('buffer-stat').textContent = data.learning.policy.arrival_buffer_minutes + ' min';
  $('offer-count').textContent = data.cares.length * data.rides.length;
  navigate(false);
  const saved = sessionStorage.getItem('firststep.plan');
  if (saved) api('/api/plans/' + encodeURIComponent(saved)).then(plan => { if (!currentPlan) renderPlan(plan); }).catch(() => sessionStorage.removeItem('firststep.plan'));
}).catch(e => notify('Could not load the workspace: ' + e.message, true));
