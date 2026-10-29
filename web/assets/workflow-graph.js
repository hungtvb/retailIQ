/* RetailIQ graph renderer: no dependencies, no HTML interpolation of tool output. */
(function (root) {
  'use strict';
  const SVG = 'http://www.w3.org/2000/svg';
  const chatDefinition = {
    nodes: [
      {id:'request',label:'Question',kind:'input'},
      {id:'router',label:'Intent router',kind:'guard'},
      {id:'agent',label:'Specialist agent',kind:'agent'},
      {id:'tool',label:'SQL / Retrieval',kind:'tool'},
      {id:'evidence',label:'Evidence',kind:'guard'},
      {id:'answer',label:'Answer',kind:'output'}
    ],
    edges: [
      {from:'request',to:'router'}, {from:'router',to:'agent'},
      {from:'agent',to:'tool'}, {from:'tool',to:'evidence'},
      {from:'evidence',to:'answer'}
    ]
  };
  function svgEl(tag, attrs) {
    const element = document.createElementNS(SVG, tag);
    Object.entries(attrs || {}).forEach(([key,value]) => element.setAttribute(key,String(value)));
    return element;
  }
  function statusLabel(s) {
    return ({idle:'WAITING', running:'RUNNING',completed:'DONE',awaiting:'APPROVAL',
             blocked:'BLOCKED',failed:'FAILED'}[s] || 'WAITING');
  }
  function mount(elementId, definition, options = {}) {
    const host = document.getElementById(elementId);
    if (!host) return null;
    const nodes = Array.isArray(definition.nodes) ? definition.nodes.slice(0,20) : [];
    const edges = Array.isArray(definition.edges) ? definition.edges.slice(0,40) : [];
    const width = Math.max(750,nodes.length * 168 + 40), height = 244;
    let timers = [];
    const lookup = new Map();
    const links = new Map();
    const positions = new Map(nodes.map((node,index) => [node.id,{
      x: 30 + index * 168, y: 67 + (index % 2 ? 29 : 0)}]));
    const viewport = document.createElement('div');
    viewport.className = 'graph-scroll';
    viewport.setAttribute('aria-label','Execution dependency graph');
    const canvas = document.createElement('div');
    canvas.className = 'graph-canvas';
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    const svg = svgEl('svg',{class:'graph-edges',viewBox:'0 0 '+width+' '+height,'aria-hidden':'true'});
    svg.style.width=width+'px';
    svg.style.height=height+'px';
    edges.forEach((edge) => {
      const a = positions.get(edge.from), b = positions.get(edge.to);
      if (!a || !b) return;
      const x1 = a.x + 142, y1=a.y+39, x2=b.x, y2=b.y+39;
      const path = svgEl('path',{d:'M '+x1+' '+y1+' C '+(x1+22)+' '+y1+', '+(x2-22)+' '+y2+', '+x2+' '+y2,
        class:'graph-link'});
      svg.appendChild(path);
      links.set(edge.from+'->'+edge.to,path);
    });
    canvas.appendChild(svg);
    const detail = options.detailId ? document.getElementById(options.detailId) : null;
    nodes.forEach((node) => {
      const pos = positions.get(node.id);
      const button = document.createElement('button');
      button.type='button';
      button.className='graph-node graph-node-'+(node.kind || 'agent');
      button.dataset.node=node.id;
      button.dataset.status='idle';
      button.style.left=pos.x+'px';
      button.style.top=pos.y+'px';
      const name = document.createElement('span');
      name.className='graph-node-name'; name.textContent=node.label;
      const state = document.createElement('span');
      state.className='graph-node-status'; state.textContent='WAITING';
      button.append(name,state);
      button.title=node.label;
      button.addEventListener('click',()=> {
        nodes.forEach(n=>lookup.get(n.id)?.classList.remove('graph-node-selected'));
        button.classList.add('graph-node-selected');
        if (detail) detail.textContent=button.dataset.detail || node.label+' · '+statusLabel(button.dataset.status);
      });
      lookup.set(node.id,button);
      canvas.appendChild(button);
    });
    viewport.appendChild(canvas);
    host.replaceChildren(viewport);
    function update(id, status, message, previous) {
      const button=lookup.get(id);
      if (!button) return;
      if (!['running','completed','awaiting','blocked','failed'].includes(status)) return;
      button.dataset.status=status;
      button.querySelector('.graph-node-status').textContent=statusLabel(status);
      if (typeof message==='string' && message.trim()) {
        button.dataset.detail=button.querySelector('.graph-node-name').textContent+' · '+message.slice(0,180);
      }
      if (previous) {
        const edge=links.get(previous+'->'+id);
        if(edge) edge.classList.add('graph-link-active');
      }
      if (detail) detail.textContent=button.dataset.detail || id+' · '+statusLabel(status);
      if (options.follow) button.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'});
    }
    function reset() {
      timers.forEach(clearTimeout);
      timers=[];
      for (const button of lookup.values()) {
        button.dataset.status='idle';
        button.querySelector('.graph-node-status').textContent='WAITING';
        button.classList.remove('graph-node-selected');
        delete button.dataset.detail;
      }
      for (const line of links.values()) line.classList.remove('graph-link-active');
      if (detail) detail.textContent='Select a node to inspect its execution evidence.';
    }
    function replay(events) {
      reset();
      (Array.isArray(events) ? events.slice(0,30) : []).forEach((item,i) => {
        const timer=setTimeout(() => update(item.node,item.status||'completed',
          item.detail||'',item.from),i*220);
        timers.push(timer);
      });
    }
    return {update,reset,replay,hasNode:(id)=>lookup.has(id)};
  }
  let chat = null;
  function chatReset() {
    chat = mount('execution-graph',chatDefinition);
    if (chat) chat.update('request','completed','User question submitted');
  }
  function chatEvent(event) {
    if (!chat || !event || typeof event.event!=='string') return;
    const name=event.event;
    const detail=String(event.agent || event.subagent || event.tool || name).slice(0,100);
    if (name==='agent.routed' || name==='graph.node_updated') {
      chat.update('router','completed',name,'request');
      chat.update('agent','running',detail,'router');
    } else if (name.startsWith('tool.')) {
      chat.update('router','completed','Routing finished','request');
      chat.update('agent','completed',detail,'router');
      chat.update('tool',name.endsWith('.started')?'running':
                 name.endsWith('.failed')?'failed':'completed',detail,'agent');
      if (name.endsWith('.completed')) chat.update('evidence','completed','Tool result received','tool');
    } else if (name.startsWith('agent.handoff') || name.startsWith('agent.subagent')) {
      chat.update('agent','running',detail,'router');
    } else if (name.startsWith('llm.')) {
      chat.update('agent',name.endsWith('.failed')?'failed':'running',detail,'router');
    }
  }
  function chatFinished(ok) {
    if (!chat) return;
    if (ok) {
      chat.update('router','completed','Intent selected','request');
      chat.update('agent','completed','Agent completed','router');
      chat.update('evidence','completed','Backend result returned');
      chat.update('answer','completed','Final answer received','evidence');
    } else {
      chat.update('answer','failed','Request failed');
    }
  }
  root.RetailGraph={mount,chatReset,chatEvent,chatFinished};
})(window);
