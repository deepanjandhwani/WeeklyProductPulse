# Scheduler (GitHub Actions & local)

## Local / cron

From the project root (folder containing `config.py`):

```bash
python -m scheduler
```

Same orchestration as [`scripts/run_e2e.sh`](../scripts/run_e2e.sh): Phase 1 backfill → 2 → 3 → 4 (with `--google-doc-append`).

### Environment

| Variable | Meaning |
|----------|---------|
| `SCHEDULER_SKIP_BACKFILL` | If `1` / `true`, skip `run_backfill.py` and run phases 2–4 only. |
| `SCHEDULER_WEEK` | With skip backfill, optional ISO week (e.g. `2026-W12`); default is current week. |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | Required for LLM phases. |
| `GOOGLE_*` | Optional Google Doc append via MCP — see [GOOGLE_DOCS.md](GOOGLE_DOCS.md). |

## GitHub Actions

Workflow: [`.github/workflows/scheduled-pulse.yml`](../.github/workflows/scheduled-pulse.yml)

- **Schedule:** `0 10 * * *` → **10:00 UTC every day**.  
  GitHub `schedule` events always use **UTC**. For **10:00 IST** (India), use cron **`30 4 * * *`** (04:30 UTC).
- **Manual run:** Actions → *Scheduled weekly pulse* → **Run workflow**.

### Why not “every 5 minutes”?

GitHub allows cron as short as **every 5 minutes** (`*/5 * * * *`), but running the **full** Play Store + LLM pipeline that often will exhaust APIs and minutes. Keep **one daily window** (or weekly) for production; use **workflow_dispatch** for ad-hoc runs.

### Repository secrets

| Secret | Required |
|--------|----------|
| `GROQ_API_KEY` | Yes |
| `GEMINI_API_KEY` | Yes |
| `GOOGLE_DOCS_DOCUMENT_ID` | Optional (Doc append) |
| `GOOGLE_CLIENT_ID` | Optional (MCP append) |
| `GOOGLE_CLIENT_SECRET` | Optional (MCP append) |
| `GOOGLE_DOCS_MCP_TOKEN_JSON` | Optional — paste full contents of local `~/.config/google-docs-mcp/token.json` for headless MCP append |

### Optional repository variables

| Variable | Meaning |
|----------|---------|
| `SCHEDULER_SKIP_BACKFILL` | Set to `1` only if you commit `data/consolidated/*.csv` and want to skip Phase 1 (unusual). |

### Node.js

The workflow installs **Node 20** so `npx -y @a-bonus/google-docs-mcp` works for Phase 4 MCP append.
