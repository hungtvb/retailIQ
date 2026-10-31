/* RetailIQ flow graph. Deterministic layout, no external dependency or injected HTML. */
(function (root) {
  'use strict';
  const SVG = 'http://www.w3.org/2000/svg';
  const NODE_W = 188;
  const NODE_H = 83;
  const LANE_W = 255;
  const START_X = 33;
  const START_Y = 91;
  const ROW_STEP = 111;
  const LANES = [
    {title:'01  INPUT',description:'Request and routing'},
    {title:'02  EXECUTION',description:'Agents and data tools'},
    {title:'03  VALIDATION',description:'Checks and feedback'},
    {title:'04  DECISION',description:'Human review and result'}
  ];
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
      {from:'request',to:'router',label:'route'},
      {from:'router',to:'agent',label:'delegate'},
      {from:'agent',to:'tool',label:'call'},
      {from:'tool',to:'evidence',label:'rows'},
      {from:'evidence',to:'answer',label:'respond'}
    ]
  };
  const STATUS = {
    idle:'WAITING',running:'RUNNING',completed:'DONE',awaiting:'APPROVAL',
    blocked:'BLOCKED',failed:'FAILED',skipped:'NOT REACHED'
  };
  const MARKER_COLORS = {
    idle:'#a4b4c7',active:'#22987d',running:'#3986ca',
    blocked:'#c75c57',feedback:'#bc813b'
  };
  function svgEl(tag, attrs) {
    const element = document.createElementNS(SVG,tag);
    Object.entries(attrs || {}).forEach(([key,value])=>element.setAttribute(key,String(value)));
    return element;
  }
  function laneOf(node) {
    if (node.kind==='input' || node.id==='router' || node.id==='scope_guard') return 0;
    if (node.kind==='agent' || node.kind==='tool' || node.id==='semantic_layer') return 1;
    if (node.kind==='human' || node.kind==='output') return 3;
    return 2;
  }
  function layout(nodes) {
    const groups = [[],[],[],[]];
    for (const node of nodes) groups[laneOf(node)].push(node);
    const lastExecutionY=START_Y + Math.max(0,groups[1].length-1)*ROW_STEP;
    const lastRequestY=START_Y + Math.max(0,groups[0].length-1)*ROW_STEP;
    const verificationY=groups[1].length ? lastExecutionY : lastRequestY;
    const positions=new Map();
    groups.forEach((items,lane)=>{
      items.forEach((node,i)=>{
        const anchor = lane===2 ? verificationY : lane===3 ?
          (groups[2].length ? verificationY : lastExecutionY) : START_Y;
        positions.set(node.id,{x:START_X+lane*LANE_W,
          y:anchor+i*ROW_STEP,lane});
      });
    });
    const maxY=Math.max(START_Y,...Array.from(positions.values(),p=>p.y));
    return {positions,width:LANE_W*4+12,height:maxY+NODE_H+55};
  }
  let graphSequence = 0;
  function mount(elementId, definition, options = {}) {
    const host=document.getElementById(elementId);
    if (!host || !definition) return null;
    const nodes=Array.isArray(definition.nodes)?definition.nodes.slice(0,20):[];
    const edges=Array.isArray(definition.edges)?definition.edges.slice(0,40):[];
    const lineage=definition.lineage && typeof definition.lineage==='object'?definition.lineage:{};
    const {positions,width,height}=layout(nodes);
    const uid='ri-graph-'+(++graphSequence);
    const nodeLookup=new Map(),linkLookup=new Map();
    const detail=options.detailId?document.getElementById(options.detailId):null;
    const timers=[];
    let selected=null;
    const viewport=document.createElement('div');
    viewport.className='graph-scroll';
    viewport.tabIndex=0;
    viewport.setAttribute('role','region');
    viewport.setAttribute('aria-label','Workflow, from input on the left to decision on the right. Scroll horizontally when necessary.');
    const canvas=document.createElement('div');
    canvas.className='graph-canvas';
    canvas.style.width=width+'px';
    canvas.style.height=height+'px';
    for (let i=0;i<4;i++) {
      const lane=document.createElement('div');
      lane.className='graph-lane';
      lane.style.left=(i*LANE_W+13)+'px';
      lane.style.width=(LANE_W-8)+'px';
      lane.style.height=(height-12)+'px';
      const heading=document.createElement('div');
      heading.className='graph-lane-heading';
      const title=document.createElement('strong');
      title.textContent=LANES[i].title;
      const description=document.createElement('span');
      description.textContent=LANES[i].description;
      heading.append(title,description);
      lane.appendChild(heading);
      canvas.appendChild(lane);
    }
    const svg=svgEl('svg',{
      class:'graph-edges',viewBox:'0 0 '+width+' '+height,
      'aria-hidden':'true'
    });
    svg.style.width=width+'px';
    svg.style.height=height+'px';
    const defs=svgEl('defs');
    for (const [name,color] of Object.entries(MARKER_COLORS)) {
      const marker=svgEl('marker',{id:uid+'-'+name,markerWidth:8,markerHeight:8,
        refX:7,refY:4,orient:'auto',markerUnits:'userSpaceOnUse'});
      marker.appendChild(svgEl('path',{d:'M 0 0 L 7 4 L 0 8 z',fill:color}));
      defs.appendChild(marker);
    }
    svg.appendChild(defs);
    function marker(name) {return 'url(#'+uid+'-'+name+')';}
    edges.forEach((edge)=>{
      const a=positions.get(edge.from),b=positions.get(edge.to);
      if(!a || !b) return;
      const feedback=edge.label==='retry'||edge.label==='revise'||b.lane<a.lane;
      const sameLane=a.lane===b.lane && !feedback;
      let drawing,tx,ty;
      if(feedback) {
        // A separate return channel between execution and validation lanes.
        // Avoid sweeping a retry line through the agent cards.
        const gutter=START_X+2*LANE_W-24+(edge.label==='revise'?-12:0);
        const x1=a.lane===b.lane?a.x+NODE_W:a.x;
        const y1=a.y+NODE_H/2;
        const x2=b.x+NODE_W;
        const y2=b.y+NODE_H/2;
        drawing='M '+x1+' '+y1+' L '+gutter+' '+y1+
          ' L '+gutter+' '+y2+' L '+x2+' '+y2;
        tx=gutter-7;ty=(y1+y2)/2;
      } else if(sameLane) {
        const x=a.x+NODE_W/2, y1=a.y+NODE_H, y2=b.y;
        drawing='M '+x+' '+y1+' C '+x+' '+(y1+24)+', '+x+' '+(y2-24)+', '+x+' '+y2;
        tx=x+33;ty=(y1+y2)/2;
      } else {
        const x1=a.x+NODE_W,y1=a.y+NODE_H/2;
        const x2=b.x,y2=b.y+NODE_H/2;
        drawing='M '+x1+' '+y1+' C '+(x1+32)+' '+y1+
          ', '+(x2-32)+' '+y2+', '+x2+' '+y2;
        tx=(x1+x2)/2;ty=(y1+y2)/2-11;
      }
      const path=svgEl('path',{d:drawing,
        class:'graph-link'+(feedback?' graph-link-feedback':''),
        'marker-end':marker('idle')});
      svg.appendChild(path);
      const caption=svgEl('g',{class:'graph-edge-caption'});
      if(edge.label) {
        const label=String(edge.label).slice(0,20);
        const labelWidth=Math.max(34,label.length*6.2+14);
        caption.appendChild(svgEl('rect',{x:tx-labelWidth/2,y:ty-11,width:labelWidth,
          height:18,rx:6}));
        const labelText=svgEl('text',{x:tx,y:ty+1,
          'text-anchor':'middle',class:'graph-edge-label'});
        labelText.textContent=label;
        caption.appendChild(labelText);
      }
      svg.appendChild(caption);
      linkLookup.set(edge.from+'->'+edge.to,{path,caption,feedback});
    });
    canvas.appendChild(svg);
    function inspect(id) {
      const node=nodes.find(n=>n.id===id);
      if(!node) return;
      const button=nodeLookup.get(id);
      for (const other of nodeLookup.values()) other.classList.remove('graph-node-selected');
      button.classList.add('graph-node-selected');
      for (const edge of linkLookup.values()) edge.path.classList.remove('graph-link-selected');
      const incoming=edges.filter(e=>e.to===id);
      const outgoing=edges.filter(e=>e.from===id);
      [...incoming,...outgoing].forEach(e=>{
        const entry=linkLookup.get(e.from+'->'+e.to);
        if(entry) entry.path.classList.add('graph-link-selected');
      });
      selected=id;
      if(typeof options.onSelect==='function') options.onSelect({
        id,node,status:button.dataset.status,
        evidence:button.dataset.detail||'',lineage:lineage[id]||null,
        incoming,outgoing
      });
      if(detail) {
        const inLabels=incoming.map(e=>e.from+(e.label?' ['+e.label+']':'')).join(', ')||'start';
        const outLabels=outgoing.map(e=>e.to+(e.label?' ['+e.label+']':'')).join(', ')||'end';
        const evidence=button.dataset.detail||'No execution evidence recorded.';
        detail.textContent=node.label+' · '+(STATUS[button.dataset.status]||'WAITING')+
          ' | IN ← '+inLabels+' | OUT → '+outLabels+' | '+evidence;
      }
    }
    nodes.forEach((node,index)=>{
      const pos=positions.get(node.id);
      if(!pos) return;
      const button=document.createElement('button');
      button.type='button';
      button.className='graph-node graph-node-'+(node.kind||'agent');
      button.dataset.node=node.id;
      button.dataset.status='idle';
      button.style.left=pos.x+'px';
      button.style.top=pos.y+'px';
      const headline=document.createElement('span');
      headline.className='graph-node-header';
      const seq=document.createElement('span');
      seq.className='graph-node-number';
      seq.textContent=String(index+1).padStart(2,'0');
      const kind=document.createElement('span');
      kind.className='graph-node-kind';
      kind.textContent=String(node.kind||'step').toUpperCase();
      headline.append(seq,kind);
      const name=document.createElement('span');
      name.className='graph-node-name';
      name.textContent=node.label;
      const state=document.createElement('span');
      state.className='graph-node-status';
      state.textContent='WAITING';
      button.append(headline,name,state);
      button.setAttribute('aria-label',node.label+', waiting. Select for inputs, outputs and evidence.');
      button.addEventListener('click',()=>inspect(node.id));
      nodeLookup.set(node.id,button);
      canvas.appendChild(button);
    });
    viewport.appendChild(canvas);
    // Show all four phases at once when space permits; preserve horizontal
    // scrolling on smaller screens where labels would become unreadable.
    if (host.__riGraphObserver) host.__riGraphObserver.disconnect();
    host.replaceChildren(viewport);
    if (typeof root.ResizeObserver === 'function') {
      const fit = () => {
        const available = viewport.clientWidth;
        if (!available) return; // scenario graph may be hidden until selected
        canvas.style.zoom = available >= 630
          ? String(Math.min(1, (available - 10) / width)) : '';
      };
      const observer = new root.ResizeObserver(fit);
      observer.observe(viewport);
      host.__riGraphObserver = observer;
      if (typeof root.requestAnimationFrame === 'function') root.requestAnimationFrame(fit);
    }
    if(options.detailed && Object.keys(lineage).length) {
      const section=document.createElement('section');
      section.className='graph-provenance';
      const heading=document.createElement('div');
      heading.className='graph-provenance-heading';
      const title=document.createElement('strong');
      title.textContent='Tools & data lineage';
      const warning=document.createElement('span');
      warning.textContent='Reference metadata · a reached step is not proof of an agent-owned tool call';
      heading.append(title,warning);
      section.appendChild(heading);
      const list=document.createElement('div');
      list.className='graph-lineage-list';
      for(const [nodeId,info] of Object.entries(lineage)) {
        const owner=nodes.find(n=>n.id===nodeId);
        if(!owner||!info||typeof info!=='object') continue;
        const item=document.createElement('button');
        item.type='button';
        item.className='graph-lineage-item';
        item.dataset.owner=nodeId;
        const append=(label,value,css)=>{
          const box=document.createElement('span');
          box.className='graph-lineage-part '+css;
          const tag=document.createElement('small');
          tag.textContent=label;
          const name=document.createElement('strong');
          name.textContent=String(value||'Not recorded');
          box.append(tag,name);
          item.appendChild(box);
        };
        const arrow=label=>{
          const el=document.createElement('span');
          el.className='graph-lineage-arrow';
          el.textContent='→';
          el.setAttribute('aria-label',label);
          el.title=label;
          item.appendChild(el);
        };
        append('STEP',owner.label,'graph-part-agent');
        arrow('uses / computes');
        append('TOOL / OPERATION',info.tool,'graph-part-tool');
        arrow('source / inputs');
        append('DATA SOURCE',info.source,'graph-part-source');
        item.title=String(info.relation||'Reference lineage');
        item.addEventListener('click',()=>{
          inspect(nodeId);
          nodeLookup.get(nodeId)?.scrollIntoView({block:'nearest',inline:'nearest'});
        });
        list.appendChild(item);
      }
      section.appendChild(list);
      host.appendChild(section);
    }
    function setEdge(previous,id,status) {
      const edge=linkLookup.get(previous+'->'+id);
      if(!edge) return;
      edge.path.classList.add('graph-link-active');
      edge.path.classList.toggle('graph-link-running',status==='running');
      edge.path.classList.toggle('graph-link-blocked',status==='blocked'||status==='failed');
      edge.path.classList.toggle('graph-link-feedback-active',edge.feedback);
      edge.caption.classList.add('graph-edge-used');
      const style=(status==='blocked'||status==='failed')?'blocked':
        edge.feedback?'feedback':status==='running'?'running':'active';
      edge.path.setAttribute('marker-end',marker(style));
    }
    function update(id,status,message,previous) {
      const button=nodeLookup.get(id);
      if(!button||!Object.hasOwn(STATUS,status)||status==='idle') return;
      button.dataset.status=status;
      button.querySelector('.graph-node-status').textContent=STATUS[status];
      button.setAttribute('aria-label',button.querySelector('.graph-node-name').textContent+
        ', '+STATUS[status].toLowerCase()+'. Select for inputs, outputs and evidence.');
      if(typeof message==='string'&&message.trim()) button.dataset.detail=message.slice(0,240);
      if(previous) setEdge(previous,id,status);
      if(selected===id) inspect(id);
      else if(!selected && detail) {
        detail.textContent=button.querySelector('.graph-node-name').textContent+
          ' · '+STATUS[status]+' · '+(button.dataset.detail||'');
      }
      if(options.follow) button.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'});
    }
    function reset() {
      timers.splice(0).forEach(clearTimeout);
      selected=null;
      for(const button of nodeLookup.values()) {
        button.dataset.status='idle';
        button.querySelector('.graph-node-status').textContent='WAITING';
        button.classList.remove('graph-node-selected');
        delete button.dataset.detail;
      }
      for(const edge of linkLookup.values()) {
        edge.path.classList.remove('graph-link-active','graph-link-running',
          'graph-link-blocked','graph-link-feedback-active','graph-link-selected');
        edge.path.setAttribute('marker-end',marker('idle'));
        edge.caption.classList.remove('graph-edge-used');
      }
      if(detail) detail.textContent='Select a node to inspect incoming/outgoing handoffs and recorded evidence.';
    }
    function markTerminal(status) {
      if(status!=='blocked'&&status!=='rejected') return;
      for(const button of nodeLookup.values()) {
        if(button.dataset.status==='idle') {
          button.dataset.status='skipped';
          button.querySelector('.graph-node-status').textContent='NOT REACHED';
        }
      }
    }
    function showAll(events,terminalStatus) {
      reset();
      for(const [i,item] of (Array.isArray(events)?events.slice(0,40):[]).entries()) {
        update(item.node,item.status||'completed',item.detail||'',item.from);
        if(typeof options.onStep==='function') options.onStep(item,i);
      }
      markTerminal(terminalStatus);
    }
    function replay(events,terminalStatus) {
      reset();
      const visible=Array.isArray(events)?events.slice(0,40):[];
      visible.forEach((item,i)=>{
        timers.push(setTimeout(()=>{
          update(item.node,item.status||'completed',item.detail||'',item.from);
          if(typeof options.onStep==='function') options.onStep(item,i);
          if(i===visible.length-1) markTerminal(terminalStatus);
        },i*260));
      });
    }
    return {update,reset,replay,showAll,select:inspect,hasNode:(id)=>nodeLookup.has(id)};
  }
  let chat=null,chatHasEvidence=false;
  function chatClear() {chat=mount('execution-graph',chatDefinition);}
  function chatReset() {
    chatHasEvidence=false;
    chatClear();
    if(chat)chat.update('request','completed','User question submitted');
  }
  function chatEvent(event) {
    if(!chat||!event||typeof event.event!=='string')return;
    const name=event.event;
    const detail=String(event.agent||event.subagent||event.tool||name).slice(0,100);
    if(name==='agent.routed'||name==='graph.node_updated'){
      chat.update('router','completed',name,'request');
      chat.update('agent','running',detail,'router');
    } else if(name.startsWith('tool.')){
      chat.update('router','completed','Routing finished','request');
      chat.update('agent','completed',detail,'router');
      chat.update('tool',name.endsWith('.started')?'running':
        name.endsWith('.failed')?'failed':'completed',detail,'agent');
      if(name.endsWith('.completed')){
        chatHasEvidence=true;
        chat.update('evidence','completed','Tool result received','tool');
      }
    } else if(name.startsWith('agent.handoff')||name.startsWith('agent.subagent')){
      chat.update('agent','running',detail,'router');
    } else if(name.startsWith('llm.')){
      chat.update('agent',name.endsWith('.failed')?'failed':'running',detail,'router');
    }
  }
  function chatFinished(ok) {
    if(!chat)return;
    if(ok){
      chat.update('router','completed','Intent selected','request');
      chat.update('agent','completed','Agent completed','router');
      if(chatHasEvidence)chat.update('evidence','completed','Backend evidence collected','tool');
      chat.update('answer','completed','Final answer received',chatHasEvidence?'evidence':null);
    } else chat.update('answer','failed','Request failed');
  }
  root.RetailGraph={mount,chatClear,chatReset,chatEvent,chatFinished};
})(window);
