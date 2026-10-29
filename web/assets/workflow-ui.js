/* RetailIQ workflow explorer. Backend recorded steps, static lineage labeled separately. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let scenarios = [];
  let run = null;
  let graph = null;
  let busy = false;
  let view = 'overview';
  let selectedId = '';

  function status(message, isError = false) {
    const el = $('workflow-status');
    el.textContent = message;
    el.classList.toggle('workflow-error', isError);
  }
  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  }
  function renderInspector(info) {
    const host = $('workflow-node-detail');
    host.replaceChildren();
    if (!info) {
      host.appendChild(element('p','workflow-help',
        'Select a graph node or timeline event to inspect its evidence, tool and data source.'));
      return;
    }
    selectedId = info.id;
    const title = element('h3','',info.node.label);
    const state = element('span','workflow-inspector-state',info.status.toUpperCase());
    state.dataset.status = info.status;
    const header = element('div','workflow-inspector-head');
    header.append(title,state);
    host.appendChild(header);

    function field(name,value) {
      const wrap = element('div','workflow-inspector-field');
      wrap.append(element('span','workflow-inspector-label',name),
                  element('span','workflow-inspector-value',value));
      host.appendChild(wrap);
    }
    field('Recorded node evidence',info.evidence || 'No execution event recorded for this step.');
    const inbound = info.incoming.map(e=>e.from+(e.label?' → '+e.label:'')).join(' · ');
    const outbound = info.outgoing.map(e=>e.label?e.label+' → '+e.to:e.to).join(' · ');
    field('Incoming handoffs',inbound || 'Start');
    field('Outgoing handoffs',outbound || 'End');
    if(info.lineage) {
      const title = element('h4','workflow-inspector-section','Tool & data provenance');
      host.appendChild(title);
      const flow = element('div','workflow-inspector-chain');
      flow.append(element('div','workflow-chain-agent',info.node.label),
                  element('span','workflow-chain-arrow','→'),
                  element('div','workflow-chain-tool',info.lineage.tool),
                  element('span','workflow-chain-arrow','→'),
                  element('div','workflow-chain-source',info.lineage.source));
      host.appendChild(flow);
      field('Relationship / execution type',info.lineage.relation);
      field('Expected source evidence',info.lineage.evidence);
      host.append(element('p','workflow-inspector-disclaimer',
        'Lineage is the documented implementation path. A completed specialist step does not establish an autonomous tool call.'));
    } else {
      field('Tool / source','No separately documented tool call on this node.');
    }
  }
  function highlightTimeline(index) {
    const list = $('workflow-timeline');
    for(const item of list.querySelectorAll('[data-event-index]')) {
      item.classList.toggle('workflow-timeline-active',Number(item.dataset.eventIndex)===index);
    }
  }
  function renderTimeline(events) {
    const list = $('workflow-timeline');
    list.replaceChildren();
    if (!events || !events.length) {
      list.appendChild(element('p','workflow-help','Run a scenario to see recorded execution steps.'));
      return;
    }
    events.forEach((event,i)=>{
      const item=element('button','workflow-timeline-item');
      item.type='button';
      item.dataset.eventIndex=String(i);
      const index=element('span','workflow-timeline-index',String(i+1).padStart(2,'0'));
      const main=element('span','workflow-timeline-main');
      main.append(element('strong','',event.node.replaceAll('_',' ')),
                  element('small','',event.detail||'No detail'));
      const state=element('span','workflow-timeline-status',
        (event.status||'completed').toUpperCase());
      state.dataset.status=event.status||'completed';
      item.append(index,main,state);
      item.addEventListener('click',()=>{
        graph?.select(event.node);
        highlightTimeline(i);
      });
      list.appendChild(item);
    });
  }
  function selectedDefinition() {
    return scenarios.find(item=>item.id===$('workflow-scenario').value);
  }
  function markView() {
    for(const control of document.querySelectorAll('[data-workflow-view]')) {
      const active=control.dataset.workflowView===view;
      control.setAttribute('aria-pressed',String(active));
      control.classList.toggle('workflow-view-active',active);
    }
  }
  function mountGraph(definition) {
    graph=window.RetailGraph?.mount('workflow-graph',definition,{
      detailed:view==='detailed',follow:false,
      onSelect:renderInspector,
      onStep:(_event,index)=>highlightTimeline(index)
    });
    if(run) {
      graph?.showAll(run.events,run.status);
    }
    if(selectedId && graph?.hasNode(selectedId)) graph.select(selectedId);
    else renderInspector(null);
  }
  function showRun(result) {
    run=result;
    $('workflow-report').textContent=result.report||'No report';
    $('workflow-run-id').textContent='Run '+result.id.slice(0,8)+
      ' · '+result.status.replaceAll('_',' ');
    selectedId='';
    renderTimeline(result.events);
    mountGraph(result.graph);
    $('workflow-replay').disabled=false;
    $('workflow-review-controls').hidden=result.status!=='pending_manager';
    if(result.status==='pending_manager') {
      status('Manager review pending (simulated). No order or price mutation.');
    } else if(result.status==='blocked') {
      status('Verification blocked this proposal. No action taken.',true);
    } else {
      status('Execution complete. Graph and timeline reflect recorded backend events.');
    }
  }
  function preview() {
    const definition=selectedDefinition();
    if(!definition) return;
    run=null;
    selectedId='';
    $('workflow-report').textContent=definition.title;
    $('workflow-review-controls').hidden=true;
    $('workflow-run-id').textContent='Not run';
    $('workflow-replay').disabled=true;
    renderTimeline([]);
    mountGraph(definition);
    status('Choose inputs and Run. Tool/source chains are references until a backend event is recorded.');
  }
  async function request(url,body) {
    const response=await fetch(url,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(data.detail||'HTTP '+response.status);
    return data;
  }
  async function execute() {
    if(busy) return;
    busy=true;
    $('workflow-run').disabled=true;
    $('workflow-review-controls').hidden=true;
    status('Running selected workflow…');
    try {
      const result=await request('/api/workflows/run',{
        scenario:$('workflow-scenario').value,
        sku:$('workflow-sku').value.trim().toUpperCase(),
        quantity:Number($('workflow-quantity').value),
        role:$('workflow-role').value
      });
      showRun(result);
    } catch(error) {
      status('Cannot run: '+error.message,true);
    } finally {
      busy=false;
      $('workflow-run').disabled=false;
    }
  }
  async function review(decision) {
    if(busy||!run||run.status!=='pending_manager') return;
    busy=true;
    $('workflow-approve').disabled=true;
    $('workflow-reject').disabled=true;
    try {
      const result=await request('/api/workflows/runs/'+encodeURIComponent(run.id)+'/review',{
        role:$('workflow-role').value,decision
      });
      showRun(result);
    } catch(error) {
      status('Review declined: '+error.message,true);
    } finally {
      busy=false;
      $('workflow-approve').disabled=false;
      $('workflow-reject').disabled=false;
    }
  }
  async function init() {
    if(!$('workflow-scenario')) return;
    renderInspector(null);
    renderTimeline([]);
    markView();
    $('workflow-replay').disabled=true;
    for(const control of document.querySelectorAll('[data-workflow-view]')) {
      control.addEventListener('click',()=>{
        view=control.dataset.workflowView;
        markView();
        mountGraph(run?run.graph:selectedDefinition());
      });
    }
    $('workflow-replay').addEventListener('click',()=>{
      if(run) graph?.replay(run.events,run.status);
    });
    $('workflow-form').addEventListener('submit',e=>{e.preventDefault();execute();});
    $('workflow-scenario').addEventListener('change',preview);
    $('workflow-run').addEventListener('click',execute);
    $('workflow-approve').addEventListener('click',()=>review('approve'));
    $('workflow-reject').addEventListener('click',()=>review('reject'));
    try {
      const response=await fetch('/api/workflows/definitions',{cache:'no-store'});
      if(!response.ok) throw new Error('HTTP '+response.status);
      const data=await response.json();
      scenarios=Array.isArray(data.scenarios)?data.scenarios:[];
      const selector=$('workflow-scenario');
      selector.replaceChildren();
      for(const scenario of scenarios) {
        const option=document.createElement('option');
        option.value=scenario.id;
        option.textContent=scenario.title;
        selector.appendChild(option);
      }
      selector.value='week4';
      preview();
    } catch(error) {
      status('Cannot load workflow definitions: '+error.message,true);
    }
  }
  window.addEventListener('DOMContentLoaded',init);
})();
