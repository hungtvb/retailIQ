/* Four-week synthetic workflow lab: renders backend evidence, never invents a step. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let scenarios = [];
  let run = null;
  let graph = null;
  let busy = false;
  function status(message, isError = false) {
    const el = $('workflow-status');
    el.textContent = message;
    el.classList.toggle('workflow-error', isError);
  }
  function showRun(result) {
    run = result;
    $('workflow-report').textContent = result.report || 'No report';
    $('workflow-run-id').textContent = 'Run ' + result.id.slice(0,8) +
      ' · ' + result.status.replaceAll('_',' ');
    graph = window.RetailGraph?.mount('workflow-graph',result.graph,
                                    {detailId:'workflow-node-detail',follow:false});
    graph?.replay(result.events);
    const waiting = result.status === 'pending_manager';
    $('workflow-review-controls').hidden = !waiting;
    if (waiting) {
      status('Waiting for simulated manager decision. Approval does not create an order or change price.');
    } else if (result.status==='blocked') {
      status('Verification blocked this proposal. No action was taken.',true);
    } else {
      status('Backend execution finished · graph is a replay of recorded events.');
    }
  }
  function selectedDefinition() {
    return scenarios.find(x=>x.id===$('workflow-scenario').value);
  }
  function preview() {
    const scenario = selectedDefinition();
    if (!scenario) return;
    run = null;
    $('workflow-report').textContent=scenario.title;
    $('workflow-review-controls').hidden=true;
    $('workflow-run-id').textContent='Not run';
    graph = window.RetailGraph?.mount('workflow-graph',scenario,
                                     {detailId:'workflow-node-detail',follow:false});
    status('Choose inputs, then Run. Nodes stay idle until the backend returns a trace.');
  }
  async function request(url, body) {
    const response = await fetch(url,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)
    });
    const data=await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(data.detail || 'HTTP '+response.status);
    return data;
  }
  async function execute() {
    if(busy) return;
    busy=true; $('workflow-run').disabled=true;
    $('workflow-review-controls').hidden=true;
    status('Running the selected local workflow…');
    const scenario=$('workflow-scenario').value;
    const sku=$('workflow-sku').value.trim().toUpperCase();
    const quantity=Number($('workflow-quantity').value);
    try {
      const result=await request('/api/workflows/run',{
        scenario,sku,quantity,role:$('workflow-role').value
      });
      showRun(result);
    } catch(error) {
      status('Cannot run: '+error.message,true);
    } finally { busy=false; $('workflow-run').disabled=false; }
  }
  async function review(decision) {
    if(busy || !run || run.status!=='pending_manager') return;
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
    if (!$('workflow-scenario')) return;
    try {
      const response=await fetch('/api/workflows/definitions',{cache:'no-store'});
      if(!response.ok) throw new Error('HTTP '+response.status);
      const data=await response.json();
      scenarios=Array.isArray(data.scenarios)?data.scenarios:[];
      const sel=$('workflow-scenario');
      sel.replaceChildren();
      for(const scenario of scenarios) {
        const option=document.createElement('option');
        option.value=scenario.id;
        option.textContent=scenario.title;
        sel.appendChild(option);
      }
      sel.value='week4';
      preview();
    } catch(error) {
      status('Cannot load workflow definitions: '+error.message,true);
    }
    $('workflow-form').addEventListener('submit',e=>{e.preventDefault();execute();});
    $('workflow-scenario').addEventListener('change',preview);
    $('workflow-run').addEventListener('click',execute);
    $('workflow-approve').addEventListener('click',()=>review('approve'));
    $('workflow-reject').addEventListener('click',()=>review('reject'));
  }
  window.addEventListener('DOMContentLoaded',init);
})();
