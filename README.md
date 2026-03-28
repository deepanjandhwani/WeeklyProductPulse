# WeeklyProductPulse

WeeklyProductPulse is an end-to-end Voice-of-Customer pipeline for IndMoney Play Store reviews.

- Ingests a rolling 12-week window of reviews
- Clusters themes (Phase 2), extracts insights/quotes (Phase 3), generates weekly report (Phase 4)
- Appends report to Google Docs via MCP (mandatory in scheduled runs)
- Supports email delivery via SMTP or MCP (Gmail MCP)
- Includes a polished Next.js dashboard for viewing reports and emailing them to your team

See `ARCHITECTURE.md` for full design details.

## Production Topology

| Component | Platform | Role |
|-----------|----------|------|
| **Backend API + email** | Render (Docker) | Hosts FastAPI app; serves report JSON and handles email sending |
| **Frontend dashboard** | Vercel (Next.js in `frontend/`) | Claude-inspired UI (Lora + DM Sans, DOMPurify); proxies `/api/*` to Render |
| **Scheduled pipeline** | GitHub Actions | Runs Phases 1–4 every Sunday 10:00 PM IST (16:30 UTC); appends report to Google Docs; commits reports back to repo |
| **Keep-alive ping** | cron-job.org / Better Stack (external) | Pings Render `/api/health` every 5 min to prevent cold-start delays; GitHub Actions workflow kept as backup |
| **Google Docs** | Google Workspace | Primary output; report appended automatically after each pipeline run |
| **Email** | Gmail MCP (or SMTP) | Sent only when a user triggers it from the dashboard UI |

## Deployment

### Render (backend)

