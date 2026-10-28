/* RetailIQ Week 1 — framework-free local UI; no credentials or provider keys in browser. */
'use strict';

const byId = (id) => document.getElementById(id);
let roiLoaded = false;
let askInProgress = false;
let activeSessionId = '';

async function ensureSession() {
  if (activeSessionId) return activeSessionId;
  const response = await fetch('/api/sessions', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({})
  });
  if (!response.ok) throw new Error('Cannot create local chat session');
  const session = await response.json();
  activeSessionId = session.id;
  localStorage.setItem('retailiq-active-session', activeSessionId);
  await refreshSessions();
  return activeSessionId;
}

async function refreshSessions() {
  const response = await fetch('/api/sessions');
  if (!response.ok) throw new Error('Unable to read local sessions');
  const data = await response.json();
  const picker = byId('chat-session-picker');
  picker.replaceChildren();
  for (const s of data.sessions) {
    const option = document.createElement('option');
    option.value = s.id;
    option.textContent = s.title;
    picker.appendChild(option);
  }
  if (data.sessions.some(s => s.id === activeSessionId)) picker.value = activeSessionId;
}

function renderChatMessages(messages) {
  const area = byId('chat-history');
  area.replaceChildren();
  for (const message of messages) {
    const item = document.createElement('div');
    item.className = 'chat-message chat-message-' + message.role;
    const label = document.createElement('span');
    label.className = 'chat-message-label';
    label.textContent = message.role === 'user' ? 'YOU' : (message.agent || 'RETAILIQ').replaceAll('_', ' ').toUpperCase();
    const content = document.createElement('span');
    content.textContent = message.content;
    item.append(label, content);
    area.appendChild(item);
  }
  area.scrollTop = area.scrollHeight;
}

async function selectSession(id) {
  const response = await fetch('/api/sessions/' + encodeURIComponent(id));
  if (!response.ok) throw new Error('Session no longer exists');
  const session = await response.json();
  activeSessionId = id;
  localStorage.setItem('retailiq-active-session', id);
  byId('chat-session-picker').value = id;
  renderChatMessages(session.messages || []);
  const last = [...(session.messages || [])].reverse().find(x => x.role === 'assistant');
  byId('answer').textContent = last ? last.content : 'New conversation. Ask your first retail question.';
  byId('meta').textContent = last ? 'Last agent: ' + (session.active_agent || 'unknown') : 'No execution yet.';
  byId('agent-trace').replaceChildren();
}

async function createNewChat() {
  activeSessionId = '';
  await ensureSession();
  await selectSession(activeSessionId);
  byId('q').value = '';
  byId('q').focus();
}

async function deleteCurrentChat() {
  if (!activeSessionId) return;
  if (!confirm('Delete this local conversation and all messages?')) return;
  const response = await fetch('/api/sessions/' + encodeURIComponent(activeSessionId), {method: 'DELETE'});
  if (!response.ok) throw new Error('Unable to delete session');
  activeSessionId = '';
  localStorage.removeItem('retailiq-active-session');
  await refreshSessions();
  const next = byId('chat-session-picker').value;
  if (next) await selectSession(next);
  else await createNewChat();
}

async function initializeSessions() {
  try {
    await refreshSessions();
    const stored = localStorage.getItem('retailiq-active-session');
    const options = [...byId('chat-session-picker').options].map(o => o.value);
    const id = options.includes(stored) ? stored : options[0];
    if (id) await selectSession(id);
    else await createNewChat();
  } catch (err) {
    byId('meta').textContent = 'Session manager unavailable: ' + err.message;
  }
}

function showAgentEvidence(data) {
  const area = byId('agent-trace');
  area.replaceChildren();
  const chips = [];
  if (data.active_agent) chips.push(['Agent: ' + data.active_agent, '']);
  if (data.skill) chips.push(['Skill: ' + data.skill, 'agent-chip-skill']);
  if (data.handoff) chips.push(['Handoff: ' + data.handoff.from + ' → ' + data.handoff.to, 'agent-chip-handoff']);
  for (const name of data.subagents || []) chips.push(['Subagent: ' + name, '']);
  for (const [text, type] of chips) {
    const chip = document.createElement('span');
    chip.className = 'agent-chip ' + type;
    chip.textContent = text;
    area.appendChild(chip);
  }
}

function showPanel(name) {
  const roi = name === 'roi';
  byId('assistant-panel').hidden = roi;
  byId('roi-panel').hidden = !roi;
  byId('tab-assistant').setAttribute('aria-selected', String(!roi));
  byId('tab-roi').setAttribute('aria-selected', String(roi));
  if (roi && !roiLoaded) { roiLoaded = true; estimateROI(); }
}

function sample(question) {
  byId('q').value = question;
  showPanel('assistant');
  ask();
}

