'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => n == null || Number(n) < 0 ? 'Unavailable' : Number(n).toLocaleString();
const money = n => '$' + number(n);
let currentPlan = null;
let noticeTimer;
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'The request failed.');
  return data;
}
function notify(message, error=false) {
  clearTimeout(noticeTimer); $('notice').hidden=false; $('notice').className=error?'error':'';
  $('notice').textContent=message;
  noticeTimer=setTimeout(()=>{$('notice').hidden=true;},9000);
}
async function busy(button, task) {
  if (button.disabled) return;
  button.disabled=true;
  try { await task(); } catch(e) { notify(e.message,true); }
  finally { button.disabled=false; }
}
function navigate() {
  const key=['coordinate','research','learning','simulation','sources'].includes(location.hash.slice(1))?location.hash.slice(1):'coordinate';
  document.querySelectorAll('.screen').forEach(s=>s.hidden=s.id!==key);
  document.querySelectorAll('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===key);if(a.dataset.nav===key)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('page-label').textContent={coordinate:'Coordination studio',research:'Research atlas',learning:'Learning lab',simulation:'Simulator & local model',sources:'Sources & boundaries'}[key];
  if(key==='research') searchResearch().catch(e=>notify(e.message,true));
  if(key==='learning') refreshLearning().catch(e=>notify(e.message,true));
  if(key==='simulation') refreshModel().catch(e=>notify(e.message,true));
}
function renderPlan(plan) {
  currentPlan=plan;
  sessionStorage.setItem('firststep.plan',plan.id);
  const labels={prepared:'Ready for consent',blocked:'Needs another resource',committed:'Demo confirmed',failed:'Disruption recorded',completed:'Demo completed'};
  $('plan-badge').textContent=labels[plan.status];
  $('plan-badge').className='badge '+(plan.status==='blocked'||plan.status==='failed'?'orange':plan.status==='committed'||plan.status==='completed'?'green':'purple');
  $('steps').innerHTML=plan.steps.map((s,i)=>`<div class="step ${esc(s.state)}"><span class="step-icon">${s.state==='verified'?'✓':i+1}</span><span class="step-text">${esc(s.label)}</span></div>`).join('');
  const rejects=`<details><summary>Why other combinations were excluded (${plan.rejected.length})</summary><ul>${plan.rejected.map(r=>`<li><strong>${esc(r.care.name)} + ${esc(r.ride.name)}</strong><br>${r.reasons.map(esc).join(' ')}</li>`).join('')}</ul></details>`;
  if(!plan.feasible){$('plan-content').innerHTML=`<div class="blocked-message"><strong>No feasible arrangement yet.</strong><p>${esc(plan.explanation)}</p><p>Review the rejected combinations below to see the specific budget, schedule, age, or availability constraint.</p></div>${rejects}`;return;}
  const s=plan.selected;
  $('plan-content').innerHTML=`<div class="plan-summary"><div><h3>${esc(plan.case.name)}’s first-day plan</h3><p>${esc(plan.case.shift_start)}–${esc(plan.case.shift_end)} shift · Policy v${plan.policy.version}</p></div><div class="price">${money(s.weekly)}<small>per week · ${money(plan.case.weekly_budget-s.weekly)} within budget</small></div></div>
    <div class="arrangement"><div class="arrangement-card"><span class="card-icon">C</span><div><h3>${esc(s.care.name)}</h3><p>${esc(s.care.opens)}–${esc(s.care.closes)} · ${money(s.care.weekly)}/week</p></div><span class="card-status">Demo offer</span></div><div class="arrangement-card"><span class="card-icon">T</span><div><h3>${esc(s.ride.name)}</h3><p>Depart ${esc(s.ride.departure)} · arrive ${esc(s.ride.arrival)} · ${money(s.ride.weekly)}/week</p></div><span class="card-status">Schedule fits</span></div><div class="arrangement-card"><span class="card-icon">F</span><div><h3>${money(s.deposit)} deposit within bridge budget</h3><p>Conditional on the complete demo arrangement</p></div><span class="card-status">Budget fits</span></div></div>
    <p class="plan-note">${esc(plan.explanation)} Required arrival buffer: ${plan.policy.arrival_buffer_minutes} minutes.</p>
    ${plan.status==='prepared'?'<label class="consent"><input type="checkbox" id="consent">I understand this is a simulation and consent to confirming the demo arrangement.</label><button id="confirm-button" class="button primary">Confirm demo arrangement</button>':''}
    ${plan.status==='committed'?'<div class="actions"><button class="button danger" id="withdraw-button">Simulate provider withdrawal</button><button class="button secondary" id="delay-button">Record 15-minute delay</button><button class="button secondary" id="complete-button">Record on-time start</button></div>':''}
    ${plan.status==='failed'?'<div class="blocked-message">A disruption was recorded. Visit the Learning lab to evaluate a better arrival policy, or create a new plan.</div>':''}
    ${plan.status==='completed'?'<p class="plan-note">On-time start recorded for this synthetic case. No real employment outcome is claimed.</p>':''}
    ${rejects}<details><summary>Feasible alternatives (${plan.alternatives.length})</summary><ul>${plan.alternatives.map(a=>`<li>${esc(a.care.name)} + ${esc(a.ride.name)} · ${money(a.weekly)}/week</li>`).join('')||'<li>No additional combination meets every constraint.</li>'}</ul></details>`;
  if($('confirm-button'))$('confirm-button').onclick=()=>busy($('confirm-button'),async()=>{
    if(!$('consent').checked)throw new Error('Please confirm that you consent to this simulated arrangement.');
    renderPlan(await api(`/api/plans/${plan.id}/confirm`,{consent:true}));notify('Demo arrangement confirmed. No external bookings were made.');
  });
  for(const [id,kind] of [['withdraw-button','provider_withdrawal'],['delay-button','transport_delay'],['complete-button','on_time']]){
    if($(id))$(id).onclick=()=>busy($(id),async()=>{
      const data=await api(`/api/plans/${plan.id}/outcome`,{kind,delay_minutes:15});
      renderPlan(data.replacement||data.plan);
      notify(data.replacement?'The withdrawn offer was excluded. A replacement plan was checked against every constraint.':kind==='transport_delay'?'Delay recorded. The Learning lab can now evaluate a candidate policy.':'Synthetic on-time start recorded.');
    });
  }
}
function estimate(n,moe,currency=false){return `${currency?money(n):number(n)}${moe!=null&&moe>=0?`<span class="table-secondary">± ${number(moe)}</span>`:''}`;}
async function searchResearch(){
  const q=$('research-search').value,kind=$('research-kind').value;
  $('research-results').innerHTML='<p class="muted">Loading records…</p>';
  if(kind==='providers'){
    const data=await api('/api/research/providers?q='+encodeURIComponent(q));
    $('research-context').textContent=`${data.matches.toLocaleString()} matching source-listed licensed centers · showing up to 50 · file date May 25, 2025`;
    $('research-results').innerHTML=data.rows.length?`<table><thead><tr><th>Center</th><th>Location</th><th>Licensed capacity</th><th>Contact</th></tr></thead><tbody>${data.rows.map(r=>`<tr><td>${esc(r.facility_name)}<span class="table-secondary">${esc(r.facility_type)} · ${esc(r.facility_number)}</span></td><td>${esc(r.facility_address)}<span class="table-secondary">${esc(r.facility_city)}, CA ${esc(r.facility_zip)}</span></td><td>${esc(r.facility_capacity)}<span class="table-secondary">Not vacancies</span></td><td>${esc(r.facility_telephone_number)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty"><h3>No matching centers</h3><p>Try a California county, city, or provider name.</p></div>';
  }else{
    const data=await api('/api/research/areas?q='+encodeURIComponent(q)+'&level='+kind);
    $('research-context').textContent=`${data.rows.length} results shown (up to 30) · ${data.period} · ${data.full_database?'Full research database connected':'Bundled county extract; install the full database for tract and block-group searches'}`;
    $('research-results').innerHTML=data.rows.length?`<table><thead><tr><th>Area</th><th>Population</th><th>Children under 6</th><th>Median household income</th><th>Households without vehicle</th></tr></thead><tbody>${data.rows.map(r=>`<tr><td>${esc(r.name)}<span class="table-secondary">${esc(r.geo_id)}</span></td><td>${estimate(r.population_estimate,r.population_moe)}</td><td>${number(r.own_children_under6)}<span class="table-secondary">Own children in families</span></td><td>${estimate(r.median_household_income_2024_dollars,r.income_moe,true)}</td><td>${estimate(r.households_no_vehicle,r.households_no_vehicle_moe)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty"><h3>No matching areas</h3><p>Try a county name. Tract and block-group searches require the full database.</p></div>';
  }
}
function renderEvaluation(result){
  $('learning-results').hidden=false;
  const column=(name,r)=>`<div class="eval-column"><h3>${name}</h3>${[['On time','on_time',''],['Late','late','late'],['Declined','declined','declined']].map(([label,key,cls])=>`<div class="eval-row"><span>${label}</span><progress class="${cls}" value="${r[key]}" max="5" aria-label="${name}: ${label}"></progress><strong>${r[key]}</strong></div>`).join('')}</div>`;
  $('learning-results').innerHTML=`<div class="panel-title"><h2>${result.promoted?'Candidate adopted':'Current policy retained'}</h2><span class="badge ${result.promoted?'green':'orange'}">Policy checks</span></div><p class="muted">${esc(result.reason)}</p><div class="eval-grid">${column('Small suite: current',result.baseline)}${column('Small suite: candidate',result.candidate)}</div>${result.broader_check?`<div class="inset-note"><strong>Broader paired check · ${result.broader_check.config.cases} households</strong><p>On-time starts: ${result.broader_check.baseline.on_time} current / ${result.broader_check.candidate.on_time} candidate. Declines: ${result.broader_check.baseline.declined} current / ${result.broader_check.candidate.declined} candidate.</p></div>`:''}<p class="small muted">${esc(result.scope)}</p><details><summary>Inspect all five scenario outcomes</summary><table><thead><tr><th>Scenario</th><th>Current policy</th><th>Candidate</th></tr></thead><tbody>${result.baseline.results.map((r,i)=>`<tr><td>${esc(r.id)}</td><td>${esc(r.outcome)}</td><td>${esc(result.candidate.results[i].outcome)}</td></tr>`).join('')}</tbody></table></details>`;
}
async function refreshEvents(){
  const events=await api('/api/events');
  $('event-list').innerHTML=events.length?events.map(e=>`<div class="event"><div>${esc(e.kind.replaceAll('_',' '))}<span class="table-secondary">${e.plan_id?'Demo plan '+esc(e.plan_id.slice(0,8)):'Scheduling policy'} · event ${e.id}</span></div><small>${esc(new Date(e.at).toLocaleTimeString())}</small></div>`).join(''):'<p class="muted">No events yet. Create a plan in the Coordination studio.</p>';
}
async function refreshLearning(){
  const l=await api('/api/learning');
  $('policy-buffer').textContent=l.policy.arrival_buffer_minutes;
  $('buffer-stat').textContent=l.policy.arrival_buffer_minutes+' min';
  $('policy-version').textContent='Version '+l.policy.version;
  $('learning-evidence').textContent=`${l.observed_delays.length} demo transport delay${l.observed_delays.length===1?'':'s'} recorded${l.observed_delays.length?' · largest observed delay: '+Math.max(...l.observed_delays)+' minutes':''}.`;
  $('learn-button').disabled=!l.observed_delays.length;
  if(l.latest)renderEvaluation(l.latest);
  await refreshEvents();
}
$('case-form').addEventListener('submit',e=>{
  e.preventDefault();busy($('plan-button'),async()=>{
    const fields=Object.fromEntries(new FormData(e.target));
    for(const key of ['child_age','weekly_budget','bridge_budget'])fields[key]=Number(fields[key]);
    renderPlan(await api('/api/plans',fields));notify(currentPlan.feasible?'A complete demo plan meets the current constraints.':'No complete plan fits. Review the blockers below.');
  });
});
$('research-button').onclick=()=>busy($('research-button'),searchResearch);
$('research-search').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('research-button').click();}});
$('research-kind').onchange=()=>busy($('research-button'),searchResearch);
$('learn-button').onclick=()=>busy($('learn-button'),async()=>{const data=await api('/api/learning/run',{});await refreshLearning();renderEvaluation(data.result);notify(data.result.reason);});
$('refresh-events').onclick=()=>busy($('refresh-events'),refreshEvents);
const percent=v=>(v*100).toFixed(1)+'%';
function simulationConfig(){
  const data=Object.fromEntries(new FormData($('simulation-form')));
  for(const k of Object.keys(data))data[k]=Number(data[k]);
  for(const k of ['delay_probability','withdrawal_probability','funding_failure_probability'])data[k]/=100;
  return data;
}
function studioCase(){
  const data=Object.fromEntries(new FormData($('case-form')));
  for(const k of ['child_age','weekly_budget','bridge_budget'])data[k]=Number(data[k]);
  return data;
}
function renderSimulation(r){
  $('simulation-results').hidden=false;
  const summary=(name,key)=>`<div class="eval-column"><h3>${name} · ${r.config[key+'_buffer']}-minute buffer</h3><div class="policy-number"><strong>${percent(r[key].on_time_rate)}</strong><span>on-time synthetic starts, including declines in denominator</span></div><p class="muted">${number(r[key].on_time)} of ${number(r.config.cases)} households · ${number(r[key].feasible)} feasible plans</p></div>`;
  $('simulation-results').innerHTML=`<div class="panel-title"><h2>Two policies. The same synthetic world.</h2><span class="badge purple">Seed ${r.config.seed}</span></div><div class="eval-grid">${summary('Baseline','baseline')}${summary('Candidate','candidate')}</div><p class="muted">Candidate difference: <strong>${r.on_time_rate_difference>=0?'+':''}${(r.on_time_rate_difference*100).toFixed(1)} percentage points</strong>. Approximate 95% Monte Carlo interval: ${(r.paired_95pct_interval[0]*100).toFixed(1)} to ${(r.paired_95pct_interval[1]*100).toFixed(1)} points.</p><p class="small muted">${esc(r.interval_scope)}</p><div class="table-panel"><table><thead><tr><th>Outcome</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>${[['On-time start','on_time'],['Late arrival','late'],['Provider withdrew','provider_withdrawal'],['Funding failed','funding_failure'],['No feasible plan','declined']].map(([label,key])=>`<tr><td>${label}</td><td>${number(r.baseline[key])}</td><td>${number(r.candidate[key])}</td></tr>`).join('')}<tr><td>Mean weekly cost of feasible plans</td><td>${r.baseline.mean_feasible_weekly_cost===null?'Unavailable':money(r.baseline.mean_feasible_weekly_cost)}</td><td>${r.candidate.mean_feasible_weekly_cost===null?'Unavailable':money(r.candidate.mean_feasible_weekly_cost)}</td></tr></tbody></table></div><p class="small muted">Paired outcomes: ${r.paired.improved} improved to on time, ${r.paired.worsened} lost an on-time result, ${r.paired.unchanged} unchanged in on-time status. Costs are planned costs, not measured spending.</p><details><summary>Inspect the first ${r.samples.length} paired cases</summary><div class="table-panel"><table><thead><tr><th>Household</th><th>Baseline</th><th>Candidate</th><th>Predicted on-time probability</th></tr></thead><tbody>${r.samples.map(s=>`<tr><td>${esc(s.case.name)}<span class="table-secondary">${money(s.case.weekly_budget)}/week · ${esc(s.case.shift_start)} start · delay ${s.delay_minutes} min</span></td><td>${esc(s.baseline.outcome)}</td><td>${esc(s.candidate.outcome)}</td><td>${s.baseline.prediction===null?'Unscored':percent(s.baseline.prediction)} / ${s.candidate.prediction===null?'Unscored':percent(s.candidate.prediction)}<span class="table-secondary">Baseline / candidate · synthetic estimates</span></td></tr>`).join('')}</tbody></table></div></details><details><summary>Inspect simulator assumptions</summary><ul>${r.assumptions.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></details>`;
}
function renderModel(m){
  const e=m.evaluation,b=m.baseline_evaluation;
  $('model-summary').innerHTML=`<p class="muted">${number(m.training.train_rows)} training plans · ${number(m.training.test_rows)} separate test plans. Both sets are synthetic feasible plans.</p><div class="model-stats"><div><strong>${e.brier.toFixed(3)}</strong><span>Test Brier loss</span></div><div><strong>${b.brier.toFixed(3)}</strong><span>Constant baseline loss</span></div><div><strong>${e.auroc===null?'N/A':e.auroc.toFixed(3)}</strong><span>Test AUROC</span></div></div><p class="small muted">Lower Brier loss is better. AUROC measures ranking. Test accuracy: ${percent(e.accuracy)}; constant-baseline accuracy: ${percent(b.accuracy)}. Trained ${esc(new Date(m.trained_at).toLocaleString())}.</p>`;
  $('model-calibration').hidden=false;
  $('model-calibration').innerHTML=`<div class="panel-title"><h2>Held-out calibration</h2><span class="badge">Same generator · different seed</span></div><p class="muted">Predicted probabilities compared with observed synthetic outcomes in each populated bin. Small bins are noisy.</p><div class="table-panel"><table><thead><tr><th>Prediction range</th><th>Test cases</th><th>Mean prediction</th><th>Observed on-time rate</th></tr></thead><tbody>${e.calibration.map(c=>`<tr><td>${percent(c.lower)}–${percent(c.upper)}</td><td>${number(c.count)}</td><td>${percent(c.predicted)}</td><td>${percent(c.observed)}</td></tr>`).join('')}</tbody></table></div><details><summary>Inspect learned weights and training procedure</summary><p>Batch gradient descent · ${m.training.epochs} epochs · L2 ${m.training.l2}. Normalization statistics are fit only on training data. Train seed ${m.training.train_seed}; test seed ${m.training.test_seed}.</p><table><thead><tr><th>Feature</th><th>Standardized coefficient</th></tr></thead><tbody>${m.feature_names.map((f,i)=>`<tr><td>${esc(f)}</td><td>${m.weights[i].toFixed(4)}</td></tr>`).join('')}</tbody></table><p>Intercept: ${m.intercept.toFixed(4)}. Coefficients describe this generator, not causal effects in real families.</p></details>`;
}
async function refreshModel(){
  renderModel((await api('/api/model')).model);
  const sim=await api('/api/simulator');
  if(sim.latest)renderSimulation(sim.latest);
}
$('simulation-form').addEventListener('submit',e=>{
  e.preventDefault();busy($('simulation-button'),async()=>{renderSimulation(await api('/api/simulator/run',simulationConfig()));notify('Paired synthetic simulation completed. The active planning policy was not changed.');});
});
$('train-model-button').onclick=()=>busy($('train-model-button'),async()=>{
  const button=$('train-model-button'),original=button.textContent;button.textContent='Training locally…';
  try {renderModel((await api('/api/model/train',{train_count:4000,test_count:1000,seed:20261122})).model);notify('Local model trained and saved. Metrics use a separate synthetic test set.');}
  finally {button.textContent=original;}
});
$('score-model-button').onclick=()=>busy($('score-model-button'),async()=>{
  const r=await api('/api/model/predict',{case:studioCase(),context:simulationConfig()});
  $('model-prediction').innerHTML=`<div class="inset-note"><strong>${r.prediction.probability===null?'Not scored':percent(r.prediction.probability)+' synthetic on-time probability'}</strong><p>${esc(r.prediction.reason)}</p></div>`;
});
window.addEventListener('hashchange',navigate);
api('/api/bootstrap').then(data=>{
  $('geo-count').textContent=number(data.stats.geographies);
  $('buffer-stat').textContent=data.learning.policy.arrival_buffer_minutes+' min';
  $('offer-count').textContent=data.cares.length*data.rides.length;
  navigate();
  const saved=sessionStorage.getItem('firststep.plan');
  if(saved)api('/api/plans/'+encodeURIComponent(saved)).then(renderPlan).catch(()=>sessionStorage.removeItem('firststep.plan'));
}).catch(e=>notify('Could not load the workspace: '+e.message,true));
