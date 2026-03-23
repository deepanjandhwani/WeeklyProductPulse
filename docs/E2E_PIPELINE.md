# End-to-end pipeline test

Run **Phase 1 → 2 → 3 → 4** in order. Phase 4 can append to Google Docs via **MCP** (`GOOGLE_DOCS_APPEND_TRANSPORT=mcp`) — same setup as [GOOGLE_DOCS.md](GOOGLE_DOCS.md) (`auth` + `.env` OAuth vars + `GOOGLE_DOCS_DOCUMENT_ID`).

## Prerequisites

| Requirement | Purpose |
|-------------|---------|
| `.env` | `GROQ_API_KEY`, `GEMINI_API_KEY` |
| `.env` | For Doc append: `GOOGLE_DOCS_DOCUMENT_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| `npx` + token | `npx -y @a-bonus/google-docs-mcp auth` → `~/.config/google-docs-mcp/token.json` |
| Python venv | `pip install -r requirements.txt` (includes `mcp` for Phase 4 append) |

Work from the **inner project root** (folder containing `.env`, `config.py`, `phase4_report/`).

## Option A — One script (recommended)

```bash
cd /path/to/WeeklyProductPulse/WeeklyProductPulse   # inner root
chmod +x scripts/run_e2e.sh
./scripts/run_e2e.sh
```

- **Phase 1** runs `run_backfill.py`: fetches the **lookback window** of weeks from the Play Store and writes `data/consolidated/<current_iso_week>_full.csv`. **This can take many minutes** and needs network.
- Phases **2–4** run for the same week the script resolves (defaults to **current** ISO week).

**Skip Phase 1** when you already have `data/consolidated/<WEEK>_full.csv` (e.g. re-test phases 2–4 only):

```bash
SKIP_BACKFILL=1 WEEK=2026-W12 ./scripts/run_e2e.sh
```

## Option B — Commands by hand

Replace `2026-W12` with your week (or use `get_current_iso_week()` from a Python shell).

```bash
set -a && source .env && set +a
export GOOGLE_DOCS_APPEND_TRANSPORT=mcp   # for Doc append via MCP

# 1. Fetch + consolidate (or skip if consolidated CSV exists)
python run_backfill.py

# 2. Map + reduce themes
python -m phase2_clustering.tagger --week 2026-W12
python -m phase2_clustering.theme_aggregator --week 2026-W12

# 3. Quotes + insights JSON
python -m phase3_insights.insight_extractor --week 2026-W12

# 4. Markdown report + append to Doc (if enabled / --google-doc-append)
python -m phase4_report.report_generator --week 2026-W12 --google-doc-append
```

## Success checks

| Artifact | Path |
|----------|------|
| Consolidated reviews | `data/consolidated/<week>_full.csv` |
| Tagged CSV | `data/tagged/<week>_tagged.csv` |
| Theme summary | `data/tagged/<week>_theme_summary.json` |
| Insights | `data/tagged/<week>_insights.json` |
| Pulse report | `data/reports/<week>_pulse.md` |
| GDoc payload | `data/reports/<week>_gdoc_payload.json` |
| Logs | `mcp_google_doc_appended` / `google_docs_append_ok` in run logs when MCP append succeeds |

## Notes

- **Cursor MCP** (`.cursor/mcp.json`) is separate from **Phase 4 MCP append** (Python spawns `npx @a-bonus/google-docs-mcp`). Both can share the same OAuth token file.
- If Phase 4 append fails, the Markdown and `*_gdoc_payload.json` are still written; check logs and [GOOGLE_DOCS.md](GOOGLE_DOCS.md).

## GitHub Actions (daily schedule)

Production scheduling uses **`python -m scheduler`** from [`.github/workflows/scheduled-pulse.yml`](../.github/workflows/scheduled-pulse.yml). See [SCHEDULER.md](SCHEDULER.md) for secrets, UTC vs IST cron, and why a 5-minute cron is not recommended for the full pipeline.
