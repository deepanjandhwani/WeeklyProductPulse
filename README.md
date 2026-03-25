# WeeklyProductPulse

WeeklyProductPulse is an end-to-end Voice-of-Customer pipeline for IndMoney Play Store reviews.

- Ingests a rolling 12-week window of reviews
- Clusters themes (Phase 2), extracts insights/quotes (Phase 3), generates weekly report (Phase 4)
- Appends report to Google Docs via MCP (mandatory in scheduled runs)
- Supports email delivery via SMTP or MCP (Gmail MCP)
- Includes FastAPI dashboard for viewing reports and sending emails on-demand

See `ARCHITECTURE.md` for full design details.

## Production Topology

| Component | Platform | Role |
|-----------|----------|------|
| **Backend API + email** | Railway (Docker) | Hosts FastAPI app; serves report JSON and handles email sending |
| **Frontend dashboard** | Vercel (static) | Serves HTML/CSS/JS; proxies `/api/*` requests to Railway |
| **Scheduled pipeline** | GitHub Actions | Runs Phases 1–4 daily at 10:00 UTC; appends report to Google Docs |
| **Google Docs** | Google Workspace | Primary output; report appended automatically after each pipeline run |
| **Email** | Gmail MCP (or SMTP) | Sent only when a user triggers it from the dashboard UI |

## Deployment

### Railway (backend + UI)

1. Create a Railway service from the GitHub repo.
2. Set **Root Directory** to `WeeklyProductPulse`.
3. Railway detects the `Dockerfile` and builds automatically.
4. Add environment variables in Railway → Variables:

| Variable | Value |
|----------|-------|
| `GROQ_API_KEY` | Groq API key |
| `GEMINI_API_KEY` | Gemini API key (optional if all phases use Groq) |
| `GOOGLE_DOCS_APPEND_ENABLED` | `true` |
| `GOOGLE_DOCS_APPEND_TRANSPORT` | `mcp` |
| `GOOGLE_DOCS_DOCUMENT_ID` | Google Doc ID from the document URL |
| `GOOGLE_CLIENT_ID` | OAuth Desktop client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth Desktop client secret |
| `EMAIL_TRANSPORT` | `mcp` |
| `EMAIL_MCP_COMMAND` | `npx` |
| `EMAIL_MCP_ARGS` | `-y @gongrzhe/server-gmail-autoauth-mcp` |
| `EMAIL_MCP_TOOL` | `send_email` |
| `PULSE_WEB_API_TOKEN` | Random 32+ char string (protects email API) |
| `LOG_LEVEL` | `INFO` |

5. Generate a public domain under Railway → Networking → Public Networking.
6. Verify: `https://<railway-domain>/api/reports`

### Vercel (frontend)

