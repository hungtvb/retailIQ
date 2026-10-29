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
  const plotted=positionGraph(state);
  assert.ok(new Set(plotted.map(n=>n.x)).size >=2, 'Nodes collapsed into one vertical lane');
  assert.ok(new Set(plotted.map(n=>n.y)).size >=3, 'Graph has no two-dimensional spread');
});
test('handoff, child delegation and MCP require explicit event metadata',()=>{
  let state=startGraph('req-1');
  state=log(state,'agent.routed',{agent:'sales_agent'});
  state=log(state,'agent.handoff',
    {previous_agent:'sales_agent',target_agent:'inventory_agent'});
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
