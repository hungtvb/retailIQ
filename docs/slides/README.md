# RetailIQ Week 1 Presentation

The checklist-aligned deck is [`RetailIQ_Flezi_Week1_Checklist_Aligned.pptx`](RetailIQ_Flezi_Week1_Checklist_Aligned.pptx). It covers the product problem, Week 1 architecture, data/KPI definitions, demo questions, FDE and harness patterns, cost/ROI assumptions, testing, risks, and open verification gates.

## Build the deck

Run from the repository root:

```bash
python scripts/build_slides.py
python scripts/build_slides_checklist.py
```

The first command creates `RetailIQ_Flezi_Week1_Demo.pptx`; the second adds the official-checklist slides and creates the deck linked above. Both files are written to this folder.

## Presentation notes

**Deck content maintenance:** The checked-in PPTX is a previously generated snapshot; updating Markdown business documentation **does not automatically modify slides**. Before presentation, refresh/regenerate and visually review the deck against the new [Faster · Easier · Reliable business scope](../21_INVENTORY_SALES_BUSINESS_SCOPE.md). Do not claim the PPTX already reflects the revised wording until it has been rebuilt and checked.

- Frame the problem as **human-driven navigation/filtering across existing tools**, not “the retailer has no tools”; RetailIQ targets easier and potentially faster natural-language task completion with verified answers.
- Replenishment Review is the featured *cross-source pattern demo*, not the overall business objective.
- Reserve most of the demo for four required data questions plus meaningful Chain/Agent/Router/Subagent/Handoff/Skill/Custom Workflow evidence.
- Explain that the retailer and transaction data are synthetic.
- Treat the 3.75-month payback as an illustrative estimate, **not** a measured business result; Faster/Easier impact and ease scores are not yet measured.
- Main CI on code commit `224fcb7` passed 276 Python and 12 Node tests, plus mocked graph and localhost E2E checks; see [test evidence](../06_Test_Evidence.md). Full-mode LLM/Chroma execution, RAGAS scores, and LangSmith traces remain unverified.
- Do not present local logs or mocked graph tests as live LangSmith/provider evidence.

For setup and the demo sequence, see [`../03_Week1_Demo_Runbook.md`](../03_Week1_Demo_Runbook.md) and [`../09_Week1_Checklist_and_Evidence.md`](../09_Week1_Checklist_and_Evidence.md).