1. Create a new **Web Service** on [render.com](https://render.com), connect your GitHub repo.
2. Set **Root Directory** to `WeeklyProductPulse`.
3. Render detects the `Dockerfile` and builds automatically.
4. Add environment variables in Render → Environment:

| Variable | Value |
|----------|-------|
| `GROQ_API_KEY` | Groq API key |
| `GEMINI_API_KEY` | Gemini API key (optional) |
| `GOOGLE_DOCS_APPEND_ENABLED` | `true` |
| `GOOGLE_DOCS_APPEND_TRANSPORT` | `mcp` |
| `GOOGLE_DOCS_DOCUMENT_ID` | Google Doc ID from the document URL |
| `GOOGLE_CLIENT_ID` | OAuth Desktop client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth Desktop client secret |
| `EMAIL_TRANSPORT` | `mcp` |
| `EMAIL_MCP_COMMAND` | `npx` |
| `EMAIL_MCP_ARGS` | `-y @gongrzhe/server-gmail-autoauth-mcp` |
| `EMAIL_MCP_TOOL` | `send_email` |
| `PULSE_WEB_API_TOKEN` | Random 32+ char string (protects email + upload API) |
| `GMAIL_MCP_CREDENTIALS_JSON` | Full JSON from `~/.gmail-mcp/credentials.json` (OAuth refresh token for Gmail MCP) |
| `GOOGLE_DOCS_MCP_TOKEN_JSON` | Full JSON from `~/.config/google-docs-mcp/token.json` |
| `LOG_LEVEL` | `INFO` |

5. Note your public Render URL (e.g. `https://weeklyproductpulse.onrender.com`).
6. Verify: `https://<render-domain>/api/health` should return `{"status":"ok"}`.

> **Note — Render free tier cold starts:** Free instances spin down after ~15 minutes of inactivity and take 30–60 seconds to wake. GitHub Actions cron is **not reliable** for keepalive (free-tier runs can be delayed 15–30 min, longer than Render's sleep window). Use a dedicated external ping service: **[cron-job.org](https://cron-job.org)** (free, reliable, every 5 min) or **[Better Stack Uptime](https://betterstack.com)** (free, every 3 min) — both point at `https://weeklyproductpulse.onrender.com/api/health`. The `.github/workflows/keep-render-awake.yml` workflow is kept as a secondary backup.

### Vercel (frontend — Next.js)

Python dependencies live in **`requirements-app.txt`** (not `requirements.txt`) so Vercel does **not** auto-detect a Python project at the repo root. The repo uses **npm workspaces**: root **`package.json`** declares `workspaces: ["frontend"]` and lists **`next`**, **`react`**, and **`react-dom`** so Vercel’s “Next.js version” check passes when deploying from the **repository root**. There is a **single** `package-lock.json` at the repo root (no lockfile inside `frontend/`).

**Deploy from repo root (default in Vercel):**

- Root **`vercel.json`**: `npm install` then **`npm run build:vercel`** (runs `next build` in `frontend/`, then copies **`frontend/.next` → `.next`** so Vercel’s Next runtime finds the output at the repo root).
- Root **`.nvmrc`**: Node `20` (matches Vercel).

**Or deploy only the Next app (often simpler):**

1. Go to [vercel.com/new](https://vercel.com/new) and import your GitHub repo.
2. Set **Root Directory** to **`frontend`** (one level — if your repo already opens inside `WeeklyProductPulse`, use **`frontend`** only, not `WeeklyProductPulse/frontend`).
3. If your GitHub repo has an extra nesting folder (`WeeklyProductPulse/frontend`), use that full path instead.
4. In Vercel → **Settings → Environment Variables**, add:

| Key | Value |
|-----|-------|
| `PULSE_API_UPSTREAM` | `https://weeklyproductpulse.onrender.com` (your Render URL, no trailing slash) |

5. Optionally set the same URL in `frontend/.env.local` for local `next dev`.
6. Deploy. All `/api/*` calls from the dashboard are proxied to `PULSE_API_UPSTREAM` via `next.config.ts` rewrites.

> **“No Next.js version detected”:** Vercel is reading the wrong folder’s `package.json`. Pull latest `main`, then either (a) set **Root Directory** to **`frontend`** and redeploy, or (b) leave Root Directory empty (repo root) so the workspace **root** `package.json` (which lists `next`) is used. Do **not** mix a Root Directory of `frontend` with expecting the root lockfile — if you use `frontend`, `frontend/vercel.json` runs `npm install` + `npm run build` there.
>
> **“No fastapi entrypoint found”:** Pull latest `main` (`requirements-app.txt` + Next workspace). Clear any **Framework Override** that forces Python.
>
> **`routes-manifest.json` / `web/static`:** The build finished but deployment failed looking for `/web/static/routes-manifest.json`. That means **Output Directory** is still set to **`web/static`** (legacy static UI). For Next.js it must be **empty** — Vercel uses **`frontend/.next`** (or **`.next`** when Root Directory is `frontend`). In **Project → Settings → Build & Development**, clear **Output Directory** (turn off override if needed), keep **Framework Preset** as **Next.js**, then redeploy.
>
> **`.next` not found at `/vercel/path0/.next`:** With **Root Directory** at the repo root, `next build` only creates **`frontend/.next`**. The repo’s **`build:vercel`** script copies that folder to **`.next`** at the root. Pull latest `main` and redeploy, **or** set **Root Directory** to **`frontend`** and use the simpler **`frontend/vercel.json`** build (`npm run build` in that folder) so `.next` is already at the project root.

### GitHub Actions (scheduled pipeline)

Workflow: `.github/workflows/scheduled-pulse.yml`

**Required repository secrets** (Settings → Secrets and variables → Actions):

| Secret | What |
|--------|------|
| `GROQ_API_KEY` | Groq API key |
| `GEMINI_API_KEY` | Gemini API key (optional) |
| `GOOGLE_DOCS_DOCUMENT_ID` | Google Doc ID |
| `GOOGLE_CLIENT_ID` | OAuth Desktop client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth Desktop client secret |
| `GOOGLE_DOCS_MCP_TOKEN_JSON` | Full JSON from `~/.config/google-docs-mcp/token.json` |

**Optional repository variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCHEDULER_PHASE1_MODE` | `auto` | `auto` / `incremental` / `backfill` |
| `SCHEDULER_SKIP_BACKFILL` | (unset) | Set `1` to skip Phase 1 if consolidated CSV exists |

The workflow:
- Validates `GROQ_API_KEY` and `GOOGLE_DOCS_DOCUMENT_ID` before running
- Runs Phases 1–4 every **Sunday 10:00 PM IST (16:30 UTC)**
- **Commits** generated `*_pulse.md` reports back to the repo (`[skip ci]`) so the next Render deploy includes them

### Keep Render awake (external ping service — recommended)

GitHub Actions cron is **not reliable** for keepalive on the free tier — runs can be delayed 15–30 minutes, longer than Render's 15-minute sleep window. Use a purpose-built external ping service instead:

**Option A — [cron-job.org](https://cron-job.org) (free)**
1. Sign up → Create Cronjob
2. URL: `https://weeklyproductpulse.onrender.com/api/health`
3. Schedule: every **5 minutes**
4. Save

**Option B — [Better Stack Uptime](https://betterstack.com) (free tier)**
1. Sign up → Add Monitor
2. URL: `https://weeklyproductpulse.onrender.com/api/health`
3. Check interval: **3 minutes**
4. Save

**Option C — [Freshping](https://freshping.io) (free)**
1. Sign up → Add Check
2. URL: `https://weeklyproductpulse.onrender.com/api/health`
3. Frequency: **1 minute**
4. Save

A backup GitHub Actions workflow (`.github/workflows/keep-render-awake.yml`) is also in the repo but should not be the sole keepalive mechanism.

### Local development

```bash
cd WeeklyProductPulse/WeeklyProductPulse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-app.txt
cp .env.example .env
# Fill .env with real values
```

Start the **API** (reports + email):

```bash
.venv/bin/uvicorn web.main:app --reload --host 0.0.0.0 --port 8000
```

Start the **Next.js dashboard** (in a second terminal):

```bash
cd frontend
cp .env.example .env.local   # set PULSE_API_UPSTREAM=http://127.0.0.1:8000
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The FastAPI app also serves the legacy static UI at `/` when accessed directly via Uvicorn.

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
| Render | Render dashboard → Environment |
| GitHub Actions | Repository → Settings → Secrets and variables → Actions |
| Vercel | Project → Settings → Environment Variables |

## MCP Email Setup (Gmail)

1. Enable **Gmail API** in Google Cloud Console for your project.
2. Set `EMAIL_TRANSPORT=mcp` and MCP vars (see Render table above).
3. Run auth once locally: `npx -y @gongrzhe/server-gmail-autoauth-mcp auth`
4. OAuth keys file: `~/.gmail-mcp/gcp-oauth.keys.json` (auto-created from `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
5. For Render: add `GMAIL_MCP_CREDENTIALS_JSON` as an environment variable (paste the full JSON from `~/.gmail-mcp/credentials.json`). The `entrypoint.sh` script writes it to disk on container startup.

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
- The Next.js dashboard shows human-readable date ranges (e.g. "Mar 23 – 29, 2026"), skeleton loading, a success popup after email delivery, and automatically selects the current ISO week if a report exists for it.
- On **Refresh**, the dashboard bypasses the browser cache (`no-store`) to fetch the latest report list from Render.
- `groq>=0.13.1` is required for compatibility with `httpx>=0.28` (older versions crash on empty API keys).
- Render free tier spins down after ~15 min of inactivity. GitHub Actions cron is too unreliable for keepalive — use **cron-job.org** or **Better Stack** (both free) to ping `/api/health` every 5 min. The GitHub Actions backup workflow is already in the repo but delayed runs mean it can't guarantee zero cold starts.
