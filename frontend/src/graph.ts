/**
 * A projection of observed backend events into a display-only network.
 * Do not infer MCP usage, skill execution, or subagents from architecture.
 * No graph framework, random positions, or synthetic execution events.
 */
export type NodeKind = 'request' | 'agent' | 'subagent' | 'tool' | 'mcp' | 'mcp-server' | 'output';
export type NodeStatus = 'running' | 'completed' | 'failed' | 'pending' | 'observed';
export type EdgeKind = 'route' | 'call' | 'handoff' | 'context' | 'delegate' | 'result' | 'mcp';
export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  status: NodeStatus;
  skill?: string;
  skillState?: 'selected' | 'loaded';
}
export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  kind: EdgeKind;
  status: NodeStatus;
}
export interface GraphState {
  requestId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  eventsSeen: number;
  phase: 'empty' | 'running' | 'complete' | 'failed' | 'unavailable';
}
export interface ExecutionEvent {
  event?: string;
  request_id?: string;
  agent?: string;
  previous_agent?: string;
  target_agent?: string;
  tool?: string;
  mcp_server?: string;
  skill?: string;
  subagent?: string;
  status?: string;
  execution_mode?: string;
  level?: string;
}

export const emptyGraph = (): GraphState => ({
  requestId: '', nodes: [], edges: [], eventsSeen: 0, phase: 'empty'
});
export function startGraph(requestId: string): GraphState {
  return { requestId, nodes: [{
    id: 'request', label: 'User request', kind: 'request', status: 'running'
  }], edges: [], eventsSeen: 0, phase: 'running' };
}

const concise = (value: unknown, max = 42) =>
  typeof value === 'string' ? value.replaceAll('_', ' ').slice(0, max) : '';
function upsertNode(nodes: GraphNode[], next: GraphNode): GraphNode[] {
  const index = nodes.findIndex(node => node.id === next.id);
  if (index < 0) return [...nodes, next].slice(0, 28);
  return nodes.map((node, i) => i === index ? {
    ...node, ...next, skill: next.skill ?? node.skill,
    skillState: next.skillState ?? node.skillState
  } : node);
}
function upsertEdge(edges: GraphEdge[], edge: GraphEdge): GraphEdge[] {
  if (edges.some(e => e.id === edge.id)) return edges.map(e => e.id === edge.id ? edge : e);
  return [...edges, edge].slice(0, 44);
}
function edge(from: string, to: string, kind: EdgeKind, status: NodeStatus): GraphEdge {
  return { id: kind + ':' + from + ':' + to, from, to, kind, status };
}
function completed(label: string, kind: NodeKind, id: string, status: NodeStatus): GraphNode {
  return { id, label, kind, status };
}

