/* RetailIQ Week 1 — framework-free local UI; no credentials or provider keys in browser. */
'use strict';

const byId = (id) => document.getElementById(id);
let roiLoaded = false;
let askInProgress = false;
let activeSessionId = '';
let lastRequestId = '';
let currentRows = [];
let currentAnswerIsPersisted = false;
const AgentID = () => window.RetailIQIdentity;
const Rich = () => window.RetailIQFormat;

function renderAssistantText(target, value) {
  Rich().renderMarkdown(target, value);
}
function setActiveAgent(agent, intent = '') {
  const type = AgentID().type(agent, intent);
  const message = byId('active-response');
  AgentID().apply(message, 'iq');
  const avatar = byId('active-agent-avatar');
  avatar.replaceChildren(AgentID().icon('iq'));
  avatar.className = 'agent-avatar agent-avatar-iq';
  message.querySelector('.chat-message-label').textContent = 'RetailIQ';
  const badge = byId('evidence-agent');
  AgentID().apply(badge, type);
  badge.textContent = AgentID().TYPES[type].short;
  return type;
}

async function ensureSession() {
  if (activeSessionId) return activeSessionId;
  const response = await fetch('/api/sessions', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({})
  });
  if (!response.ok) throw new Error('Cannot create chat session');
  const session = await response.json();
  activeSessionId = session.id;
  localStorage.setItem('retailiq-active-session', activeSessionId);
  await refreshSessions();
  return activeSessionId;
}

async function refreshSessions() {
  const response = await fetch('/api/sessions');
  if (!response.ok) throw new Error('Unable to read chat sessions');
  const data = await response.json();
  const sessions = data.sessions || [];
  const picker = byId('chat-session-picker');
  picker.replaceChildren();
  if (!activeSessionId) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'New conversation';
    picker.appendChild(option);
  }
  for (const s of sessions) {
    const option = document.createElement('option');
    option.value = s.id;
    option.textContent = s.title;
    picker.appendChild(option);
  }
  // Never show one selected conversation while API calls target another.
  // A previously selected chat may fall outside the bounded session listing.
  if (activeSessionId && !sessions.some(s => s.id === activeSessionId)) {
    const option = document.createElement('option');
    option.value = activeSessionId;
    option.textContent = 'Current conversation';
    picker.appendChild(option);
  }
  picker.value = activeSessionId || '';
  return sessions;
}

function appendChatMessage(role, content, agent = '') {
  const area = byId('chat-history');
  const item = document.createElement('div');
  item.className = 'chat-message chat-message-' + (role === 'user' ? 'user' : 'assistant');
  const label = document.createElement('span');
  label.className = 'chat-message-label';
  const agentType = role === 'user' ? 'user' : 'iq';
  AgentID().apply(item, agentType);
  label.textContent = role === 'user' ? 'You' : AgentID().TYPES[agentType].name;
  const body = document.createElement('span');
  body.className = 'chat-message-content';
  if (role === 'user') body.textContent = String(content);
  else renderAssistantText(body, content);
  body.classList.toggle('rich-markdown', role !== 'user');
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.append(label, body);
  if (role === 'user') {
    const avatar = document.createElement('span');
    avatar.className = 'chat-avatar chat-avatar-user';
    avatar.textContent = 'U';
    avatar.setAttribute('aria-hidden', 'true');
    item.append(bubble, avatar);
  } else {
    item.append(AgentID().avatar(agentType), bubble);
  }
  area.appendChild(item);
  return item;
}
function scrollChatToBottom() {
  const thread = byId('chat-thread');
  thread.scrollTop = thread.scrollHeight;
}
function renderChatMessages(messages) {
  const area = byId('chat-history');
  area.replaceChildren();
  // Latest assistant message is rendered exactly once in #answer, after history.
  const final = messages.length && messages[messages.length - 1].role === 'assistant' ? messages.length - 1 : -1;
  for (let i = 0; i < messages.length; i++) {
    if (i === final) continue;
    const message = messages[i];
    appendChatMessage(message.role, message.content, message.agent);
  }
  scrollChatToBottom();
}

