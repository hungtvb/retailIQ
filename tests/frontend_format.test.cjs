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
  format.renderMarkdown(target,'### Sales\\n**Strong** & *italic*\\n[valid](https://example.org) [bad](javascript:alert(1))\\n<img src=x onerror=alert(1)>');
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
  format.renderMarkdown(root,'- one\\n- two\\n\\n| Product | Units |\\n| --- | --- |\\n| Laptop | 22 |\\n\\n```sql\\nSELECT * FROM orders;\\n```');
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
