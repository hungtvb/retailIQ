# Historical documentation archive

This directory contains **dated records**, not a second source of current requirements, implementation status or quality evidence. For current guidance, start at the [documentation index](../README.md).

## Preserved records

- [2026-10-30 legacy snapshot](2026-10-30/legacy/): **34 original Markdown files** from the former flat `docs/` layout, preserved byte-for-byte. Internal links in these files may retain old relative paths.
- [2026-10-31 high-level assessment](2026-10-31/RETAILIQ_HIGH_LEVEL_OVERVIEW.md): dated project overview and gap review, superseded by canonical Product, Design and capability-status documents.
- [2026-10-31 workflow prototype](2026-10-31/26_FOUR_WEEK_GRAPH_WORKFLOWS.md): original local scenario-graph proposal and validation notes; not the current overall architecture.
- [2026-10-31 Workspace first slice](2026-10-31/28_PRODUCT_WORKSPACE_V1.md): original UI decisions and staged acceptance notes; code and current [Design](../DESIGN.md) are authoritative.
- [Course evidence and handout assets](../weeks/week-01/): original rubric, learning notes, runbook, dated execution evidence and five preserved non-Markdown artifacts (including PPTX/DOCX, RAGAS result and screenshots). They remain **course history**, not evidence for the current revision.

## Current authoritative documents

| Topic | Use this current source |
|---|---|
| Business problem, users, product scope | [Product](../PROJECT.md) |
| Required capabilities and success criteria | [Requirements](../REQUIREMENTS.md) |
| Course milestone mapping and historical timeline | [Roadmap](../COURSE_PLAN.md) |
| System responsibility and technology decisions | [Architecture](../ARCHITECTURE.md) and [Basic/Detail Design](../DESIGN.md) |
| Schema, KPI semantics, HTTP and MCP contracts | [Data & API](../DATA_API.md) |
| Scenario definitions and executable checks | [Testing & Scenario Acceptance](../27_BEHAVIORAL_ACCEPTANCE_MATRIX.md) |
| Acceptance status and unresolved evidence | [Capability Ledger](../29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md) |

**Interpretation rule:** dates and execution modes are part of each historical claim. Older “PASS” or “NOT VERIFIED” labels are not automatically true for a newer commit. Preserve relevant source SHA and execution artifacts before reporting current acceptance.
