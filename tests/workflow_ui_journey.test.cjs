/* One integrated browser-DOM journey: select scenario → inspect source → run →
   inspect timeline → review. No extra test framework or production endpoint mocks. */
'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

class Node {
  constructor(tag='div') {
    this.tagName=tag;this.children=[];this.dataset={};this.style={};
    this.attributes={};this.handlers={};this._text='';this.className='';
    this.value='';this.disabled=false;this.hidden=false;
    this.classList={
      add:(...names)=>this.classes(new Set([...this.className.split(' '),...names])),
      remove:(...names)=>this.classes(new Set(this.className.split(' ').filter(x=>!names.includes(x)))),
      toggle:(name,enabled)=>{
        const names=new Set(this.className.split(' ').filter(Boolean));
        if(enabled===undefined?!names.has(name):enabled)names.add(name);
        else names.delete(name);
        this.classes(names);
      }
    };
  }
  classes(names){this.className=[...names].filter(Boolean).join(' ');}
  get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  append(...children){this.children.push(...children);}
  appendChild(child){this.append(child);return child;}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(name,value){this.attributes[name]=String(value);}
  querySelectorAll(selector) {
    const all=[];
    function visit(node) {
      for(const child of node.children) {
        if(selector.startsWith('.') && child.className.split(' ').includes(selector.slice(1)))all.push(child);
        if(selector==='[data-event-index]' && child.dataset.eventIndex!==undefined)all.push(child);
        visit(child);
      }
    }
    visit(this);return all;
  }
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  addEventListener(event,callback){this.handlers[event]=callback;}
  scrollIntoView(){}
  click(){if(this.handlers.click)return this.handlers.click();}
}
const files=Object.fromEntries([
  'workflow-graph.js','workflow-ui.js'
].map(name=>[name,fs.readFileSync(path.join(__dirname,'../web/assets',name),'utf8')]));

test('four-week graph UI journey retains real event states and explicit source provenance',async()=>{
  const ids=new Map();
  const get=id=>{if(!ids.has(id))ids.set(id,new Node());return ids.get(id);};
  const overview=new Node('button');overview.dataset.workflowView='overview';
  const detailed=new Node('button');detailed.dataset.workflowView='detailed';
  const document={
    getElementById:get,
    createElement:tag=>new Node(tag),
    createElementNS:(_ns,tag)=>new Node(tag),
    querySelectorAll:selector=>selector==='[data-workflow-view]'?[overview,detailed]:[]
  };
  const definition={
    id:'week4',title:'Week 4 order proposal',execution:'deterministic_local_simulation',
    nodes:[
      {id:'request',label:'Order request',kind:'input'},
      {id:'inventory_search_agent',label:'Inventory Agent',kind:'agent'},
      {id:'verification',label:'Verification',kind:'guard'},
      {id:'manager_approval',label:'Manager review',kind:'human'},
      {id:'finalize',label:'Recorded decision',kind:'output'}
    ],
    edges:[
      {from:'request',to:'inventory_search_agent',label:'read'},
      {from:'inventory_search_agent',to:'verification',label:'verify'},
      {from:'verification',to:'manager_approval',label:'review'},
      {from:'manager_approval',to:'finalize',label:'decision'}
    ],
    lineage:{
      inventory_search_agent:{
        tool:'inventory(sku) (preflight)',
        source:'SQLite: inventory + products + locations',
        relation:'uses preflight data; no agent-owned tool call',
        evidence:'SKU, location and units'
      }
    }
  };
  const steps=[
    {node:'request',status:'completed',detail:'Order 2 units',from:null},
    {node:'inventory_search_agent',status:'completed',detail:'37 units',from:'request'},
    {node:'verification',status:'completed',detail:'Valid stock',from:'inventory_search_agent'},
    {node:'manager_approval',status:'awaiting',detail:'Manager review pending',from:'verification'}
  ];
  let currentId='test-run-id';
  let calls=[];
  async function fetch(url,options={}){
    const method=options.method||'GET';calls.push(method+' '+url);
    const data= method==='GET'?
      {scenarios:[...['week1','week2','week3','alerts'].map(id=>({...definition,id,title:id})),definition]}:
      url==='/api/workflows/run'?
        {id:currentId,status:'pending_manager',report:'Draft only; no order inserted',graph:definition,events:steps}:
        {id:currentId,status:'approved_simulated',report:'Recorded only',graph:definition,
          events:[...steps,{node:'manager_approval',status:'completed',
            detail:'Manager approved',from:'verification'},
            {node:'finalize',status:'completed',detail:'Recorded',from:'manager_approval'}]};
    return {ok:true,status:200,json:async()=>data};
  }
  let onReady;
  const window={
    addEventListener:(event,callback)=>{if(event==='DOMContentLoaded')onReady=callback;}
  };
  const context=vm.createContext({window,document,fetch,
    setTimeout:callback=>{callback();return 1;},clearTimeout:()=>{},console});
  vm.runInContext(files['workflow-graph.js'],context,{filename:'workflow-graph.js'});
  vm.runInContext(files['workflow-ui.js'],context,{filename:'workflow-ui.js'});
  await onReady();
  assert.equal(get('workflow-scenario').value,'week4');
  assert.match(get('workflow-status').textContent,/Choose inputs/);
  assert.equal(get('workflow-replay').disabled,true);
  detailed.click();
  assert.equal(detailed.attributes['aria-pressed'],'true');
  assert.ok(get('workflow-graph').textContent.includes('SQLite: inventory + products + locations'));

  get('workflow-role').value='manager';
  get('workflow-sku').value='EL-003';
  get('workflow-quantity').value='2';
  await get('workflow-run').click();
  assert.equal(get('workflow-review-controls').hidden,false);
  assert.equal(get('workflow-replay').disabled,false);
  assert.equal(get('workflow-timeline').querySelectorAll('[data-event-index]').length,4);
  const buttons=get('workflow-graph').querySelectorAll('.graph-node');
  const inventory=buttons.find(n=>n.dataset.node==='inventory_search_agent');
  assert.equal(inventory.dataset.status,'completed');
  inventory.click();
  assert.match(get('workflow-node-detail').textContent,/preflight data; no agent-owned tool call/);
  assert.match(get('workflow-node-detail').textContent,/SQLite: inventory/);
  get('workflow-replay').click();
  assert.equal(get('workflow-timeline').querySelectorAll('.workflow-timeline-active').length,1);
  await get('workflow-approve').click();
  assert.match(get('workflow-run-id').textContent,/approved simulated/);
  assert.equal(get('workflow-review-controls').hidden,true);
  const final=get('workflow-graph').querySelectorAll('.graph-node').find(n=>n.dataset.node==='finalize');
  assert.equal(final.dataset.status,'completed');
  assert.ok(calls.includes('POST /api/workflows/run'));
  assert.ok(calls.includes('POST /api/workflows/runs/test-run-id/review'));
});