async function selectSession(id, preserveEvidence = false) {
  const response = await fetch('/api/sessions/' + encodeURIComponent(id));
  if (!response.ok) throw new Error('Session no longer exists');
  const session = await response.json();
  activeSessionId = id;
  localStorage.setItem('retailiq-active-session', id);
  byId('chat-session-picker').value = id;
  const messages = session.messages || [];
  byId('chat-history-limit').hidden = session.messages_truncated !== true;
  renderChatMessages(messages);
  byId('chat-welcome').hidden = messages.length > 0;
  setChatError();
  const last = messages.length && messages[messages.length - 1].role === 'assistant' ? messages[messages.length - 1] : null;
  const storedEvidence = last && last.evidence ? last.evidence : {};
  currentAnswerIsPersisted = Boolean(last);
  byId('active-response').hidden = !last;
  if (last) renderAssistantText(byId('answer'), last.content);
  else byId('answer').textContent = 'Ask a retail question, then continue with a follow-up.';
  Rich().renderEvidence(byId('response-visuals'), storedEvidence);
  renderRecords(storedEvidence);
  setActiveAgent(session.active_agent || 'iq');
  byId('answer').classList.remove('is-error');
  byId('meta').textContent = last ? 'Last agent: ' + (session.active_agent || 'unknown') : 'No execution yet.';
  if (!preserveEvidence) {
    byId('agent-trace').replaceChildren();
    byId('raw').textContent = JSON.stringify(storedEvidence, null, 2);
    byId('live-trace-list').replaceChildren();
    byId('live-trace-count').textContent = '0 events';
    byId('live-trace-request').textContent = '—';
    byId('live-trace-state').textContent = 'IDLE';
    byId('live-indicator').className = 'live-indicator';
    byId('live-trace-panel').classList.remove('trace-is-live');
    lastRequestId = '';
  }
  byId('summary-agent').textContent = session.active_agent || '—';
  byId('summary-period').textContent = storedEvidence.as_of || '—';
  byId('summary-mode').textContent = preserveEvidence ? byId('summary-mode').textContent : (last ? 'Stored answer' : '—');
  byId('response-state').textContent = last ? 'READY' : 'NEW CHAT';
  byId('answer').dataset.rawAnswer = last ? last.content : '';
  scrollChatToBottom();
}

function setChatError(message = '') {
  const error = byId('chat-error');
  error.textContent = message;
  error.hidden = !message;
}

function showEmptyChat() {
  // A new chat is a draft until the first successful turn. Creating an empty
  // SQLite session on every New/Delete click polluted the history list.
  activeSessionId = '';
  localStorage.removeItem('retailiq-active-session');
  const picker = byId('chat-session-picker');
  if ([...picker.options].some(option => option.value === '')) picker.value = '';
  else picker.selectedIndex = -1;
  byId('chat-history').replaceChildren();
  byId('chat-history-limit').hidden = true;
  byId('chat-welcome').hidden = false;
  byId('active-response').hidden = true;
  currentAnswerIsPersisted = false;
  const answer = byId('answer');
  answer.textContent = 'Ask a retail question, then continue with a follow-up.';
  answer.dataset.rawAnswer = '';
  answer.classList.remove('is-error');
  Rich().renderEvidence(byId('response-visuals'), {});
  renderRecords({});
  setActiveAgent('iq');
  byId('meta').textContent = 'No execution yet.';
  byId('agent-trace').replaceChildren();
  byId('raw').textContent = '{}';
  byId('live-trace-list').replaceChildren();
  byId('live-trace-count').textContent = '0 events';
  byId('live-trace-request').textContent = '—';
  setLiveTraceState('IDLE');
  byId('summary-agent').textContent = '—';
  byId('summary-period').textContent = '—';
  byId('summary-mode').textContent = '—';
  byId('response-state').textContent = 'NEW CHAT';
  lastRequestId = '';
  setChatError();
}