1. Go to [vercel.com](https://vercel.com) and import your GitHub repo.
2. Set **Root Directory** to `WeeklyProductPulse`.
3. Framework Preset: **Other** (no framework — it's plain static HTML).
4. Build & Output settings should auto-detect from `vercel.json`:
   - Build Command: (leave empty / none)
   - Output Directory: `web/static`
5. **Before deploying**, edit `vercel.json` and replace `REPLACE_WITH_YOUR_RAILWAY_DOMAIN` with your actual Railway public domain (e.g. `weeklyproductpulse-production-xxxx.up.railway.app`).
6. Optionally add Railway CORS: in Railway Variables, set `PULSE_WEB_CORS_ORIGINS=https://your-vercel-domain.vercel.app` (allows direct API calls as a fallback).
7. Deploy. The Vercel URL will serve the dashboard and proxy all `/api/*` calls to Railway.

### GitHub Actions (scheduled pipeline)

Workflow: `.github/workflows/scheduled-pulse.yml`

**Required repository secrets** (Settings → Secrets and variables → Actions):

| Secret | What |
|--------|------|
| `GROQ_API_KEY` | Groq API key (same as Railway / `.env`) |
| `GEMINI_API_KEY` | Gemini API key (optional) |
| `GOOGLE_DOCS_DOCUMENT_ID` | Google Doc ID |
| `GOOGLE_CLIENT_ID` | OAuth Desktop client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth Desktop client secret |
| `GOOGLE_DOCS_MCP_TOKEN_JSON` | Full JSON from `~/.config/google-docs-mcp/token.json` (run `npx -y @a-bonus/google-docs-mcp auth` locally to generate) |
| `RAILWAY_PUBLIC_URL` | Your Railway public URL, e.g. `https://weeklyproductpulse-production.up.railway.app` |
| `PULSE_WEB_API_TOKEN` | Same token as Railway (protects the upload endpoint) |

**Optional repository variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCHEDULER_PHASE1_MODE` | `auto` | `auto` / `incremental` / `backfill` |
| `SCHEDULER_SKIP_BACKFILL` | (unset) | Set `1` to skip Phase 1 if consolidated CSV exists |

The workflow validates that `GROQ_API_KEY` and `GOOGLE_DOCS_DOCUMENT_ID` are set before running the pipeline. After a successful run, it pushes all `*_pulse.md` reports to Railway via `POST /api/reports/upload` so they appear on the Vercel dashboard.

### Railway persistent volume (recommended)

Reports uploaded to Railway are stored on the container filesystem. Without a volume, they are lost on each redeploy. To persist them:

1. Railway dashboard → your service → **Settings → Volumes**
2. Add a volume, mount path: `/app/data`
3. Redeploy. Reports now survive container restarts and redeploys.

### Local development

```bash
cd WeeklyProductPulse/WeeklyProductPulse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill .env with real values
```

Start web app:

```bash
.venv/bin/uvicorn web.main:app --reload --host 0.0.0.0 --port 8000
```

Run full pipeline:

```bash
python -m scheduler
```

E2E test:

```bash
./scripts/run_e2e.sh
```

Fast re-test (phases 2–4 only):

```bash
SKIP_BACKFILL=1 WEEK=2026-W12 ./scripts/run_e2e.sh
```

## Secret Management

Each environment reads its own source. **They do not share config automatically.**

| Environment | Where secrets live |
|-------------|--------------------|
| Local dev | `.env` file (git-ignored) |
| Railway | Railway dashboard → Variables |
| GitHub Actions | Repository → Settings → Secrets and variables → Actions |

## MCP Email Setup (Gmail)

1. Enable **Gmail API** in Google Cloud Console for your project.
2. Set `EMAIL_TRANSPORT=mcp` and MCP vars (see Railway table above).
3. Run auth once locally: `npx -y @gongrzhe/server-gmail-autoauth-mcp auth`
4. OAuth keys file: `~/.gmail-mcp/gcp-oauth.keys.json` (auto-created from `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
5. For Railway: inject OAuth credentials/token as env vars or secrets.

## MCP Google Docs Setup

1. Enable **Google Docs API**, **Google Drive API**, and **Google Sheets API** in Google Cloud Console.
2. Create OAuth Desktop client; add yourself as test user on consent screen.
3. Run auth once locally:
   ```bash
   cd WeeklyProductPulse/WeeklyProductPulse  # folder with .env
   set -a && source .env && set +a
   npx -y @a-bonus/google-docs-mcp auth
   ```
4. Token saved to `~/.config/google-docs-mcp/token.json`.
5. For GitHub Actions: copy contents of `token.json` into secret `GOOGLE_DOCS_MCP_TOKEN_JSON`.

## Notes

- `scripts/run_e2e.sh` uses safe `.env` parsing (handles values with spaces).
- If Google Docs append is requested but fails, Phase 4 fails by design (mandatory).
- Email is sent only from the UI (not auto-sent by the pipeline unless `EMAIL_REPORT_AFTER_PIPELINE=true`).
- `groq>=0.13.1` is required for compatibility with `httpx>=0.28` (older versions crash on empty API keys).
