/* RetailIQ Week 1 — framework-free local UI; no credentials or provider keys in browser. */
'use strict';

const byId = (id) => document.getElementById(id);
let roiLoaded = false;
let askInProgress = false;
let activeSessionId = '';
let lastRequestId = '';
let currentRows = [];

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
  byId('answer').textContent = last ? last.content : 'Run a query to view the result.';
  byId('meta').textContent = last ? 'Last agent: ' + (session.active_agent || 'unknown') : 'No execution yet.';
  byId('agent-trace').replaceChildren();
  renderRecords();
  byId('summary-agent').textContent = session.active_agent || '—';
  byId('summary-period').textContent = '—';
  byId('summary-mode').textContent = last ? 'Stored answer' : '—';
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

// Render actual SQL records and Product RAG sources, not an opaque JSON blob.
function formatCell(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return value.toLocaleString('en-US', {maximumFractionDigits: 4});
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
function renderRecords(result = {}) {
  const records = Array.isArray(result.records) ? result.records.filter(row => row && typeof row === 'object' && !Array.isArray(row)) : [];
  const contexts = Array.isArray(result.contexts) ? result.contexts : [];
  currentRows = records;
  byId('data-count').textContent = records.length + (records.length === 1 ? ' row' : ' rows');
  byId('export-csv').disabled = records.length === 0;
  const table = byId('records-table');
  const wrapper = byId('records-table-wrap');
  table.replaceChildren();
  wrapper.hidden = records.length === 0;
  const empty = byId('records-empty');
  empty.hidden = records.length > 0;
  empty.textContent = !('records' in result || 'contexts' in result) ? 'Run a query to populate this table.' :
    contexts.length ? 'Product evidence is listed below; no SQL records for this query.' : 'No structured records for this query.';
  if (records.length) {
    const cols = [...new Set(records.flatMap(row => Object.keys(row)))].slice(0, 18);
    const thead = document.createElement('thead'), header = document.createElement('tr');
    for (const col of cols) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = col.replaceAll('_', ' ');
      if (records.some(row => typeof row[col] === 'number')) th.className = 'number-col';
      header.appendChild(th);
    }
    thead.appendChild(header);
    const body = document.createElement('tbody');
    for (const record of records.slice(0, 200)) {
      const tr = document.createElement('tr');
      for (const col of cols) {
        const td = document.createElement('td');
        td.textContent = formatCell(record[col]);
        if (typeof record[col] === 'number') td.className = 'cell-number';
        tr.appendChild(td);
      }
      body.appendChild(tr);
    }
    table.append(thead, body);
    if (records.length > 200) byId('data-count').textContent += ' · first 200 shown';
  }
  const sources = [...new Set(contexts.map(c => c && c.source).filter(Boolean).map(String))];
  byId('sources-section').hidden = sources.length === 0;
  const sourceList = byId('source-list');
  sourceList.replaceChildren();
  for (const source of sources) {
    const li = document.createElement('li');
    li.textContent = source;
    sourceList.appendChild(li);
  }
}
function exportRecordsCsv() {
  if (!currentRows.length) return;
  const columns = [...new Set(currentRows.flatMap(row => Object.keys(row)))];
  const escapeCsv = value => {
    let text = value === null || value === undefined ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
    // User/document strings must not become spreadsheet formulas.
    if (typeof value === 'string' && /^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const csv = [columns.map(escapeCsv).join(','), ...currentRows.map(row => columns.map(c => escapeCsv(row[c])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'retailiq-query-results.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
  const logs = name === 'logs';
  byId('assistant-panel').hidden = name !== 'assistant';
  byId('roi-panel').hidden = !roi;
  byId('logs-panel').hidden = !logs;
  for (const key of ['assistant', 'roi', 'logs']) {
    byId('tab-' + key).setAttribute('aria-selected', String(key === name));
  }
  if (roi && !roiLoaded) { roiLoaded = true; estimateROI(); }
  if (logs) loadExecutionLogs();
}

function sample(question) {
  byId('q').value = question;
  showPanel('assistant');
  ask();
}

// Render only allowlisted event metadata. Never HTML-inject agent/model output.
function resetLiveTrace() {
  byId('live-trace-list').replaceChildren();
  byId('live-trace-count').textContent = '0 events';
  byId('live-trace-request').textContent = '—';
  byId('live-trace-state').textContent = 'CONNECTING';
  byId('live-indicator').className = 'live-indicator live-indicator-running';
  byId('live-trace-panel').classList.add('trace-is-live');
}

function setLiveTraceState(status) {
  byId('live-trace-state').textContent = status;
  byId('live-indicator').className = 'live-indicator' +
    (status === 'RUNNING' || status === 'CONNECTING' ? ' live-indicator-running' :
    status === 'ERROR' ? ' live-indicator-error' : ' live-indicator-complete');
  byId('live-trace-panel').classList.toggle('trace-is-live', status === 'RUNNING' || status === 'CONNECTING');
}

function appendLiveEvent(event) {
  const list = byId('live-trace-list');
  if (list.children.length >= 70) list.firstElementChild.remove();
  const entry = document.createElement('li');
  const level = String(event.level || 'INFO').toLowerCase();
  entry.className = 'live-trace-event level-' + (['info', 'warning', 'error'].includes(level) ? level : 'info');
  const details = [];
  for (const key of ['agent', 'previous_agent', 'target_agent', 'subagent', 'tool', 'intent', 'skill', 'execution_mode', 'error_type']) {
    if (event[key] !== null && event[key] !== undefined) {
      details.push(String(event[key]).replaceAll('_', ' '));
    }
  }
  const dot = document.createElement('span'); dot.className = 'trace-node'; dot.setAttribute('aria-hidden', 'true');
  const content = document.createElement('div'); content.className = 'trace-node-content';
  const title = document.createElement('strong'); title.textContent = String(event.event || 'execution event').replaceAll('.', ' / ').replaceAll('_', ' ');
  const sub = document.createElement('span'); sub.className = 'trace-node-meta';
  sub.textContent = details.join(' · ') || String(event.status || 'Agent execution');
  const time = document.createElement('span'); time.className = 'trace-node-duration';
  time.textContent = typeof event.duration_ms === 'number' ? event.duration_ms.toFixed(0) + ' ms'
    : (event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '');
  content.append(title, sub); entry.append(dot, content, time); list.appendChild(entry);
  byId('live-trace-count').textContent = String(Number(byId('live-trace-count').textContent.split(' ')[0]) + 1) + ' events';
  list.scrollTop = list.scrollHeight;
}

// fetch(POST) streaming: EventSource cannot send the chat body/session id.
async function consumeChatSSE(response, onEvent) {
  if (!response.body || !response.body.getReader) throw new Error('This browser does not support streaming responses.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  function parseFrame(frame) {
    const lines = frame.split('\n');
    const type = (lines.find(line => line.startsWith('event:')) || 'event: message').slice(6).trim();
    const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (data) onEvent(type, JSON.parse(data));
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream:true}).replaceAll('\r\n', '\n');
      let index;
      while ((index = buffer.indexOf('\n\n')) !== -1) {
        parseFrame(buffer.slice(0, index));
        buffer = buffer.slice(index + 2);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) parseFrame(buffer);
  } finally { reader.releaseLock(); }
}

async function ask() {
  if (askInProgress) return;
  const question = byId('q').value.trim();
  if (question.length < 3) { byId('q').reportValidity(); return; }
  askInProgress = true;
  const button = byId('ask-submit');
  const answer = byId('answer');
  const sessionPicker = byId('chat-session-picker');
  button.disabled = true;
  for (const element of [byId('chat-new'), byId('chat-delete'), sessionPicker]) element.disabled = true;
  answer.classList.remove('is-placeholder', 'is-error');
  answer.textContent = 'Waiting for agent result — follow the live execution on the right…';
  byId('response-state').textContent = 'WORKING';
  resetLiveTrace();
  renderRecords();
  byId('summary-mode').textContent = 'Running';
  let result = null;
  let streamError = '';
  let streamDone = false;
  try {
    const sessionId = await ensureSession();
    const response = await fetch('/ask/stream', {
      method: 'POST', headers: {'Content-Type':'application/json', 'Accept':'text/event-stream'},
      body: JSON.stringify({question, session_id: sessionId})
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : 'Request failed (' + response.status + ')');
    }
    await consumeChatSSE(response, (type, data) => {
      if (type === 'started') {
        lastRequestId = data.request_id || response.headers.get('X-Request-ID') || '';
        byId('live-trace-request').textContent = lastRequestId ? lastRequestId.slice(0, 10) + '…' : '—';
        setLiveTraceState('RUNNING');
      } else if (type === 'log') {
        appendLiveEvent(data);
      } else if (type === 'result') {
        result = data;
      } else if (type === 'error') {
        streamError = data.message || 'Agent execution failed.';
      } else if (type === 'done') {
        streamDone = true;
      }
    });
    if (streamError) throw new Error(streamError);
    if (!streamDone || !result) throw new Error('The connection ended before an agent result was received.');
    lastRequestId = result.request_id || lastRequestId;
    answer.textContent = result.answer || 'No answer available for this question.';
    await refreshSessions();
    await selectSession(sessionId);
    showAgentEvidence(result);
    const records = Array.isArray(result.records) ? result.records : [];
    const contexts = Array.isArray(result.contexts) ? result.contexts : [];
    byId('meta').textContent = 'Intent: ' + (result.intent || 'unknown') + '\n' +
      'Execution: ' + (result.mode || 'unknown') + '\n' +
      'Data period: ' + (result.as_of || 'unspecified') + '\n' +
      'SQL records: ' + records.length + '\n' +
      'Retrieved docs: ' + contexts.length + '\n' +
      'Active agent: ' + (result.active_agent || 'unknown') + '\n' +
      'LLM router fallback: ' + (result.route_fallback === true ? 'yes' : 'no');
    byId('raw').textContent = JSON.stringify({records, contexts: contexts.map(x => x.source)}, null, 2);
    renderRecords(result);
    byId('summary-agent').textContent = (result.active_agent || '—').replaceAll('_', ' ');
    byId('summary-period').textContent = result.as_of || '—';
    byId('summary-mode').textContent = result.mode && result.mode.toLowerCase().includes('offline') ? 'Offline demo' : 'Full agent';
    byId('response-state').innerHTML = '<span class="status-dot" aria-hidden="true"></span> COMPLETE';
    setLiveTraceState('COMPLETE');
  } catch (error) {
    answer.classList.add('is-error');
    answer.textContent = 'Unable to retrieve an answer. ' + error.message;
    byId('response-state').textContent = 'ERROR';
    setLiveTraceState('ERROR');
    byId('summary-mode').textContent = 'Error';
  } finally {
    askInProgress = false;
    button.disabled = false;
    for (const element of [byId('chat-new'), byId('chat-delete'), sessionPicker]) element.disabled = false;
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

async function loadExecutionLogs() {
  const button = byId('logs-refresh');
  const status = byId('logs-status');
  const scope = byId('log-scope').value;
  const params = new URLSearchParams({limit: '100'});
  const level = byId('log-level').value;
  if (level) params.set('level', level);
  if (scope === 'current' && activeSessionId) params.set('session_id', activeSessionId);
  if (scope === 'request' && lastRequestId) params.set('request_id', lastRequestId);
  button.disabled = true;
  status.textContent = 'Reading structured runtime events…';
  try {
    // Avoid accidentally showing global logs when no current session/request exists.
    if ((scope === 'current' && !activeSessionId) || (scope === 'request' && !lastRequestId)) {
      renderExecutionLogs([]);
      status.textContent = scope === 'request' ? 'Ask a question first to get a request ID.' : 'Create a chat session first.';
      return;
    }
    const response = await fetch('/api/logs?' + params.toString(), {cache: 'no-store'});
    if (!response.ok) throw new Error('Logs unavailable (' + response.status + ')');
    const data = await response.json();
    renderExecutionLogs(data.events || []);
    status.textContent = 'Local events only · No prompts, secrets or raw exception stacks exposed.';
  } catch (error) {
    status.textContent = error.message;
    renderExecutionLogs([]);
  } finally { button.disabled = false; }
}

function renderExecutionLogs(events) {
  const list = byId('logs-list');
  list.replaceChildren();
  byId('log-count').textContent = String(events.length);
  byId('log-request-id').textContent = lastRequestId ? lastRequestId.slice(0, 12) + '…' : '—';
  if (!events.length) {
    const empty = document.createElement('div');
    empty.className = 'log-empty';
    empty.textContent = 'No matching events. Try a retail question, then refresh.';
    list.appendChild(empty);
    return;
  }
  for (const event of events) {
    const row = document.createElement('div'); row.className = 'log-entry';
    const top = document.createElement('div'); top.className = 'log-entry-top';
    const severity = document.createElement('span');
    severity.className = 'log-severity level-' + String(event.level || 'INFO').toLowerCase();
    severity.textContent = event.level || 'INFO';
    const stamp = document.createElement('time');
    stamp.textContent = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '—';
    const name = document.createElement('strong'); name.textContent = event.event || 'unknown';
    top.append(severity, name, stamp);
    const meta = document.createElement('div'); meta.className = 'log-entry-meta';
    const parts = [];
    for (const key of ['agent', 'tool', 'subagent', 'skill', 'intent', 'target_agent', 'duration_ms', 'status', 'status_code', 'error_type', 'execution_mode', 'input_tokens', 'output_tokens']) {
      if (event[key] !== undefined && event[key] !== null) {
        parts.push(key.replaceAll('_', ' ') + ': ' + String(event[key]) + (key === 'duration_ms' ? ' ms' : ''));
      }
    }
    meta.textContent = parts.join(' · ') || 'Request event';
    row.append(top, meta);
    list.appendChild(row);
  }
}

function initRetailIQ() {
  byId('tab-assistant').addEventListener('click', () => showPanel('assistant'));
  byId('tab-roi').addEventListener('click', () => showPanel('roi'));
  byId('tab-logs').addEventListener('click', () => showPanel('logs'));
  byId('logs-refresh').addEventListener('click', loadExecutionLogs);
  byId('export-csv').addEventListener('click', exportRecordsCsv);
  byId('log-scope').addEventListener('change', loadExecutionLogs);
  byId('log-level').addEventListener('change', loadExecutionLogs);
  byId('ask-form').addEventListener('submit', (event) => { event.preventDefault(); ask(); });
  byId('roi-form').addEventListener('submit', (event) => { event.preventDefault(); estimateROI(); });
  document.querySelectorAll('[data-question]').forEach(btn => btn.addEventListener('click', () => sample(btn.dataset.question)));
  // Accessible left/right navigation inside the tab list.
  document.querySelector('.workspace-tabs').addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const tabs = ['tab-assistant', 'tab-roi', 'tab-logs'];
    const index = tabs.indexOf(event.target.id);
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const destination = byId(tabs[(index + direction + tabs.length) % tabs.length]);
    destination.focus(); destination.click(); event.preventDefault();
  });
  byId('chat-new').addEventListener('click', () => createNewChat().catch(e => alert(e.message)));
  byId('chat-delete').addEventListener('click', () => deleteCurrentChat().catch(e => alert(e.message)));
  byId('chat-session-picker').addEventListener('change', e => selectSession(e.target.value).catch(err => alert(err.message)));
  initializeSessions();
  byId('answer').classList.add('is-placeholder');
}
window.addEventListener('DOMContentLoaded', initRetailIQ);
