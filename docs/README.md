# RetailIQ — Documentation index

**One source of truth per concern.** The original flat documentation was consolidated on 2026-10-30. Prior Markdown snapshots and binary evidence remain retrievable through [archive](archive/README.md).

| Question | Canonical document |
|---|---|
| Read the complete high-level overview and post-merge assessment? | [RetailIQ High-Level Overview](RETAILIQ_HIGH_LEVEL_OVERVIEW.md) |
| Why RetailIQ, who uses it, and what value? | [PROJECT — business problem](PROJECT.md) |
| Four-week required scope, roles and timeline? | [COURSE_PLAN — course baseline](COURSE_PLAN.md) |
| How does the current application work? | [ARCHITECTURE — runtime design](ARCHITECTURE.md) |
| Trusted SQL/KPI/data and HTTP contracts? | [DATA_API — API and semantics](DATA_API.md) |
| Week 1 official 3+4 checkpoints? | [Week 1 README](weeks/week-01/README.md) |
| FDE/harness patterns, cost and ROI assumptions? | [Week 1 DESIGN](weeks/week-01/DESIGN.md) |
| Setup, demo, dependencies and troubleshooting? | [Week 1 RUNBOOK](weeks/week-01/RUNBOOK.md) |
| Actual dated test/evaluation/trace outcomes? | [Week 1 EVIDENCE](weeks/week-01/EVIDENCE.md) |

## Roadmap ownership

**Week 1:** SQL/RAG/graph local baseline; live provider acceptance must be checked per commit. **Week 2:** local freshness/semantic/MCP/memory/retrieval slices exist, with live reliability gaps. **Week 3:** approval, scope and alerts are primarily simulations; real security/Langfuse/DeepEval are open. **Week 4:** five-role deterministic workflow exists, but five autonomous agents and secure approval remain open. See the [capability ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md); create new week folders only when needed.

## Documentation governance

1. Project-wide business, course, architecture and data contracts each have one canonical file.
2. A week owns its own scope/checklist, design, runbook and evidence; a technical fix should update these or its code/tests, **not create numbered standalone notes**.
3. Every test PASS is scoped to a date, commit SHA and execution mode. Old audit snapshots are history, not current status.
4. Do not modify original course requirements to fit the implementation; do not claim Week 2–4 planned features are finished.
5. Keep snapshots in the [archive](archive/README.md); do not edit them to retroactively change historical outcomes.
6. Run `python -m scripts.check_docs_links` (also enforced by CI) whenever documentation paths change; exclude immutable historical snapshots.

[Root quick start](../README.md) · [Week 1 runbook](weeks/week-01/RUNBOOK.md).