async function createNewChat() {
  if (askInProgress) return;
  showEmptyChat();
  await refreshSessions();
  byId('q').value = '';
  byId('q').focus();
}

async function deleteCurrentChat() {
  if (askInProgress || !activeSessionId) return;
  if (!confirm('Delete this conversation and all messages?')) return;
  const sid = activeSessionId;
  const response = await fetch('/api/sessions/' + encodeURIComponent(sid), {method: 'DELETE'});
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const reason = typeof payload.detail === 'string' ? payload.detail : 'Request failed';
    throw new Error('Cannot delete conversation (' + response.status + '): ' + reason);
  }
  activeSessionId = '';
  localStorage.removeItem('retailiq-active-session');
  const remaining = await refreshSessions();
  if (remaining.length) await selectSession(remaining[0].id);
  else showEmptyChat(); // Do not silently replace a deleted chat with a new DB row.
  setChatError();
}

async function initializeSessions() {
  try {
    const sessions = await refreshSessions();
    const stored = localStorage.getItem('retailiq-active-session');
    const selected = sessions.find(s => s.id === stored);
    const id = selected ? selected.id : sessions.length ? sessions[0].id : '';
    if (id) await selectSession(id);
    else showEmptyChat();
  } catch (err) {
    showEmptyChat();
    setChatError('Unable to load conversations: ' + err.message);
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
    const known = AgentID().type(text);
    AgentID().apply(chip, known);
    chip.append(AgentID().icon(known), document.createTextNode(text));
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
  if (askInProgress) return;
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
  const identity = AgentID().type(event.subagent || event.agent || event.target_agent || event.previous_agent || '',event.intent);
  AgentID().apply(entry, identity);
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
  content.append(title, sub); entry.append(dot, AgentID().icon(identity), content, time); list.appendChild(entry);
  byId('live-trace-count').textContent = String(Number(byId('live-trace-count').textContent.split(' ')[0]) + 1) + ' events';
  list.scrollTop = list.scrollHeight;
}

// fetch(POST) streaming: EventSource cannot send the chat body/session id.
async function consumeChatSSE(response, onEvent) {
  if (!response.body || !response.body.getReader) throw new Error('This browser does not support streaming responses.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const MAX_STREAM_CHARS = 2_000_000;
  const MAX_FRAME_CHARS = 65_536;
  const MAX_EVENTS = 512;
  let buffer = '';
  let pendingCR = '';
  let received = 0;
  let events = 0;
  let completed = false;
  function normalized(chunk) {
    let text = pendingCR + chunk;
    pendingCR = '';
    if (text.endsWith('\r')) {
      pendingCR = '\r';
      text = text.slice(0, -1);
    }
    return text.replace(/\r\n?/g, '\n');
  }
  function parseFrame(frame) {
    if (frame.length > MAX_FRAME_CHARS) throw new Error('Agent event is too large.');
    const lines = frame.split('\n');
    const type = (lines.find(line => line.startsWith('event:')) || 'event: message').slice(6).trim();
    const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (data) {
      if (++events > MAX_EVENTS) throw new Error('Agent event limit exceeded.');
      onEvent(type, JSON.parse(data));
    }
  }
  function appendChunk(chunk) {
    received += chunk.length;
    if (received > MAX_STREAM_CHARS) throw new Error('Agent response stream limit exceeded.');
    buffer += normalized(chunk);
    let index;
    while ((index = buffer.indexOf('\n\n')) !== -1) {
      parseFrame(buffer.slice(0, index));
      buffer = buffer.slice(index + 2);
    }
    if (buffer.length > MAX_FRAME_CHARS) throw new Error('Agent event is too large.');
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) { completed = true; break; }
      appendChunk(decoder.decode(value, {stream:true}));
    }
    appendChunk(decoder.decode());
    if (pendingCR) { buffer += '\n'; pendingCR = ''; }
    if (buffer.trim()) parseFrame(buffer);
  } finally {
    // Cancel when malformed or oversized data interrupts the read; disconnect
    // is best-effort and does not claim to cancel synchronous provider calls.
    if (!completed) {
      try { await reader.cancel(); } catch (_) { /* reader already closed */ }
    }
    reader.releaseLock();
  }
}

