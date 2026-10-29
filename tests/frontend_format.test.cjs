/* Node.js built-in test runner: browser-free validation of unsafe LLM content. */
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag, text = '') {
    this.tagName = tag;
    this._text = text;
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this.events = new Map();
  }
  get textContent() {return this._text + this.children.map(n=>n.textContent).join('');}
  set textContent(value) {this._text=String(value);this.children=[];}
  append(...nodes) {this.children.push(...nodes);}
  appendChild(node) {this.children.push(node);return node;}
  replaceChildren(...nodes) {this._text='';this.children=nodes;}
  setAttribute(key,value) {this.attributes[key]=String(value);}
  addEventListener(event,handler) {this.events.set(event,handler);}
}

function tree(node,tag) {
  return [...(node.tagName===tag?[node]:[]),...node.children.flatMap(child=>tree(child,tag))];
}
const document = {
  createElement: tag=>new Element(tag),
  createElementNS: (_ns,tag)=>new Element(tag),
  createTextNode: value=>new Element('#text',String(value)),
};
const context = vm.createContext({
  window: {}, document, navigator: {clipboard:{writeText:async()=>{}}},
  URL, console,
});
for(const name of ['agent-identity.js','response-format.js']) {
  const source=fs.readFileSync(path.join(__dirname,'../web/assets',name),'utf8');
  vm.runInContext(source,context,{filename:name});
}
const {RetailIQFormat:format,RetailIQIdentity:identity}=context.window;

test('Markdown is rendered as safe DOM nodes and rejects javascript links',()=>{
  const target=new Element('div');
  format.renderMarkdown(target,'### Sales\n**Strong** & *italic*\n[valid](https://example.org) [bad](javascript:alert(1))\n<img src=x onerror=alert(1)>');
  assert.equal(tree(target,'h5').length,1);
  assert.equal(tree(target,'strong').length,1);
  assert.equal(tree(target,'em').length,1);
  assert.equal(tree(target,'a').length,1);
  assert.equal(tree(target,'img').length,0);
  assert.match(target.textContent,/<img src=x onerror=alert\(1\)>/);
  assert.equal(tree(target,'a')[0].rel,'noopener noreferrer nofollow');
});
test('Markdown table, list and code fence use structured elements',()=>{
  const root=new Element('div');
  format.renderMarkdown(root,'- one\n- two\n\n| Product | Units |\n| --- | --- |\n| Laptop | 22 |\n\n```sql\nSELECT * FROM orders;\n```');
  assert.equal(tree(root,'ul').length,1);
  assert.equal(tree(root,'li').length,2);
  assert.equal(tree(root,'table').length,1);
  assert.equal(tree(root,'th').length,2);
  assert.equal(tree(root,'pre').length,1);
  assert.equal(tree(root,'button').length,1);
});
test('Inventory KPI and chart equal real available rows',()=>{
  const root=new Element('div');
  format.renderEvidence(root,{intent:'stock',records:[
    {location:'Store',available:13},{location:'Warehouse',available:17}
  ]});
  const values=tree(root,'strong').map(n=>n.textContent);
  assert.deepEqual(values,['30','2']);
  assert.equal(tree(root,'span').filter(x=>x.className==='rich-bar-fill').length,2);
});
test('Sales revenue sums SQL channel rows, never LLM prose',()=>{
  const root=new Element('div');
  format.renderEvidence(root,{intent:'revenue',answer:'Definitely 999999 VND',records:[
    {channel:'Web',net_revenue_vnd:1200},{channel:'Store',net_revenue_vnd:800}
  ]});
  assert.equal(tree(root,'strong')[0].textContent,'2,000');
  assert.ok(!root.textContent.includes('999999'));
});
test('No numeric rows means no KPI/chart; citations remain plain text',()=>{
  const root=new Element('div');
  format.renderEvidence(root,{intent:'product',records:[],contexts:[{source:'<script>alert(1)</script>'}]});
  assert.equal(tree(root,'strong').length,0);
  assert.equal(tree(root,'span').filter(x=>x.className==='rich-bar-fill').length,0);
  assert.equal(tree(root,'script').length,0);
  assert.match(root.textContent,/<script>alert\(1\)<\/script>/);
});
test('Every supported specialist maps to an allowlisted identity',()=>{
  assert.equal(identity.type('sales_agent'),'sales');
  assert.equal(identity.type('inventory_agent'),'inventory');
  assert.equal(identity.type('product_agent'),'product');
  assert.equal(identity.type('retail_supervisor'),'supervisor');
  assert.equal(identity.type('arbitrary-user-style'),'iq');
  const node=new Element('span');
  assert.equal(identity.apply(node,'<script>'),'iq');
  assert.equal(node.dataset.agent,'iq');
});