async function ask() {
  if (askInProgress) return;
  const question = byId('q').value.trim();
  if (question.length < 3) { byId('q').reportValidity(); return; }
  askInProgress = true;
  const button = byId('ask-submit');
  const answer = byId('answer');
  button.disabled = true;
  answer.classList.remove('is-placeholder', 'is-error');
  answer.textContent = 'Looking through your retail data…';
  byId('response-state').textContent = 'WORKING';
  try {
    const sessionId = await ensureSession();
    const response = await fetch('/ask', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question, session_id: sessionId})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed (' + response.status + ')');
    answer.textContent = data.answer || 'No answer available for this question.';
    await refreshSessions();
    await selectSession(sessionId);
    showAgentEvidence(data);
    const records = Array.isArray(data.records) ? data.records : [];
    const contexts = Array.isArray(data.contexts) ? data.contexts : [];
    byId('meta').textContent = 'Intent: ' + (data.intent || 'unknown') + '\n' +
      'Execution: ' + (data.mode || 'unknown') + '\n' +
      'Data period: ' + (data.as_of || 'unspecified') + '\n' +
      'SQL records: ' + records.length + '\n' +
      'Retrieved docs: ' + contexts.length + '\n' +
      'Active agent: ' + (data.active_agent || 'unknown') + '\n' +
      'LLM router fallback: ' + (data.route_fallback === true ? 'yes' : 'no');
    byId('raw').textContent = JSON.stringify({records, contexts: contexts.map(x => x.source)}, null, 2);
    byId('response-state').innerHTML = '<span class="status-dot" aria-hidden="true"></span> COMPLETE';
  } catch (error) {
    answer.classList.add('is-error');
    answer.textContent = 'Unable to retrieve an answer. ' + error.message;
    byId('response-state').textContent = 'ERROR';
  } finally {
    askInProgress = false;
    button.disabled = false;
  }
}

function displayNumber(n, digits = 0) {
  return Number(n).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
}
function displayPayback(n) { return n === null ? 'No payback' : displayNumber(n, 2) + ' months'; }

async function estimateROI() {
  const form = byId('roi-form');
  if (!form.reportValidity()) return;
  const button = byId('roi-run');
  const status = byId('roi-status');
  const body = {};
  for (const [key, value] of new FormData(form)) {
    body[key === 'assisted_share_percent' ? 'assisted_share' : key] =
      key === 'assisted_share_percent' ? Number(value) / 100 : Number(value);
  }
  button.disabled = true;
  status.textContent = 'Recalculating scenario…';
  try {
    const response = await fetch('/api/roi/estimate', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error('Please check the entered numbers (' + response.status + ').');
    const b = data.business;
    const c = data.agent_cost_estimate;
    byId('roi-gross').textContent = displayNumber(b.gross_monthly_benefit_vnd) + ' VND';
    byId('roi-net').textContent = displayNumber(b.monthly_net_benefit_vnd) + ' VND';
    byId('roi-net').className = 'roi-value ' + (b.monthly_net_benefit_vnd < 0 ? 'roi-negative' : 'roi-positive');
    byId('roi-payback').textContent = displayPayback(b.payback_months);
    byId('roi-hours').textContent = displayNumber(b.hours_saved_per_month, 1) + ' h';
    byId('roi-token-cost').textContent = '$' + displayNumber(c.monthly_token_cost_usd, 3);
    byId('roi-per-request').textContent = c.cost_per_request_usd === null ? 'N/A' : '$' + displayNumber(c.cost_per_request_usd, 5);
    byId('roi-cost-breakdown').textContent = 'Estimated input $' + displayNumber(c.llm_input_cost_usd, 3) +
      ' + output $' + displayNumber(c.llm_output_cost_usd, 3) +
      ' + embedding $' + displayNumber(c.embedding_cost_usd, 3) +
      '. Token costs are part of the all-in VND budget, not an extra deduction.';
    const container = byId('roi-sensitivity');
    container.replaceChildren();
    const paybacks = data.sensitivity.map(s => s.payback_months).filter(n => n !== null && Number.isFinite(n));
    const maxPayback = Math.max(12, ...paybacks);
    for (const scenario of data.sensitivity) {
      const row = document.createElement('div'); row.className = 'roi-chartrow';
      const name = document.createElement('span'); name.textContent = displayNumber(scenario.assisted_share * 100) + '% helped';
      const track = document.createElement('div'); track.className = 'roi-track';
      const bar = document.createElement('div'); bar.className = 'roi-fill';
      bar.style.width = scenario.payback_months === null ? '0%' : Math.min(100, scenario.payback_months / maxPayback * 100) + '%';
      const detail = document.createElement('span');
      detail.textContent = scenario.payback_months === null ? 'No payback' : displayNumber(scenario.payback_months, 1) + ' mo';
      track.appendChild(bar); row.append(name, track, detail); container.appendChild(row);
    }
    status.textContent = 'Illustrative scenario recalculated locally. No LLM call was made.';
  } catch (error) {
    status.textContent = 'Unable to calculate: ' + error.message;
  } finally { button.disabled = false; }
}

function initRetailIQ() {
  byId('tab-assistant').addEventListener('click', () => showPanel('assistant'));
  byId('tab-roi').addEventListener('click', () => showPanel('roi'));
  byId('ask-form').addEventListener('submit', (event) => { event.preventDefault(); ask(); });
  byId('roi-form').addEventListener('submit', (event) => { event.preventDefault(); estimateROI(); });
  document.querySelectorAll('[data-question]').forEach(btn => btn.addEventListener('click', () => sample(btn.dataset.question)));
  // Accessible left/right navigation inside the tab list.
  document.querySelector('.workspace-tabs').addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const destination = byId(event.target.id === 'tab-roi' ? 'tab-assistant' : 'tab-roi');
    destination.focus(); destination.click(); event.preventDefault();
  });
  byId('chat-new').addEventListener('click', () => createNewChat().catch(e => alert(e.message)));
  byId('chat-delete').addEventListener('click', () => deleteCurrentChat().catch(e => alert(e.message)));
  byId('chat-session-picker').addEventListener('change', e => selectSession(e.target.value).catch(err => alert(err.message)));
  initializeSessions();
  byId('answer').classList.add('is-placeholder');
}
window.addEventListener('DOMContentLoaded', initRetailIQ);
