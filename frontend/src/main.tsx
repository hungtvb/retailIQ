import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  applyExecutionEvent, emptyGraph, finishGraph, positionGraph,
  startGraph, unavailableGraph, type ExecutionEvent, type GraphState,
  type GraphNode, type PositionedNode
} from './graph';
import './styles.css';

type RecordRow = Record<string, unknown>;
type Evidence = {
  records?: RecordRow[];
  contexts?: Array<{source?: string}>;
  as_of?: string;
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  agent?: string;
  evidence?: Evidence;
  request_id?: string | null;
};
type SessionItem = { id: string; title: string; active_agent?: string };
type Session = SessionItem & { messages: Message[]; messages_truncated?: boolean };
type AskResult = Evidence & {
  answer: string; session_id?: string; active_agent?: string;
  request_id?: string; mode?: string; intent?: string;
};
type Phase = 'ready' | 'running' | 'complete' | 'error';
type StoredTrace = {
  request_id: string;
  status: 'complete';
  truncated: boolean;
  events: ExecutionEvent[];
};
type Account = {user_id:string;username:string;role:'analyst'|'manager';csrf_token:string};
type ReviewProposal = {
  proposal_id:string;case_id:string;cutoff:string;snapshot_id:string;
  warehouse_id:string;requested_units:number;available_units:number;
  status:string;version:number;source_sha256:string;policy_id:string;
  reviewed_by:string|null;operational_write_executed:boolean;
};
type ReviewEligibility = {
  eligible:boolean;reason_codes:string[];candidate?:ReviewProposal;
};

const IDEAS = [
  {label:'Top sellers',question:'Which products are top sellers?'},
  {label:'Stock levels',question:'How many units of AlphaBook Pro 14 are in stock?'},
  {label:'Revenue',question:'What is the revenue this month?'},
  {label:'Product details',question:'Tell me about USB-C GaN Charger 65W'}
];

function AppIcon({name, size=18}: {name:string;size?:number}) {
  const props={width:size,height:size,viewBox:'0 0 24 24',fill:'none',
    stroke:'currentColor',strokeWidth:1.7,strokeLinecap:'round' as const,
    strokeLinejoin:'round' as const, 'aria-hidden':true as const};
  if (name==='network') return <svg {...props}><rect x="9" y="2.5" width="6" height="6" rx="1.5"/><rect x="2" y="15.5" width="6" height="6" rx="1.5"/><rect x="16" y="15.5" width="6" height="6" rx="1.5"/><path d="M12 8.5v3.5M5 15.5V12h14v3.5"/></svg>;
  if (name==='plus') return <svg {...props}><path d="M12 4v16M4 12h16"/></svg>;
  if (name==='send') return <svg {...props}><path d="m21 3-8.4 18-2.6-7L3 11.4 21 3Z" /></svg>;
  if (name==='trash') return <svg {...props}><path d="M3 6h18M8 6V4h8v2m3 0-1 15H6L5 6m5 4v7m4-7v7"/></svg>;
  if (name==='menu') return <svg {...props}><path d="M4 6h16M4 12h16M4 18h16"/></svg>;
  if (name==='chat') return <svg {...props}><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H4l2.1-4.5A7.5 7.5 0 1 1 20 11.5Z"/></svg>;
  return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>;
}

const formatStatus = (s: string) => s === 'completed' ? 'Done' :
  s === 'running' ? 'Running' : s === 'failed' ? 'Failed' :
  s === 'observed' ? 'Observed' : 'Pending';

