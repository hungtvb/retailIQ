# RetailIQ Week 1 Web UI — DESIGN 7.md application

## Reference

User-provided **Pirsch Analytics — Style Reference** (`DESIGN 7.md`), applied as a visual system rather than copied as a marketing website. Kept the two existing functional areas: AI Assistant and Cost & ROI.

## Design tokens

| Token | Value | Usage |
| --- | --- | --- |
| Cream Paper | `#f8f5ed` | canvas and cards |
| Ink | `#000000` | headings, icons, card borders |
| Graphite | `#707070` | secondary text, captions |
| Sunshine | `#ffda6e` | main Ask / Recalculate actions and a small headline accent |
| Mint | `#6ece9d` | status dots, positive state |
| Type | `DM Sans` (online), `Inter` fallback | single-family editorial type |
| Card radius | 24px | all major cards |
| Border | 1px solid black | cards, navigation, fields |
| Spacing base | 8px | sections and card gaps |

No photographic assets, gradients, drop shadows, or secondary body fonts. The page uses only CSS/SVG icons and existing business data.

## Implemented components

- Minimal header with monochrome logo, curriculum label and local-demo indicator.
- Centered editorial hero and numbered section badge.
- Tabs for Assistant and Cost & ROI with `aria-selected`, keyboard arrow navigation, and no remount of business state.
- Outlined question bar, single yellow submit CTA, and reusable question chips.
- Response and execution evidence cards with expandable, preformatted source records.
- ROI assumptions form, forecast summary cards, sensitivity bars and explicit synthetic-data disclaimer.
- Responsive layouts for desktop and mobile without horizontal scrolling.

## Engineering notes

- `web/index.html`: semantic markup, no business calculations.
- `web/assets/styles.css`: tokens, component styles and responsive breakpoints.
- `web/assets/app.js`: event handlers and calls to existing endpoints.
- `retailiq/api/http.py`: local static asset mount `/assets`.
- `tests/test_ui_style.py`: asset integrity and style checks.
- `scripts/visual_ui_smoke.py`: optional Chromium visual smoke (requires Playwright installed) with mock browser fetch using real local API data from FastAPI TestClient. This intentionally does **not** validate a real LLM or Azure API call.

## Local use

From project root:

```bash
python -m pytest -q
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000`. Fonts load from Google Fonts when available; the page is fully usable offline using an installed fallback font.

## Demo integrity

ROI results are illustrative financial forecasts, not measured savings or measured token consumption. Offline responses are deterministic mock-data responses. No API secrets are exposed in browser assets.