/** Event contract currently supported by existing RetailIQ offline/full streams. */
export function applyExecutionEvent(state: GraphState, event: ExecutionEvent): GraphState {
  if (state.phase !== 'running' || !event.event) return state;
  if (event.request_id && state.requestId && event.request_id !== state.requestId) return state;
  let nodes = state.nodes, edges = state.edges;
  const name = event.event;
  const failed = name.endsWith('.failed') || event.status === 'failed' || event.level === 'ERROR';
  const status: NodeStatus = failed ? 'failed' :
    name.endsWith('.completed') ? 'completed' : 'running';
  const agentId = event.agent ? 'agent:' + event.agent : '';
  const existingAgent = agentId && nodes.some(n => n.id === agentId);
  const activeAgent = nodes.findLast(n => n.kind === 'agent' && n.status === 'running');

  if (name === 'agent.routed' && agentId) {
    nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', agentId, 'running'));
    edges = upsertEdge(edges, edge('request', agentId, 'route', 'completed'));
  } else if (name === 'agent.handoff' && event.previous_agent && event.target_agent) {
    const from = 'agent:' + event.previous_agent;
    const to = 'agent:' + event.target_agent;
    // Handoff proves transfer, NOT completion of the source agent.
    const source = nodes.find(n => n.id === from);
    nodes = upsertNode(nodes, completed(concise(event.previous_agent), 'agent', from,
      source?.status === 'completed' || source?.status === 'failed' ?
        source.status : 'observed'));
    nodes = upsertNode(nodes, completed(concise(event.target_agent), 'agent', to, 'running'));
    // Offline mode's legacy handoff event is a deterministic context change.
    // Only the full LangGraph Command transfer is an actual handoff.
    edges = upsertEdge(edges, edge(from, to,
      event.execution_mode === 'full' ? 'handoff' : 'context','observed'));
  } else if (name.startsWith('agent.subagent.') && event.agent && event.subagent) {
    const from = 'agent:' + event.agent;
    const to = 'subagent:' + event.subagent;
    nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', from, 'running'));
    nodes = upsertNode(nodes, completed(concise(event.subagent), 'subagent', to, status));
    edges = upsertEdge(edges, edge(from, to, 'delegate', status));
  } else if (name === 'chat.turn_result' && event.agent) {
    // The backend identifies the responsible final agent. This is the
    // only evidence-backed association between execution and the answer.
    const owner = nodes.find(n => n.id === agentId);
    nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', agentId,
      owner?.status === 'completed' || owner?.status === 'failed' ?
        owner.status : 'observed'));
    edges = upsertEdge(edges, edge(agentId, 'answer', 'result', 'observed'));
  } else if ((name === 'skill.selected' || name === 'skill.loaded') && event.skill) {
    // A skill file was loaded or a routing policy selected it. Neither event
    // proves that an LLM followed the skill instructions.
    const owner = (event.agent && nodes.find(n => n.id === 'subagent:' + event.agent)) ||
      (event.agent && nodes.find(n => n.id === 'agent:' + event.agent)) ||
      (!event.agent ? activeAgent || nodes.findLast(n => n.kind === 'agent') : undefined);
    if (owner) nodes = nodes.map(n => n.id === owner.id ? {
      ...n, skill: concise(event.skill),
      skillState: name === 'skill.loaded' ? 'loaded' : (n.skillState ?? 'selected')
    } : n);
  } else if ((name.startsWith('tool.') || name.startsWith('mcp.tool.')) && event.tool) {
    const isMcp = name.startsWith('mcp.');
    // A tool called inside an observed subagent belongs to that subagent,
    // not to an invented second top-level agent.
    const childId = event.agent ? 'subagent:' + event.agent : '';
    const hasChild = childId && nodes.some(n => n.id === childId);
    const from = hasChild ? childId : (agentId || activeAgent?.id);
    const id = (isMcp ? 'mcp:' : 'tool:') + event.tool;
    if (agentId && !existingAgent && !hasChild) {
      nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', agentId, 'running'));
      edges = upsertEdge(edges, edge('request', agentId, 'route', 'observed'));
    }
    if (isMcp && event.mcp_server) {
      const serverId = 'mcp-server:' + event.mcp_server;
      nodes = upsertNode(nodes, completed(concise(event.mcp_server),
        'mcp-server', serverId, status));
      if (from) edges = upsertEdge(edges,edge(from,serverId,'mcp','observed'));
      edges = upsertEdge(edges,edge(serverId,id,'mcp',status));
    } else if (from) {
      edges = upsertEdge(edges, edge(from,id,isMcp?'mcp':'call',status));
    }
    nodes = upsertNode(nodes, completed(concise(event.tool), isMcp ? 'mcp' : 'tool', id, status));
  } else if (name.startsWith('agent.') && (name.endsWith('.started') ||
    name.endsWith('.completed') || name.endsWith('.failed')) && event.agent) {
    nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', agentId, status));
    if (!edges.some(e => e.to === agentId)) edges = upsertEdge(edges,
      edge('request', agentId, 'route', 'completed'));
  }
  return { ...state, nodes, edges, eventsSeen: state.eventsSeen + 1 };
}
export function finishGraph(state: GraphState, ok: boolean): GraphState {
  if (state.phase !== 'running') return state;
  let nodes = state.nodes, edges = state.edges;
  // A delivered response does not prove every intermediate node completed.
  // Without an explicit *.completed event, mark that step as observed.
  nodes = nodes.map(n => n.status === 'running' && n.kind !== 'request' ?
    { ...n, status: 'observed' as const } : n);
  edges = edges.map(e => e.status === 'running' ?
    { ...e, status: 'observed' as const } : e);
  nodes = upsertNode(nodes, {id:'request',label:'User request',kind:'request',
    status:ok?'completed':'failed'});
  if (ok) {
    nodes = upsertNode(nodes, {id:'answer',label:'Response delivered',
      kind:'output',status:'completed'});
    // No invented dependency: without an observed chat.turn_result agent,
    // output deliberately has no incoming edge.
  }
  return { ...state, nodes, edges, phase:ok?'complete':'failed' };
}
export function unavailableGraph(): GraphState {
  return {...emptyGraph(), phase:'unavailable'};
}