test('Link protocol, credentials and oversized URLs are rejected', () => {
  assert.equal(format.safeLink('javascript:alert(1)'), null);
  assert.equal(format.safeLink('data:text/html,evil'), null);
  assert.equal(format.safeLink('https://user:password@example.org/'), null);
  assert.equal(format.safeLink(' https://example.org/'), null);
  assert.equal(format.safeLink('https://example.org/' + 'x'.repeat(2049)), null);
  assert.equal(format.safeLink('https://example.org/a'), 'https://example.org/a');
});

test('SQL KPI fails closed on malformed, unsafe, overflowing or excessive records', () => {
  const invalid = [
    [{available: '10'}],
    [null],
    [{available: 1.5}],
    [{available: Number.MAX_SAFE_INTEGER}, {available: 1}],
    Array.from({length: 201}, () => ({available: 1})),
  ];
  for (const records of invalid) {
    const root = new Element('div');
    format.renderEvidence(root, {intent: 'stock', records});
    assert.equal(tree(root, 'strong').length, 0);
  }
  const negative = new Element('div');
  format.renderEvidence(negative, {intent: 'revenue', records: [
    {channel: 'Refunds', net_revenue_vnd: -100},
    {channel: 'Sales', net_revenue_vnd: 200},
  ]});
  assert.equal(tree(negative, 'strong')[0].textContent, '100');
  assert.equal(tree(negative, 'span').filter(el => el.className === 'rich-bar-fill').length, 0);
});

test('Citations are bounded and never converted to HTML nodes', () => {
  const root = new Element('div');
  format.renderEvidence(root, {intent: 'product', contexts: Array.from({length: 1000},
    (_, i) => ({source: i === 0 ? '<img src=x onerror=alert(1)>' : 'source-' + i}))});
  assert.equal(tree(root, 'img').length, 0);
  assert.ok(tree(root, 'span').filter(el => el.className === 'rich-citation').length <= 8);
});

function loadSseParser() {
  const scope = vm.createContext({
    window: {addEventListener() {}}, document: {}, TextDecoder, URL, console
  });
  const source = fs.readFileSync(path.join(__dirname, '../web/assets/app.js'), 'utf8');
  vm.runInContext(source, scope, {filename: 'app.js'});
  return vm.runInContext('consumeChatSSE', scope);
}
function fakeStream(parts) {
  let index = 0;
  let cancelled = false;
  let released = false;
  return {
    response: {body: {getReader: () => ({
      read: async () => index === parts.length ? {done: true} :
        {done: false, value: Buffer.from(parts[index++])},
      cancel: async () => { cancelled = true; },
      releaseLock: () => { released = true; }
    })}},
    cancelled: () => cancelled,
    released: () => released,
  };
}
test('SSE parser handles fragmented CRLF boundaries', async () => {
  const parser = loadSseParser();
  const parts = ['event: started\\r', '\\ndata: {"ok":true}\\r', '\\n\\r', '\\n'];
  const stream = fakeStream(parts.map(part => part.replaceAll('\\r', '\r').replaceAll('\\n', '\n')));
  const events = [];
  await parser(stream.response, (type, payload) => events.push({type, payload}));
  assert.equal(events.length, 1);
  assert.equal(events[0].type, 'started');
  assert.equal(events[0].payload.ok, true);
  assert.equal(stream.released(), true);
  assert.equal(stream.cancelled(), false);
});
test('SSE parser rejects oversized frames and cancels reader', async () => {
  const parser = loadSseParser();
  const stream = fakeStream(['event: log\\ndata: ' + 'x'.repeat(70_000)]);
  await assert.rejects(parser(stream.response, () => {}), /too large/);
  assert.equal(stream.cancelled(), true);
  assert.equal(stream.released(), true);
});
test('SSE parser rejects event floods', async () => {
  const parser = loadSseParser();
  const stream = fakeStream([Array.from({length: 513},
    () => 'event: log\\ndata: {}\\n\\n').join('').replaceAll('\\n', '\n')]);
  await assert.rejects(parser(stream.response, () => {}), /event limit/);
  assert.equal(stream.cancelled(), true);
});


