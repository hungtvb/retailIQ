/**
 * A projection of observed backend events into a display-only network.
 * Do not infer MCP usage, skill execution, or subagents from architecture.
 * No graph framework, random positions, or synthetic execution events.
 */
export type NodeKind = 'request' | 'agent' | 'subagent' | 'tool' | 'mcp' | 'output';
export type NodeStatus = 'running' | 'completed' | 'failed' | 'pending' | 'observed';
export type EdgeKind = 'route' | 'call' | 'handoff' | 'delegate' | 'result' | 'mcp';
export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  status: NodeStatus;
  skill?: string;
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
    ...node, ...next, skill: next.skill ?? node.skill
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
    nodes = upsertNode(nodes, completed(concise(event.previous_agent), 'agent', from, 'completed'));
    nodes = upsertNode(nodes, completed(concise(event.target_agent), 'agent', to, 'running'));
    edges = upsertEdge(edges, edge(from, to, 'handoff', 'completed'));
  } else if (name.startsWith('agent.subagent.') && event.agent && event.subagent) {
    const from = 'agent:' + event.agent;
    const to = 'subagent:' + event.subagent;
    nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', from, 'running'));
    nodes = upsertNode(nodes, completed(concise(event.subagent), 'subagent', to, status));
    edges = upsertEdge(edges, edge(from, to, 'delegate', status));
  } else if (name === 'skill.selected' && event.skill) {
    // Selection proves intended skill, not the execution of that skill.
    const owner = activeAgent || nodes.findLast(n => n.kind === 'agent');
    if (owner) nodes = nodes.map(n => n.id === owner.id ?
      { ...n, skill: concise(event.skill) } : n);
  } else if ((name.startsWith('tool.') || name.startsWith('mcp.tool.')) && event.tool) {
    const isMcp = name.startsWith('mcp.');
    const from = agentId || activeAgent?.id;
    const id = (isMcp ? 'mcp:' : 'tool:') + event.tool;
    if (agentId && !existingAgent) {
      nodes = upsertNode(nodes, completed(concise(event.agent), 'agent', agentId, 'running'));
      edges = upsertEdge(edges, edge('request', agentId, 'route', 'completed'));
    }
    nodes = upsertNode(nodes, completed(concise(event.tool), isMcp ? 'mcp' : 'tool', id, status));
    if (from) edges = upsertEdge(edges, edge(from, id, isMcp ? 'mcp' : 'call', status));
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
  const terminal = nodes.findLast(n => n.kind === 'tool' || n.kind === 'mcp' ||
    n.kind === 'agent' || n.kind === 'subagent');
  if (ok) {
    nodes = upsertNode(nodes, {id:'answer',label:'Response delivered',
      kind:'output',status:'completed'});
    if (terminal) edges = upsertEdge(edges, edge(terminal.id,'answer','result','completed'));
    else edges = upsertEdge(edges,edge('request','answer','result','completed'));
  }
  return { ...state, nodes, edges, phase:ok?'complete':'failed' };
}
export function unavailableGraph(): GraphState {
  return {...emptyGraph(), phase:'unavailable'};
}

export interface PositionedNode extends GraphNode { x: number; y: number; }
export function positionGraph(graph: GraphState): PositionedNode[] {
  const agents = graph.nodes.filter(n => n.kind === 'agent');
  const subagents = graph.nodes.filter(n => n.kind === 'subagent');
  const tools = graph.nodes.filter(n => n.kind === 'tool' || n.kind === 'mcp');
  const positions = new Map<string, [number, number]>();
  const isSingleLane = agents.length <= 1 && tools.length <= 1 && subagents.length === 0;
  // A lone execution path still occupies a readable 2D network, rather than
  // shrinking into a vertical column. This is spatial arrangement, not a
  // fabricated branch, event or link.
  if (isSingleLane) {
    positions.set('request', [200, 115]);
    if (agents[0]) positions.set(agents[0].id, [595, 190]);
    if (tools[0]) positions.set(tools[0].id, [200, 370]);
    if (graph.nodes.some(n=>n.id==='answer')) positions.set('answer', [595, 470]);
  } else {
    positions.set('request', [400, 78]);
    const agentSlots: Array<[number,number]> = agents.length === 2
      ? [[195,210],[605,210]]
      : [[170,185],[625,185],[400,325],[160,345],[635,345],[400,390]];
    agents.forEach((n,i) => positions.set(n.id,agentSlots[i] ?? [
      175+(i%4)*155, 345+Math.floor(i/4)*70
    ]));
    subagents.forEach((n,i) => positions.set(n.id,[
      235 + (i%3)*175, 355 + Math.floor(i/3)*70
    ]));
    tools.forEach((n,i) => positions.set(n.id, tools.length === 1
      ? [400,432] : [175 + (i%4)*150, 418+Math.floor(i/4)*72]));
    if (graph.nodes.some(n=>n.id==='answer')) positions.set('answer',[400,510]);
  }
  return graph.nodes.map(n => ({ ...n, x: positions.get(n.id)?.[0] ?? 400,
    y: positions.get(n.id)?.[1] ?? 300 }));
}
