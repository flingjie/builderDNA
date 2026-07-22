# Archived — Frontend (Next.js)

BuilderDNA 2.0 replaces the web UI with **CLI + Rich terminal output** (`builderdna radar agent`).

The Next.js frontend is **no longer maintained** and has been superseded by:
- `cli/main.py` — `builderdna radar` / `builderdna opportunities` / `builderdna health`
- `cli/formatters.py` — Rich tables with trends, opportunities, related repos, vendor tags
- `report/builder_report.py` — Markdown + JSON report generation

To start the legacy frontend:
```bash
cd frontend && npm run dev
```

API endpoints that previously served the frontend (`/api/explorer`, `/api/vendors`, `/api/compare`) now return empty data with deprecation notes.