// Browser-state regressions: deleted chats must not be recreated and failed
// optimistic turns must not survive a refresh from persisted conversation data.
function chatBrowserFixture(initialSessions = [], {failDelete = false, failAsk = false, streamReply = null} = {}) {
  class BrowserElement extends Element {
    constructor(tag) {
      super(tag);
      this.hidden = false;
      this.value = '';
      this.selectedIndex = 0;
      const classes = new Set();
      this.classList = {
        add: (...names) => names.forEach(name => classes.add(name)),
        remove: (...names) => names.forEach(name => classes.delete(name)),
        toggle: (name, enabled) => {
          if (enabled) classes.add(name);
          else classes.delete(name);
        }
      };
    }
    get options() { return this.children; }
    querySelector() { return new BrowserElement('span'); }
    focus() {}
    reportValidity() { return false; }
  }
  const elements = new Map();
  const node = id => {
    if (!elements.has(id)) elements.set(id, new BrowserElement('div'));
    return elements.get(id);
  };
  const doc = {
    getElementById: node,
    createElement: tag => new BrowserElement(tag),
    createElementNS: (_ns, tag) => new BrowserElement(tag),
    createTextNode: text => new Element('#text', String(text)),
    querySelectorAll: () => [],
  };
  const storage = new Map();
  const sessions = [...initialSessions];
  const calls = [];
  const respond = (status, data = {}) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  });
  async function fetchMock(url, options = {}) {
    const method = options.method || 'GET';
    calls.push([method, url]);
    if (url === '/api/sessions' && method === 'GET') {
      return respond(200, {sessions: sessions.map(s => ({
        id: s.id, title: s.title || 'Conversation', message_count: s.messages?.length || 0
      }))});
    }
    if (url === '/api/sessions' && method === 'POST') {
      const id = 'created-' + String(sessions.length + 1);
      const session = {id, title: 'New conversation', messages: []};
      sessions.unshift(session);
      return respond(201, session);
    }
    const prefix = '/api/sessions/';
    if (url.startsWith(prefix)) {
      const id = decodeURIComponent(url.slice(prefix.length));
      const index = sessions.findIndex(s => s.id === id);
      if (index === -1) return respond(404, {detail: 'Session not found'});
      if (method === 'DELETE') {
        if (failDelete) return respond(503, {detail: 'Checkpoint cleanup failed'});
        sessions.splice(index, 1);
        return respond(204);
      }
      return respond(200, {...sessions[index], active_agent: 'sales_agent', messages_truncated: false});
    }
    if (url === '/ask/stream' && failAsk) return respond(503, {detail: 'Provider unavailable'});
    if (url === '/ask/stream' && streamReply) {
      const request = JSON.parse(options.body);
      const session = sessions.find(s => s.id === request.session_id);
      session.messages.push(
        {role: 'user', content: request.question},
        {role: 'assistant', content: streamReply.answer, agent: streamReply.active_agent,
         evidence: {intent: streamReply.intent, records: streamReply.records,
                    contexts: streamReply.contexts, as_of: streamReply.as_of}}
      );
      const events = [
        ['started', {request_id: 'request-1'}],
        ['result', {...streamReply, request_id: 'request-1', session_id: request.session_id}],
        ['done', {request_id: 'request-1'}]
      ];
      const bytes = Buffer.from(events.map(([type, payload]) =>
        'event: ' + type + '\\n' + 'data: ' + JSON.stringify(payload) + '\\n\\n').join('').replaceAll('\\n', '\n'));
      let read = false;
      return {ok: true, status: 200, headers: {get: () => null},
        body: {getReader: () => ({
          read: async () => read ? {done: true} : (read = true, {done: false, value: bytes}),
          cancel: async () => {}, releaseLock: () => {}
        })}};
    }
    throw new Error('Unexpected request: ' + method + ' ' + url);
  }
  const scope = vm.createContext({
    window: {addEventListener() {}, RetailIQIdentity: identity, RetailIQFormat: format},
    document: doc, localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    fetch: fetchMock, confirm: () => true, console, URL, TextDecoder,
  });
  const app = fs.readFileSync(path.join(__dirname, '../web/assets/app.js'), 'utf8');
  vm.runInContext(app, scope, {filename: 'app.js'});
  const run = expression => vm.runInContext(expression, scope);
  return {run, node, calls, sessions, storage};
}

