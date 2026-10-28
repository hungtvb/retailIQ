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

- Reserve most of the demo for the four use cases and their evidence.
- Explain that the retailer and transaction data are synthetic.
- Treat the 3.75-month payback as an illustrative estimate, not a measured business result.
- Main CI on code commit `224fcb7` passed 276 Python and 12 Node tests, plus mocked graph and localhost E2E checks; see [test evidence](../06_Test_Evidence.md). Full-mode LLM/Chroma execution, RAGAS scores, and LangSmith traces remain unverified.
- Do not present local logs or mocked graph tests as live LangSmith/provider evidence.

For setup and the demo sequence, see [`../03_Week1_Demo_Runbook.md`](../03_Week1_Demo_Runbook.md) and [`../09_Week1_Checklist_and_Evidence.md`](../09_Week1_Checklist_and_Evidence.md).