async function ask() {
  if (askInProgress) return;
  const question = byId('q').value.trim();
  setChatError();
  if (question.length < 3) { byId('q').reportValidity(); return; }
  askInProgress = true;
  const button = byId('ask-submit');
  const answer = byId('answer');
  const sessionPicker = byId('chat-session-picker');
  if (currentAnswerIsPersisted) {
    appendChatMessage('assistant', answer.dataset.rawAnswer || answer.textContent, byId('summary-agent').textContent);
  }
  currentAnswerIsPersisted = false;
  byId('chat-welcome').hidden = true;
  byId('active-response').hidden = false;
  appendChatMessage('user', question);
  byId('q').value = '';
  scrollChatToBottom();
  button.disabled = true;
  document.querySelectorAll('[data-question]').forEach(item => {item.disabled = true;});
  for (const element of [byId('chat-new'), byId('chat-delete'), sessionPicker]) element.disabled = true;
  answer.classList.remove('is-placeholder', 'is-error');
  answer.textContent = 'Thinking…';
  Rich().renderEvidence(byId('response-visuals'), {});
  setActiveAgent('iq');
  byId('response-state').textContent = 'WORKING';
  resetLiveTrace();
  renderRecords();
  byId('summary-mode').textContent = 'Running';
  let result = null;
  let streamError = '';
  let streamDone = false;
  let sessionId = activeSessionId;
  setChatError();
  try {
    sessionId = await ensureSession();
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
    await refreshSessions();
    await selectSession(sessionId, true);
    answer.dataset.rawAnswer = result.answer || 'No answer available for this question.';
    renderAssistantText(answer, answer.dataset.rawAnswer);
    setActiveAgent(result.active_agent, result.intent);
    Rich().renderEvidence(byId('response-visuals'), result);
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
    byId('summary-mode').textContent = result.mode && result.mode.toLowerCase().includes('offline') ? 'Offline · rules' : 'AI workflow';
    const completedState = byId('response-state');
    const dot = document.createElement('span');
    dot.className = 'status-dot';
    dot.setAttribute('aria-hidden', 'true');
    completedState.replaceChildren(dot, document.createTextNode(' COMPLETE'));
    setLiveTraceState('COMPLETE');
    scrollChatToBottom();
    byId('q').focus();
  } catch (error) {
    // Remove optimistic messages and restore the authoritative saved history.
    // A stream may fail after the backend saved its turn, so re-read SQLite.
    try {
      if (sessionId) await selectSession(sessionId);
      else showEmptyChat();
    } catch (_) {
      showEmptyChat();
    }
    setChatError('Unable to complete the request: ' + error.message);
    if (!byId('q').value.trim()) byId('q').value = question;
    byId('response-state').textContent = 'ERROR';
    byId('summary-mode').textContent = 'Error';
    scrollChatToBottom();
  } finally {
    askInProgress = false;
    button.disabled = false;
    document.querySelectorAll('[data-question]').forEach(item => {item.disabled = false;});
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
    status.textContent = 'Illustrative scenario recalculated. No LLM call was made.';
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
    status.textContent = 'Application events only · No prompts, secrets or raw exception stacks exposed.';
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
  byId('chat-new').addEventListener('click', () => createNewChat().catch(e => setChatError(e.message)));
  byId('chat-delete').addEventListener('click', () => deleteCurrentChat().catch(e => setChatError(e.message)));
  byId('chat-session-picker').addEventListener('change', e => {
    if (!e.target.value) { showEmptyChat(); return; }
    selectSession(e.target.value).catch(err => setChatError(err.message));
  });
  initializeSessions();
  byId('answer').classList.add('is-placeholder');
}
window.addEventListener('DOMContentLoaded', initRetailIQ);