test('New chat is a draft and deleting the last chat leaves no replacement session', async () => {
  const fixture = chatBrowserFixture([{id: 's1', title: 'Sales', messages: [
    {role: 'user', content: 'Revenue?'},
    {role: 'assistant', content: '100', evidence: {records: [], contexts: []}},
  ]}]);
  await fixture.run('initializeSessions()');
  assert.equal(fixture.run('activeSessionId'), 's1');
  await fixture.run('deleteCurrentChat()');
  assert.equal(fixture.sessions.length, 0);
  assert.equal(fixture.run('activeSessionId'), '');
  assert.equal(fixture.node('chat-error').hidden, true);
  assert.equal(fixture.node('chat-history').children.length, 0);
  assert.equal(fixture.node('chat-welcome').hidden, false);
  assert.equal(fixture.calls.filter(([method]) => method === 'POST').length, 0);
  await fixture.run('createNewChat()');
  assert.equal(fixture.calls.filter(([method]) => method === 'POST').length, 0);
});

test('Checkpoint deletion errors are visible and preserve the selected chat', async () => {
  const fixture = chatBrowserFixture([{id: 's2', messages: []}], {failDelete: true});
  await fixture.run('initializeSessions()');
  await assert.rejects(fixture.run('deleteCurrentChat()'), /503.*Checkpoint cleanup failed/);
  assert.equal(fixture.sessions.length, 1);
  assert.equal(fixture.run('activeSessionId'), 's2');
});

test('Failed request restores saved history instead of keeping optimistic messages', async () => {
  const fixture = chatBrowserFixture([{id: 's3', messages: [
    {role: 'user', content: 'What is revenue?'},
    {role: 'assistant', content: '100 VND', evidence: {records: [], contexts: []}},
  ]}], {failAsk: true});
  await fixture.run('initializeSessions()');
  fixture.node('q').value = 'And last month?';
  await fixture.run('ask()');
  assert.equal(fixture.node('chat-history').children.length, 1);
  assert.equal(fixture.node('chat-history').textContent.includes('And last month?'), false);
  assert.equal(fixture.node('q').value, 'And last month?');
  assert.match(fixture.node('chat-error').textContent, /Provider unavailable/);
  assert.equal(fixture.node('chat-error').hidden, false);
});


