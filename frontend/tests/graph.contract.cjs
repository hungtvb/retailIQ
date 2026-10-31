'use strict';
/** Event projection contract: graph only displays what real SSE metadata proves. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const code = fs.readFileSync(path.join(__dirname,'../src/graph.ts'),'utf8');
const compiled = ts.transpileModule(code, {compilerOptions:{
  target:ts.ScriptTarget.ES2023,module:ts.ModuleKind.CommonJS
}}).outputText;
const moduleContext={exports:{}};
vm.runInNewContext(compiled,{module:moduleContext,exports:moduleContext.exports});
const {emptyGraph,startGraph,applyExecutionEvent,finishGraph,
  unavailableGraph,positionGraph}=moduleContext.exports;

function log(state, event, extra={}){
  return applyExecutionEvent(state,{event,request_id:'req-1',...extra});
}
test('empty matrix contains no fictitious static agent, tool, skill, MCP or links',()=>{
  assert.equal(emptyGraph().nodes.length,0);
  assert.equal(emptyGraph().edges.length,0);
  assert.equal(unavailableGraph().nodes.length,0);
});
test('real offline routing and tool call construct visible nodes and 2D positions',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'sales_agent'});
  state=log(state,'skill.selected',{skill:'sales_analysis'});
  state=log(state,'tool.offline_lookup.started',
    {agent:'sales_agent',tool:'reviewed_sql_or_lexical'});
  state=log(state,'tool.offline_lookup.completed',
    {agent:'sales_agent',tool:'reviewed_sql_or_lexical'});
  assert.equal(state.nodes.filter(n=>n.kind==='agent').length,1);
  assert.equal(state.nodes.find(n=>n.kind==='agent').skill,'sales analysis');
  assert.equal(state.nodes.find(n=>n.kind==='tool').status,'completed');
  assert.equal(state.nodes.filter(n=>n.kind==='mcp').length,0);
  assert.equal(state.edges.filter(e=>e.kind==='handoff').length,0);
  state=finishGraph(state,true);
  assert.equal(state.nodes.find(n=>n.kind==='agent').status,'observed');
  assert.equal(state.edges.filter(e=>e.kind==='result').length,0,
    'No fabricated response dependency without a result agent event');
  const plotted=positionGraph(state);
  assert.ok(new Set(plotted.map(n=>n.x)).size >=2, 'Nodes collapsed into one vertical lane');
  assert.ok(new Set(plotted.map(n=>n.y)).size >=3, 'Graph has no two-dimensional spread');
});
test('handoff, child delegation and MCP require explicit event metadata',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'sales_agent'});
  state=log(state,'agent.handoff',
    {previous_agent:'sales_agent',target_agent:'inventory_agent',execution_mode:'full'});
  state=log(state,'agent.subagent.started',
    {agent:'inventory_agent',subagent:'stock_verifier'});
  state=log(state,'mcp.tool.started',
    {agent:'inventory_agent',tool:'inventory_lookup'});
  assert.equal(state.edges.filter(e=>e.kind==='handoff').length,1);
  assert.equal(state.edges.filter(e=>e.kind==='delegate').length,1);
  assert.equal(state.edges.filter(e=>e.kind==='mcp').length,1);
  assert.equal(state.nodes.filter(n=>n.kind==='subagent').length,1);
  assert.equal(state.nodes.filter(n=>n.kind==='mcp').length,1);
  state=log(state,'mcp.tool.completed',
    {agent:'inventory_agent',tool:'inventory_lookup'});
  assert.equal(state.nodes.find(n=>n.kind==='mcp').status,'completed');
});
test('cross-request and partial handoff events do not create false topology',()=>{
  let state=startGraph('req-1');
  const old=applyExecutionEvent(state,{
    event:'agent.handoff',request_id:'other',previous_agent:'sales_agent',
    target_agent:'inventory_agent'
  });
  assert.equal(old.nodes.length,1);
  assert.equal(old.eventsSeen,0);
  state=log(state,'agent.handoff',{previous_agent:'sales_agent'});
  assert.equal(state.nodes.length,1);
  assert.equal(state.edges.length,0);
  state=log(state,'skill.selected',{skill:'not_executed'});
  assert.equal(state.nodes.length,1);
  assert.equal(state.nodes[0].skill,undefined);
});

test('role-based layout never collides for handoff, MCP, subagents or multiple tools',()=>{
  const examples=[
    {
      nodes:[
        {id:'request',kind:'request'},
        {id:'agent:sales',kind:'agent',skill:'sales_analysis'},
        {id:'agent:inventory',kind:'agent',skill:'inventory_check'},
        {id:'tool:sql',kind:'tool'},
        {id:'answer',kind:'output'}
      ]
    },
    {
      nodes:[
        {id:'request',kind:'request'},
        ...Array.from({length:6},(_,i)=>({id:'agent:'+i,kind:'agent',skill:'stock_analysis'})),
        ...Array.from({length:3},(_,i)=>({id:'subagent:'+i,kind:'subagent'})),
        ...Array.from({length:8},(_,i)=>({id:'tool:'+i,kind:i%2?'mcp':'tool'})),
        {id:'answer',kind:'output'}
      ]
    }
  ];
  for(const input of examples)for(const compact of [false,true]){
    const nodes=positionGraph(input,compact);
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j];
      const heightA=a.skill?126:102,heightB=b.skill?126:102;
      const touchingX=Math.abs(a.x-b.x)<180;
      const touchingY=Math.abs(a.y-b.y)<(heightA+heightB)/2;
      assert.ok(!(touchingX&&touchingY),
        (compact?'mobile':'desktop')+' overlap: '+a.id+' '+b.id);
    }
  }
});
test('handoff never implies completion of the sending agent',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'sales_agent'});
  state=log(state,'agent.handoff',{
    previous_agent:'sales_agent',target_agent:'inventory_agent',execution_mode:'full'});
  assert.equal(state.nodes.find(n=>n.id==='agent:sales_agent').status,'observed');
  assert.equal(state.nodes.find(n=>n.id==='agent:inventory_agent').status,'running');
  state=log(state,'chat.turn_result',{agent:'inventory_agent'});
  state=finishGraph(state,true);
  assert.equal(state.nodes.find(n=>n.id==='agent:sales_agent').status,'observed');
  const resultEdge=state.edges.find(n=>n.kind==='result');
  assert.equal(resultEdge.status,'observed');
  assert.equal(resultEdge.from,'agent:inventory_agent',
    'The final result must point to the actual responsible agent, not the last inserted node');
  assert.equal(resultEdge.to,'answer');
});

test('offline legacy handoff telemetry is context, never autonomous handoff',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'inventory_agent',execution_mode:'offline'});
  state=log(state,'agent.handoff',{
    previous_agent:'sales_agent',target_agent:'inventory_agent',
    execution_mode:'offline'
  });
  assert.equal(state.edges.filter(e=>e.kind==='handoff').length,0);
  assert.equal(state.edges.filter(e=>e.kind==='context').length,1);
  assert.equal(state.nodes.find(n=>n.id==='agent:sales_agent').status,'observed');
});
test('real MCP tool span creates explicitly named server, MCP tool and attributable edges',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'inventory_agent',execution_mode:'offline'});
  state=log(state,'skill.selected',{
    skill:'inventory_availability',agent:'inventory_agent'
  });
  state=log(state,'mcp.tool.started',{
    agent:'inventory_agent',tool:'inventory_lookup',
    mcp_server:'retailiq',execution_mode:'full'
  });
  assert.equal(state.nodes.filter(n=>n.kind==='mcp-server').length,1);
  assert.equal(state.nodes.filter(n=>n.kind==='mcp').length,1);
  assert.equal(state.nodes.find(n=>n.kind==='mcp').status,'running');
  assert.ok(state.edges.some(e=>e.from==='agent:inventory_agent' &&
    e.to==='mcp-server:retailiq'));
  assert.ok(state.edges.some(e=>e.from==='mcp-server:retailiq' &&
    e.to==='mcp:inventory_lookup'));
  state=log(state,'mcp.tool.completed',{
    agent:'inventory_agent',tool:'inventory_lookup',
    mcp_server:'retailiq',execution_mode:'full'
  });
  assert.equal(state.nodes.find(n=>n.kind==='mcp').status,'completed');
});
test('skill selected and skill content loaded are different observable states',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'product_agent'});
  state=log(state,'skill.selected',{agent:'product_agent',skill:'product_grounding'});
  assert.equal(state.nodes.find(n=>n.kind==='agent').skillState,'selected');
  state=log(state,'skill.loaded',{agent:'product_agent',skill:'product_grounding'});
  assert.equal(state.nodes.find(n=>n.kind==='agent').skillState,'loaded');
});
test('observed subagent owns tool call instead of duplicating child as top-level agent',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'retail_supervisor'});
  state=log(state,'agent.subagent.started',{
    agent:'retail_supervisor',subagent:'sales_agent',execution_mode:'full'
  });
  state=log(state,'tool.sql.started',{agent:'sales_agent',tool:'sales_analytics'});
  assert.ok(state.edges.some(e=>e.from==='subagent:sales_agent' &&
    e.to==='tool:sales_analytics'));
  assert.equal(state.nodes.filter(n=>n.id==='agent:sales_agent').length,0);
});