function arc(from: PositionedNode, to: PositionedNode, kind: string): string {
  const dx=to.x-from.x, dy=to.y-from.y;
  const distance=Math.max(1,Math.hypot(dx,dy));
  const ux=dx/distance,uy=dy/distance;
  const x1=from.x+ux*69, y1=from.y+uy*36;
  const x2=to.x-ux*69, y2=to.y-uy*36;
  const bend=kind==='handoff'? -34 : kind==='delegate'? 28 : 0;
  const cx=(x1+x2)/2 - uy*bend;
  const cy=(y1+y2)/2 + ux*bend;
  return 'M '+x1+' '+y1+' Q '+cx+' '+cy+' '+x2+' '+y2;
}
function wrapNodeLabel(label: string, limit = 18): string[] {
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  for (const word of words) {
    const index = lines.length - 1;
    if (index >= 0 && lines[index].length + word.length + 1 <= limit) {
      lines[index] += ' ' + word;
    } else if (lines.length < 2) {
      lines.push(word.slice(0, limit));
    }
  }
  if (lines.length === 0) return ['—'];
  if (words.join(' ').length > lines.join(' ').length) {
    lines[lines.length - 1] = lines[lines.length - 1].slice(0, limit - 1) + '…';
  }
  return lines;
}
function MatrixNode({node}: {node: PositionedNode}) {
  const colors: Record<string,string> = {
    request:'#8095aa',agent:'#895ed2',subagent:'#a77ce4',
    tool:'#448bd0',mcp:'#2989aa','mcp-server':'#177b95',output:'#10a38b'
  };
  const c=colors[node.kind] || '#8193a8';
  const isLive=node.status==='running';
  const labelLines = wrapNodeLabel(node.label);
  const hasSkill = Boolean(node.skill);
  // Keep the skill chip and the second tool-label line inside the card.
  const height = hasSkill ? 126 : labelLines.length > 1 ? 102 : 87;
  return <g className={'matrix-node matrix-'+node.kind+' state-'+node.status}
    transform={'translate('+node.x+' '+node.y+')'}
    aria-label={node.label+', '+formatStatus(node.status)}>
    <rect className="matrix-node-halo" x="-94" y="-48" width="188" height={height+8}
      rx="17" fill={c} opacity={isLive?.15:0}/>
    <rect x="-90" y="-44" width="180" height={height} rx="13"
      fill="white" stroke={node.status==='failed'?'#db6567':c}
      strokeWidth={node.status==='running'?2.6:1.8}/>
    <rect x="-90" y="-44" width="5" height={height} rx="2.5" fill={c}/>
    <circle cx="-67" cy="-22" r="5" fill={node.status==='failed'?'#e46e6b':
      node.status==='completed'?'#22af87':isLive?c:'#98a9b5'}/>
    <text x="-52" y="-18" fill="#607084" className="matrix-node-type">
      {node.kind==='mcp'?'MCP TOOL':node.kind==='mcp-server'?'MCP SERVER':node.kind.toUpperCase()}
    </text>
    {labelLines.map((line,i)=><text key={i} x="-70"
      y={i===0?7:26} className="matrix-node-label">{line}</text>)}
    <text x="-70" y={labelLines.length>1?41:27}
      className={'matrix-node-state text-'+node.status}>{formatStatus(node.status)}</text>
    {hasSkill && <>
      <rect x="-70" y="48" width="140" height="21" rx="6"
        fill="#effaf6" stroke="#b9e5d8"/>
      <text x="0" y="62" textAnchor="middle" className="matrix-skill">
        {(node.skillState==='loaded'?'Loaded: ':'Selected: ')+node.skill!.slice(0,17)}
      </text>
    </>}
  </g>;
}
function GraphCanvas({graph}: {graph:GraphState}) {
  const [compact,setCompact]=useState(() => window.matchMedia('(max-width: 670px)').matches);
  useEffect(()=>{
    const media=window.matchMedia('(max-width: 670px)');
    const onChange=()=>setCompact(media.matches);
    media.addEventListener('change',onChange);
    return ()=>media.removeEventListener('change',onChange);
  },[]);
  const positioned=positionGraph(graph,compact);
  const canvasHeight = compact ? Math.max(510,...positioned.map(n=>n.y+65)) :
    Math.max(560,...positioned.map(n=>n.y+75));
  const canvasWidth = compact ? 360 : 800;
  const lookup=new Map(positioned.map(n=>[n.id,n]));
  const available=graph.phase!=='empty' && graph.phase!=='unavailable';
  return <div className="matrix-wrap" aria-label="Observed agent execution network">
    {!available ? <div className="matrix-empty">
      <span className="matrix-empty-icon"><AppIcon name="network" size={27}/></span>
      <strong>{graph.phase==='unavailable'?'Execution trace unavailable':'Execution network'}</strong>
      <p>{graph.phase==='unavailable'
        ? 'Saved answers are available, but their execution events are not yet persisted.'
        : 'The network appears when a question starts. Nodes reflect recorded execution events only.'}</p>
    </div> :
    <svg className={'matrix-svg'+(compact?' matrix-svg-mobile':'')+
      (!compact&&canvasHeight>590?' matrix-svg-expanded':'')}
      viewBox={'0 0 '+canvasWidth+' '+canvasHeight} role="img"
      aria-label={positioned.length+' observed execution nodes and '+graph.edges.length+' relationships'}>
      <defs>
        <pattern id="matrix-grid" width="24" height="24" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="#d9e7e4"/>
        </pattern>
        <marker id="matrix-arrow-route" viewBox="0 0 12 12" refX="10" refY="6"
          markerWidth="7" markerHeight="7" orient="auto">
          <path d="M2 2 L10 6 L2 10" fill="none" stroke="#9fb9b5" strokeWidth="1.8"/>
        </marker>
        <marker id="matrix-arrow-handoff" viewBox="0 0 12 12" refX="10" refY="6"
          markerWidth="7" markerHeight="7" orient="auto">
          <path d="M2 2 L10 6 L2 10" fill="none" stroke="#985bdb" strokeWidth="1.8"/>
        </marker>
        <marker id="matrix-arrow-delegate" viewBox="0 0 12 12" refX="10" refY="6"
          markerWidth="7" markerHeight="7" orient="auto">
          <path d="M2 2 L10 6 L2 10" fill="none" stroke="#448bd0" strokeWidth="1.8"/>
        </marker>
      </defs>
      <rect width={canvasWidth} height={canvasHeight} rx="16" fill="#f9fcfb"/>
      <rect width={canvasWidth} height={canvasHeight} rx="16" fill="url(#matrix-grid)"/>
      <circle cx={canvasWidth/2} cy={canvasHeight/2} r={compact?140:205} fill="none" stroke="#e8f3f0" strokeWidth="1.2" strokeDasharray="5 7"/>
      <circle cx={canvasWidth/2} cy={canvasHeight/2} r={compact?84:110} fill="none" stroke="#edf5f2" strokeWidth="1" strokeDasharray="3 8"/>
      {graph.edges.map(e=>{
        const a=lookup.get(e.from),b=lookup.get(e.to);
        if(!a || !b) return null;
        const path=arc(a,b,e.kind);
        return <g key={e.id} data-from={e.from} data-to={e.to}
          className={'matrix-link matrix-link-'+e.kind+' state-'+e.status}>
          <path d={path} className="matrix-edge-shadow"/>
          <path d={path} className="matrix-edge-main"
            markerEnd={'url(#matrix-arrow-'+(
              e.kind==='handoff'?'handoff':e.kind==='delegate'?'delegate':'route')+')'}/>
          {e.kind==='handoff' && <text x={(a.x+b.x)/2} y={(a.y+b.y)/2-11}
            textAnchor="middle" className="matrix-edge-caption">HANDOFF</text>}
          {e.kind==='context' && <text x={(a.x+b.x)/2} y={(a.y+b.y)/2-11}
            textAnchor="middle" className="matrix-edge-caption matrix-edge-caption-context">OFFLINE CONTEXT</text>}
          {e.kind==='delegate' && <text x={(a.x+b.x)/2} y={(a.y+b.y)/2-11}
            textAnchor="middle" className="matrix-edge-caption">DELEGATE</text>}
        </g>;
      })}
      {positioned.map(node=><MatrixNode key={node.id} node={node}/>)}
    </svg>}
    <div className="matrix-legend" aria-hidden="true">
      <span><i className="legend-agent"/>Agent</span>
      <span><i className="legend-tool"/>Tool / MCP</span>
      <span><i className="legend-handoff"/>Handoff</span>
      <span><i className="legend-context"/>Offline context</span>
      <span><i className="legend-active"/>Running</span>
    </div>
  </div>;
}
function EvidenceTable({evidence}: {evidence?:Evidence}) {
  const rows=Array.isArray(evidence?.records)?evidence!.records!.filter(
    (row):row is RecordRow=>row!==null && typeof row==='object' && !Array.isArray(row)
  ):[];
  const sources=(evidence?.contexts || []).flatMap(x=>x.source?[x.source]:[]).slice(0,5);
  if (!rows.length && !sources.length) return null;
  const allKeys=rows.length?Object.keys(rows[0]):[];
  // Put evidence that answers a retail question before incidental identifiers.
  // The dataset values stay unchanged; this only reorders visible columns.
  const firstKeys=['sku','name','location','available','units_sold',
    'net_revenue_vnd','on_hand','reserved','revenue','quantity'];
  const keys=[
    ...firstKeys.filter(key=>allKeys.includes(key)),
    ...allKeys.filter(key=>!firstKeys.includes(key))
  ].slice(0,12);
  return <div className="answer-evidence">
    <div className="evidence-top"><span>Source records</span>
      <span>{rows.length} row{rows.length===1?'':'s'} · {keys.length} column{keys.length===1?'':'s'}</span></div>
    {rows.length>0 && <div className="evidence-table-wrap" tabIndex={0}
      aria-label="Source records table; scroll horizontally for additional columns"><table>
      <thead><tr>{keys.map(key=><th key={key}>{key.replaceAll('_',' ')}</th>)}</tr></thead>
      <tbody>{rows.slice(0,6).map((row,i)=><tr key={i}>{keys.map(key=><td key={key}>
        {typeof row[key]==='number'?Number(row[key]).toLocaleString('en-US'):
          row[key]==null?'—':String(row[key])}</td>)}</tr>)}</tbody>
    </table></div>}
    {allKeys.length>12&&<p className="evidence-small">Showing first 12 of {allKeys.length} evidence columns</p>}
    {rows.length>6&&<p className="evidence-small">Showing 6 of {rows.length} returned rows</p>}
    {sources.length>0&&<div className="source-tags">{sources.map((source,i)=>
      <span key={i}>{source}</span>)}</div>}
  </div>;
}