test('Persisted assistant turns retain KPI cards and charts when reopening history', async () => {
  const revenueEvidence = {intent: 'revenue', records: [
    {channel: 'Web', net_revenue_vnd: 1200},
    {channel: 'Store', net_revenue_vnd: 800}
  ], contexts: []};
  const fixture = chatBrowserFixture([{id: 'sales-chat', messages: [
    {role: 'user', content: 'Revenue?'},
    {role: 'assistant', content: '**Revenue:** 2,000 VND', agent: 'sales_agent',
     evidence: revenueEvidence},
    {role: 'user', content: 'Tell me about the charger'},
    {role: 'assistant', content: 'See [S1]', agent: 'product_agent',
     evidence: {intent: 'product', records: [], contexts: [{source: 'catalog/charger.md'}]}}
  ]}]);
  await fixture.run('initializeSessions()');
  const history = fixture.node('chat-history');
  assert.equal(history.children.length, 3); // Latest assistant is rendered separately.
  assert.equal(tree(history, 'strong').some(n => n.textContent === '2,000'), true);
  assert.equal(tree(history, 'span').some(n => n.className === 'rich-bar-fill'), true);
  assert.equal(tree(fixture.node('response-visuals'), 'span')
    .some(n => n.className === 'rich-citation' && n.textContent === 'catalog/charger.md'), true);
  await fixture.run('createNewChat()');
  await fixture.run("selectSession('sales-chat')");
  assert.equal(tree(fixture.node('chat-history'), 'strong')
    .some(n => n.textContent === '2,000'), true);
  assert.equal(tree(fixture.node('chat-history'), 'span')
    .some(n => n.className === 'rich-bar-fill'), true);
});

test('New streamed answer preserves the preceding answer formatting and sources', async () => {
  const previousEvidence = {intent: 'product', records: [],
    contexts: [{source: 'catalog/previous.md'}]};
  const fixture = chatBrowserFixture([{id: 'followup-chat', messages: [
    {role: 'user', content: 'Tell me about the product'},
    {role: 'assistant', content: '**Product facts** [S1]', agent: 'product_agent',
     evidence: previousEvidence}
  ]}], {streamReply: {
    intent: 'stock', answer: '**Stock:** 30 units', active_agent: 'inventory_agent',
    as_of: '2026-10', mode: 'LangGraph Multi-Agent',
    records: [{location: 'Store', available: 13}, {location: 'Warehouse', available: 17}],
    contexts: []
  }});
  await fixture.run('initializeSessions()');
  fixture.node('q').value = 'How much stock?';
  await fixture.run('ask()');
  const history = fixture.node('chat-history');
  assert.equal(history.children.length, 3);
  assert.equal(tree(history, 'span').some(n =>
    n.className === 'rich-citation' && n.textContent === 'catalog/previous.md'), true);
  assert.equal(tree(fixture.node('response-visuals'), 'strong')
    .some(n => n.textContent === '30'), true);
  await fixture.run("selectSession('followup-chat')");
  assert.equal(tree(fixture.node('chat-history'), 'span')
    .some(n => n.className === 'rich-citation' && n.textContent === 'catalog/previous.md'), true);
  assert.equal(tree(fixture.node('response-visuals'), 'strong')
    .some(n => n.textContent === '30'), true);
});

test('Old assistant messages without evidence remain valid Markdown-only history', async () => {
  const fixture = chatBrowserFixture([{id: 'legacy', messages: [
    {role: 'user', content: 'Hi'},
    {role: 'assistant', content: '**Hello**', evidence: null},
    {role: 'user', content: 'Next'},
    {role: 'assistant', content: 'New', evidence: null}
  ]}]);
  await fixture.run('initializeSessions()');
  assert.equal(fixture.node('chat-history').children.length, 3);
  assert.equal(tree(fixture.node('chat-history'), 'strong').some(n => n.textContent === 'Hello'), true);
  assert.equal(tree(fixture.node('chat-history'), 'section').length, 0);
});
