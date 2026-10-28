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