async function readJson<T>(response: Response): Promise<T> {
  const data=await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(
    typeof data.detail==='string'?data.detail:'Request failed (HTTP '+response.status+')');
  return data as T;
}
async function consumeEvents(response:Response,
  onFrame:(type:string, data:Record<string,unknown>)=>void) {
  if(!response.body) throw new Error('Streaming is not supported by this browser.');
  const reader=response.body.getReader(),decoder=new TextDecoder();
  let buffer='',total=0;
  for(;;){
    const {done,value}=await reader.read();
    if(done) break;
    total+=value.byteLength;
    if(total>2_000_000) throw new Error('Execution event stream exceeded the size limit.');
    buffer+=decoder.decode(value,{stream:true}).replaceAll('\r\n','\n');
    let separator=buffer.indexOf('\n\n');
    while(separator!==-1){
      const frame=buffer.slice(0,separator);
      buffer=buffer.slice(separator+2);
      let event='',data='';
      for(const line of frame.split('\n')){
        if(line.startsWith('event:')) event=line.slice(6).trim();
        if(line.startsWith('data:')) data+=line.slice(5).trim();
      }
      if(event&&data){
        try{
          const parsed=JSON.parse(data) as Record<string,unknown>;
          if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed)) onFrame(event,parsed);
        }catch { /* Invalid transport frame is not trusted. */ }
      }
      separator=buffer.indexOf('\n\n');
    }
  }
}