export interface PositionedNode extends GraphNode { x: number; y: number; }
export function positionGraph(graph: GraphState, compact = false): PositionedNode[] {
  const agents = graph.nodes.filter(n => n.kind === 'agent');
  const subagents = graph.nodes.filter(n => n.kind === 'subagent');
  const tools = graph.nodes.filter(n => n.kind === 'tool' || n.kind === 'mcp' || n.kind === 'mcp-server');
  const positions = new Map<string, [number, number]>();
  const onePath = agents.length <= 1 && tools.length <= 1 && subagents.length === 0;
  const hasOutput = graph.nodes.some(n => n.id === 'answer');

  if (compact) {
    // At 390px, two 180px-wide cards cannot share a row without collision.
    // A single chain can use a legible zig-zag; complex graphs distribute
    // roles in consecutive rows instead of scaling cards down to unreadable.
    const left = 95, right = 265;
    if (onePath) {
      positions.set('request', [left,82]);
      if (agents[0]) positions.set(agents[0].id,[right,198]);
      if (tools[0]) positions.set(tools[0].id,[left,350]);
      if (hasOutput) positions.set('answer',[right,490]);
    } else {
      positions.set('request',[180,80]);
      let nextY = 215, index = 0;
      for (const n of [...agents,...subagents,...tools]) {
        positions.set(n.id,[index%2===0?left:right,nextY]);
        nextY+=155;
        index++;
      }
      if(hasOutput) positions.set('answer',[180,nextY+8]);
    }
    return graph.nodes.map(n=>({...n,x:positions.get(n.id)?.[0]??180,
      y:positions.get(n.id)?.[1]??190}));
  }

  if (onePath) {
    // Balanced quadrants without inventing extra execution branches.
    positions.set('request', [200,105]);
    if (agents[0]) positions.set(agents[0].id,[595,190]);
    if (tools[0]) positions.set(tools[0].id,[200,365]);
    if (hasOutput) positions.set('answer',[595,480]);
  } else {
    positions.set('request', [400,75]);
    const arrange = (items: GraphNode[], y: number): number => {
      if (!items.length) return y;
      const slots = items.length===1?[400]:items.length===2?[205,595]:[165,400,635];
      items.forEach((item,i)=>{
        const row=Math.floor(i/3),col=i%3;
        positions.set(item.id,[slots.length===3?slots[col]:slots[i]??slots[0],
          y+row*145]);
      });
      return y+Math.ceil(items.length/3)*145;
    };
    let next = arrange(agents,205);
    next = arrange(subagents,next);
    next = arrange(tools,next);
    if (hasOutput) positions.set('answer',[400,next+3]);
  }
  return graph.nodes.map(n => ({...n,x:positions.get(n.id)?.[0]??400,
    y:positions.get(n.id)?.[1]??300}));
}