function App(){
  const [sessions,setSessions]=useState<SessionItem[]>([]);
  const [activeId,setActiveId]=useState('');
  const [messages,setMessages]=useState<Message[]>([]);
  const [question,setQuestion]=useState('');
  const [phase,setPhase]=useState<Phase>('ready');
  const [graph,setGraph]=useState<GraphState>(emptyGraph);
  const [selectedRequestId,setSelectedRequestId]=useState('');
  const [traceTruncated,setTraceTruncated]=useState(false);
  const [error,setError]=useState('');
  const [sidebarOpen,setSidebarOpen]=useState(false);
  const [loading,setLoading]=useState(true);
  const [account,setAccount]=useState<Account|null>(null);
  const [authLoading,setAuthLoading]=useState(true);
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [authError,setAuthError]=useState('');
  const [proposals,setProposals]=useState<ReviewProposal[]>([]);
  const [eligibility,setEligibility]=useState<ReviewEligibility|null>(null);
  const [reviewBusy,setReviewBusy]=useState(false);
  const [reviewNotice,setReviewNotice]=useState('');
  const accountEpoch=useRef(0);
  const messageEnd=useRef<HTMLDivElement>(null);
  const activeIdRef=useRef('');
  const inFlight=useRef(false);
  const requestSerial=useRef(0);

  const busy=phase==='running';

  function secureFetch(url:string, init:RequestInit={}){
    const headers=new Headers(init.headers);
    if(init.method && !['GET','HEAD'].includes(init.method.toUpperCase())){
      if(!account?.csrf_token)throw new Error('Sign in again to continue.');
      headers.set('X-CSRF-Token',account.csrf_token);
    }
    return fetch(url,{...init,headers,credentials:'same-origin'});
  }
  function clearWorkspace(){
    ++requestSerial.current;
    ++accountEpoch.current;
    activeIdRef.current='';
    inFlight.current=false;
    setSessions([]);setActiveId('');setMessages([]);setQuestion('');
    setPhase('ready');setGraph(emptyGraph());setLoading(false);
    setSelectedRequestId('');setTraceTruncated(false);setError('');
    setProposals([]);setEligibility(null);setReviewNotice('');setReviewBusy(false);
    localStorage.removeItem('retailiq-workspace-session');
    localStorage.removeItem('retailiq-workspace-owner');
  }
  async function signIn(){
    setAuthError('');
    try{
      const res=await fetch('/api/auth/login',{
        method:'POST',headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body:JSON.stringify({username:username.trim(),password})
      });
      if(!res.ok)throw new Error('Invalid credentials or login temporarily unavailable.');
      const me=await readJson<Account>(await fetch('/api/auth/me',{cache:'no-store'}));
      // Never restore a conversation remembered for an earlier account.
      if(localStorage.getItem('retailiq-workspace-owner')!==me.user_id){
        localStorage.removeItem('retailiq-workspace-session');
      }
      setPassword('');setAccount(me);setLoading(true);
    }catch(e){setAuthError((e as Error).message)}
  }
  async function signOut(){
    try{
      await readJson<unknown>(await secureFetch('/api/auth/logout',{method:'POST'}));
      clearWorkspace();
      setAccount(null);setAuthError('');setPassword('');
    }catch(e){setError((e as Error).message)}
  }
  async function refreshProposals(){
    if(!account)return;
    const epoch=accountEpoch.current;
    const url=account.role==='manager'?'/api/uc01/proposals':'/api/uc01/my-proposals';
    const result=await readJson<{proposals:ReviewProposal[]}>(await secureFetch(url));
    if(epoch===accountEpoch.current)setProposals(result.proposals??[]);
  }
  async function submitReview(){
    if(!account||account.role!=='analyst'||!activeId||reviewBusy)return;
    const epoch=accountEpoch.current;
    setReviewBusy(true);setReviewNotice('');
    try{
      const value=await readJson<ReviewProposal>(await secureFetch('/api/uc01/proposals',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({session_id:activeId})
      }));
      if(epoch!==accountEpoch.current)return;
      setReviewNotice('Submitted '+value.case_id+' for local Manager review.');
      await refreshProposals();
    }catch(e){
      if(epoch===accountEpoch.current)setReviewNotice((e as Error).message);
    }finally{
      if(epoch===accountEpoch.current)setReviewBusy(false);
    }
  }
  async function decideReview(p:ReviewProposal, decision:'approve'|'reject'){
    if(!account||account.role!=='manager'||reviewBusy)return;
    const epoch=accountEpoch.current;
    setReviewBusy(true);setReviewNotice('');
    try{
      const result=await readJson<ReviewProposal>(await secureFetch(
        '/api/uc01/proposals/'+encodeURIComponent(p.proposal_id)+'/decision',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({decision,expected_version:p.version})
        }));
      if(epoch!==accountEpoch.current)return;
      setReviewNotice(result.status+' · local proposal only; no transfer executed.');
      await refreshProposals();
    }catch(e){
      if(epoch===accountEpoch.current)setReviewNotice((e as Error).message);
    }finally{
      if(epoch===accountEpoch.current)setReviewBusy(false);
    }
  }

  async function refreshSessions(){
    const epoch=accountEpoch.current;
    const list=await readJson<{sessions:SessionItem[]}>(await secureFetch('/api/sessions'));
    if(epoch!==accountEpoch.current)return [];
    setSessions(list.sessions ?? []);
    return list.sessions ?? [];
  }
  async function restoreTrace(sid:string, requestId:string|undefined|null,
                              serial:number) {
    if (!requestId) {
      if (serial===requestSerial.current) {
        setSelectedRequestId('');setTraceTruncated(false);setGraph(unavailableGraph());
      }
      return;
    }
    try {
      const saved=await readJson<StoredTrace>(await secureFetch('/api/sessions/'+
        encodeURIComponent(sid)+'/traces/'+encodeURIComponent(requestId)));
      if(serial!==requestSerial.current)return;
      let next=startGraph(saved.request_id);
      for(const event of saved.events)next=applyExecutionEvent(next,event);
      setGraph(finishGraph(next,saved.status==='complete'));
      setTraceTruncated(saved.truncated);
      setSelectedRequestId(requestId);
    }catch{
      if(serial===requestSerial.current) {
        setGraph(unavailableGraph());
        setSelectedRequestId(requestId);setTraceTruncated(false);
      }
    }
  }
  async function openSession(id:string){
    if(inFlight.current) return;
    const serial=++requestSerial.current;
    setError('');setLoading(true);setGraph(emptyGraph());
    try{
      const session=await readJson<Session>(await secureFetch('/api/sessions/'+encodeURIComponent(id)));
      if(serial!==requestSerial.current) return;
      activeIdRef.current=id;setActiveId(id);
      setMessages(session.messages??[]);
      setGraph(unavailableGraph());
      const latest=[...(session.messages??[])].reverse().find(m=>m.role==='assistant');
      void restoreTrace(id,latest?.request_id,serial);
      localStorage.setItem('retailiq-workspace-session',id);
      setSidebarOpen(false);
      setPhase('ready');
    }catch(e){if(serial===requestSerial.current)setError((e as Error).message)}
    finally{if(serial===requestSerial.current)setLoading(false)}
  }
  function newChat(){
    if(inFlight.current) return;
    ++requestSerial.current;
    activeIdRef.current='';setActiveId('');
    setMessages([]);setGraph(emptyGraph());setPhase('ready');
    setSelectedRequestId('');setTraceTruncated(false);
    setQuestion('');setError('');setLoading(false);setSidebarOpen(false);
    localStorage.removeItem('retailiq-workspace-session');
  }
  async function deleteSession(id:string){
    if(inFlight.current) return;
    const confirmed=window.confirm('Delete this conversation and its saved messages?');
    if(!confirmed) return;
    try{
      await readJson<unknown>(await secureFetch('/api/sessions/'+encodeURIComponent(id),{method:'DELETE'}));
    }catch(e){
      // 204 has no JSON body; errors are handled below for non-2xx.
      setError((e as Error).message);return;
    }
    if(activeIdRef.current===id)newChat();
    await refreshSessions().catch(e=>setError((e as Error).message));
  }
  // Auth must bootstrap before a protected chat, source, or review fetch.
  useEffect(()=>{
    let mounted=true;
    (async()=>{
      try{
        const response=await fetch('/api/auth/me',{cache:'no-store'});
        if(response.ok && mounted){
          const me=await readJson<Account>(response);
          if(localStorage.getItem('retailiq-workspace-owner')!==me.user_id)
            localStorage.removeItem('retailiq-workspace-session');
          setAccount(me);
        }
      }catch{/* No current identity; show the login page. */}
      finally{if(mounted)setAuthLoading(false)}
    })();
    return()=>{mounted=false};
  },[]);
  // Rehydrate only conversations owned by the active account.
  useEffect(()=>{
    if(!account){setLoading(false);return}
    const epoch=accountEpoch.current;
    localStorage.setItem('retailiq-workspace-owner',account.user_id);
    let mounted=true;
    setLoading(true);
    (async()=>{
      try{
        const list=await readJson<{sessions:SessionItem[]}>(await secureFetch('/api/sessions'));
        if(!mounted||epoch!==accountEpoch.current)return;
        setSessions(list.sessions??[]);
        const remembered=localStorage.getItem('retailiq-workspace-session');
        if(remembered && list.sessions?.some(s=>s.id===remembered)){
          const session=await readJson<Session>(await secureFetch('/api/sessions/'+encodeURIComponent(remembered)));
          if(!mounted||epoch!==accountEpoch.current)return;
          activeIdRef.current=remembered;setActiveId(remembered);
          setMessages(session.messages??[]);
          setGraph(unavailableGraph());
          const latest=[...(session.messages??[])].reverse().find(m=>m.role==='assistant');
          void restoreTrace(remembered,latest?.request_id,requestSerial.current);
        }
      }catch(e){if(mounted&&epoch===accountEpoch.current)setError((e as Error).message)}
      finally{if(mounted&&epoch===accountEpoch.current)setLoading(false)}
    })();
    return()=>{mounted=false};
  },[account?.user_id]);
  useEffect(()=>{
    if(!account)return;
    void refreshProposals().catch(e=>setReviewNotice((e as Error).message));
  },[account?.user_id]);
  useEffect(()=>{
    if(account?.role!=='analyst'||!activeId){
      setEligibility(null);return;
    }
    let mounted=true;
    secureFetch('/api/uc01/eligibility?session_id='+encodeURIComponent(activeId))
      .then(r=>readJson<ReviewEligibility>(r))
      .then(value=>{if(mounted)setEligibility(value)})
      .catch(()=>{if(mounted)setEligibility({eligible:false,reason_codes:['SOURCE_UNAVAILABLE']})});
    return()=>{mounted=false};
  },[account?.user_id,activeId,messages.length,phase]);
  useEffect(()=>{messageEnd.current?.scrollIntoView({block:'end',behavior:'auto'})},
    [messages,phase]);

  async function sendQuestion(q:string){
    const content=q.trim();
    if(inFlight.current || content.length<3 || content.length>500)return;
    inFlight.current=true;
    const serial=++requestSerial.current;
    setError('');setQuestion('');setPhase('running');
    setMessages(prev=>[...prev,{role:'user',content}]);
    setGraph(emptyGraph());
    setSelectedRequestId('');setTraceTruncated(false);
    let sessionId=activeIdRef.current;
    try{
      if(!sessionId){
        const created=await readJson<SessionItem>(await secureFetch('/api/sessions',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({title:content.slice(0,78)})
        }));
        if(serial!==requestSerial.current)return;
        sessionId=created.id;activeIdRef.current=sessionId;setActiveId(sessionId);
        localStorage.setItem('retailiq-workspace-session',sessionId);
        await refreshSessions();
      }
      const response=await secureFetch('/ask/stream',{
        method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},
        body:JSON.stringify({question:content,session_id:sessionId})
      });
      if(!response.ok) await readJson<unknown>(response);
      let result:AskResult|null=null,hasDone=false,streamError='';
      await consumeEvents(response,(type,data)=>{
        if(serial!==requestSerial.current)return;
        if(type==='started'){
          const rid=typeof data.request_id==='string'?data.request_id:'';
          setGraph(startGraph(rid));
        }else if(type==='log'){
          setGraph(prev=>applyExecutionEvent(prev,data as ExecutionEvent));
        }else if(type==='result'){
          result=data as AskResult;
        }else if(type==='error'){
          streamError=typeof data.message==='string'?data.message:'Execution failed';
        }else if(type==='done'){hasDone=true}
      });
      if(serial!==requestSerial.current)return;
      if(streamError)throw new Error(streamError);
      if(!hasDone||!result)throw new Error('Stream ended before the answer was received.');
      setGraph(prev=>finishGraph(prev,true));
      setSelectedRequestId((result as AskResult).request_id||'');
      const session=await readJson<Session>(await secureFetch('/api/sessions/'+encodeURIComponent(sessionId)));
      if(serial===requestSerial.current){
        setMessages(session.messages??[]);
        setPhase('complete');
      }
      await refreshSessions();
    }catch(e){
      if(serial!==requestSerial.current)return;
      setGraph(prev=>finishGraph(prev,false));
      setError((e as Error).message);
      setPhase('error');
      if(sessionId) {
        try{
          const saved=await readJson<Session>(await secureFetch('/api/sessions/'+encodeURIComponent(sessionId)));
          if(serial===requestSerial.current)setMessages(saved.messages??[]);
        }catch{/* Preserve the user question if the network is down. */}
      }
    }finally{
      if(serial===requestSerial.current)inFlight.current=false;
    }
  }
  const statusLabel=busy?'Processing':phase==='error'?'Execution failed':
    phase==='complete'?'Complete':'Ready';
  const existingCycle=Boolean(eligibility?.candidate&&proposals.some(p=>
    p.case_id===eligibility.candidate?.case_id &&
    p.cutoff===eligibility.candidate?.cutoff &&
    p.source_sha256===eligibility.candidate?.source_sha256));
  if(authLoading)return <div className="auth-shell"><p>Checking local sign-in…</p></div>;
  if(!account)return <div className="auth-shell">
    <form className="auth-card" onSubmit={e=>{e.preventDefault();void signIn()}}>
      <span className="pane-eyebrow">RETAILIQ · PRIVATE WORKSPACE</span>
      <h1>Sign in</h1>
      <p>Use your local Analyst or Manager account. No default credentials are provided.</p>
      <label htmlFor="auth-username">Username</label>
      <input id="auth-username" autoComplete="username" required maxLength={64}
        value={username} onChange={e=>setUsername(e.target.value)}/>
      <label htmlFor="auth-password">Password</label>
      <input id="auth-password" type="password" autoComplete="current-password" required
        value={password} onChange={e=>setPassword(e.target.value)}/>
      {authError&&<p className="auth-error" role="alert">{authError}</p>}
      <button type="submit" className="auth-submit">Sign in</button>
    </form>
  </div>;
  return <div className="app-shell">
    <header className="app-header">
      <button className="mobile-menu" aria-label="Toggle conversations" onClick={()=>setSidebarOpen(v=>!v)}>
        <AppIcon name="menu"/></button>
      <a className="brand" href="/workspace" aria-label="RetailIQ workspace">
        <span className="brand-mark"><AppIcon name="network" size={21}/></span>
        <span>Retail<span className="brand-iq">IQ</span></span>
      </a>
      <span className="header-divider"/>
      <span className="product-label">Agentic Analytics</span>
      <div className="header-right">
        <span className="header-account">{account.username} · {account.role}</span>
        <button className="auth-logout" onClick={()=>void signOut()}>Sign out</button>
      </div>
    </header>
    <div className="app-body">
      <aside className={'sidebar'+(sidebarOpen?' sidebar-open':'')} aria-label="Conversations">
        <div className="sidebar-title">WORKSPACE</div>
        <button className="new-chat" onClick={newChat} disabled={busy}><AppIcon name="plus" size={16}/> New conversation</button>
        <div className="sidebar-group">CONVERSATIONS <span>{sessions.length}</span></div>
        <div className="session-list">
          {sessions.map(session=><div key={session.id} className={'session-row'+(activeId===session.id?' selected':'')}>
            <button disabled={busy} className="session-select" onClick={()=>openSession(session.id)}
              aria-current={activeId===session.id?'page':undefined}>
              <AppIcon name="chat" size={15}/><span>{session.title||'Conversation'}</span>
            </button>
            <button disabled={busy} className="session-delete" aria-label={'Delete '+session.title}
              title="Delete conversation" onClick={()=>deleteSession(session.id)}>
              <AppIcon name="trash" size={14}/>
            </button>
          </div>)}
          {sessions.length===0 && <p className="sidebar-empty">Your conversations will appear here.</p>}
        </div>
        <div className="sidebar-foot"><span className="sidebar-status-dot"/> API-backed workspace</div>
      </aside>
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="Close sidebar"
        onClick={()=>setSidebarOpen(false)}/>}
      <main className="workspace-main">
        <section className="chat-pane" aria-label="RetailIQ chat">
          <div className="pane-head">
            <div><span className="pane-eyebrow">CONVERSATION</span><h1>Retail assistant</h1></div>
            <span className={'chat-state chat-state-'+phase}><i/>{statusLabel}</span>
          </div>
          <div className="message-scroll" role="log" aria-live="polite" aria-relevant="additions">
            {loading && <div className="chat-centered">Loading conversations…</div>}
            {!loading && messages.length===0 && <div className="chat-onboarding">
              <div className="onboarding-icon"><AppIcon name="network" size={30}/></div>
              <h2>Ask your retail data.</h2>
              <p>Explore sales, stock, orders and product information. Every answer stays connected to its evidence.</p>
              <span className="onboarding-kicker">TRY A QUESTION</span>
              <div className="starter-grid">{IDEAS.map(x=><button key={x.label}
                disabled={busy} onClick={()=>sendQuestion(x.question)}>
                <span>{x.label}</span><span aria-hidden="true">↗</span>
              </button>)}</div>
            </div>}
            {messages.map((msg,i)=><article key={i}
              className={'message message-'+msg.role}>
              <div className="message-identity">{msg.role==='assistant'?
                <span className="assistant-avatar">IQ</span>:<span className="user-avatar">YOU</span>}
                <span>{msg.role==='assistant'?'RetailIQ':'You'}</span>
                {msg.role==='assistant'&&msg.request_id&&<button
                  className={'view-execution'+(selectedRequestId===msg.request_id?' selected':'')}
                  disabled={busy} onClick={()=>{setGraph(unavailableGraph());
                    void restoreTrace(activeIdRef.current,msg.request_id,requestSerial.current)}}
                  aria-label={'Show execution for answer '+(i+1)}>
                  {selectedRequestId===msg.request_id?'Viewing execution':'View execution'}
                </button>}
              </div>
              <div className="message-body">{msg.content}</div>
              {msg.role==='assistant'&&<EvidenceTable evidence={msg.evidence}/>}
            </article>)}
            {busy && <article className="message message-assistant" aria-label="Processing request">
              <div className="message-identity"><span className="assistant-avatar">IQ</span> RetailIQ</div>
              <div className="thinking"><span/><span/><span/> Analyzing your request</div>
            </article>}
            <div ref={messageEnd}/>
          </div>
          <div className="composer-area">
            {error && <div className="error-banner" role="alert">{error}</div>}
            <form className="composer" onSubmit={e=>{e.preventDefault();void sendQuestion(question)}}>
              <textarea aria-label="Ask RetailIQ" placeholder="Ask about revenue, products, inventory…"
                rows={2} maxLength={500} value={question} disabled={busy}
                onChange={e=>setQuestion(e.target.value)}
                onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey && !e.nativeEvent.isComposing){
                  e.preventDefault();void sendQuestion(question)
                }}}/>
              <div className="composer-bottom"><span>Enter to send · Shift+Enter for new line</span>
                <button type="submit" disabled={busy||question.trim().length<3}
                  aria-label="Send message"><AppIcon name="send" size={17}/></button>
              </div>
            </form>
          </div>
        </section>
        <section className="network-pane" aria-label="Agent execution matrix">
          <div className="pane-head network-header">
            <div><span className="pane-eyebrow">OBSERVABILITY</span><h2>Agent network</h2></div>
            <span className={'network-state network-state-'+graph.phase}><i/>{graph.phase==='running'?'Live':
              graph.phase==='complete'?'Completed':graph.phase==='failed'?'Failed':
              graph.phase==='unavailable'?'Not recorded':'Standby'}</span>
          </div>
          <GraphCanvas graph={graph}/>
          <section className="review-section" aria-label="UC-01 local Manager review">
            <div className="review-heading">
              <div><span className="pane-eyebrow">UC-01 · HISTORICAL CASE</span>
                <h3>{account.role==='manager'?'Manager inbox':'Review proposals'}</h3></div>
              <button className="review-refresh" disabled={reviewBusy}
                onClick={()=>void refreshProposals()}>Refresh</button>
            </div>
            <p className="review-boundary">Decisions are local records only. No warehouse transfer, reservation or order update is executed.</p>
            {account.role==='analyst'&&eligibility?.eligible&&
              <div className="review-eligible">
                <p>Verified candidate: <strong>{eligibility.candidate?.snapshot_id}</strong>
                  {' · '+eligibility.candidate?.available_units} historical units available</p>
                {existingCycle?
                  <span className="review-muted">Already submitted. See review status below.</span>:
                  <button className="review-action" disabled={reviewBusy||busy}
                    onClick={()=>void submitReview()}>Submit for Manager review</button>}
              </div>}
            {account.role==='analyst'&&eligibility&&!eligibility.eligible&&activeId&&
              <p className="review-muted">No eligible verified proposal for this conversation.</p>}
            {reviewNotice&&<p className="review-notice" role="status">{reviewNotice}</p>}
            <div className="review-list">
              {proposals.length===0&&<p className="review-muted">No local review items.</p>}
              {proposals.map(p=><article key={p.proposal_id} className="review-item">
                <strong>{p.case_id}</strong>
                <span className="review-status">{p.status.replaceAll('_',' ')}</span>
                <small>Snapshot {p.snapshot_id} · {p.available_units} available / {p.requested_units} requested</small>
                <small>Cutoff {p.cutoff} · source {p.source_sha256.slice(0,12)}</small>
                {account.role==='manager'&&p.status==='PENDING'&&<div className="review-buttons">
                  <button disabled={reviewBusy} onClick={()=>void decideReview(p,'approve')}>Approve locally</button>
                  <button disabled={reviewBusy} onClick={()=>void decideReview(p,'reject')}>Reject locally</button>
                </div>}
              </article>)}
            </div>
          </section>
          {traceTruncated&&<div className="trace-warning" role="status">
            Partial trace: the event capture limit was reached.
          </div>}
          <footer className="network-footer">
            <div className="network-metric"><span>Nodes</span><strong>{graph.nodes.length}</strong></div>
            <div className="network-metric"><span>Connections</span><strong>{graph.edges.length}</strong></div>
            <div className="network-metric"><span>Events</span><strong>{graph.eventsSeen}</strong></div>
            <div className="network-request"><span>Request</span>
              <code>{graph.requestId ? graph.requestId.slice(0,12) : '—'}</code></div>
          </footer>
        </section>
      </main>
    </div>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
