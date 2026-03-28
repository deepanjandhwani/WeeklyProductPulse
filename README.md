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
| **Frontend dashboard** | Vercel (Next.js in `frontend/`) | Lora + DM Sans, DOMPurify, nav brand asset in `frontend/public/`; proxies `/api/*` to Render |
| **Scheduled pipeline** | GitHub Actions | Runs Phases 1–4 every Sunday 10:00 PM IST (16:30 UTC); appends report to Google Docs; commits reports back to repo |
| **Keep-alive ping** | cron-job.org / Better Stack (external) | Pings Render `/api/health` every 5 min to prevent cold-start delays; GitHub Actions workflow kept as backup |
| **Google Docs** | Google Workspace | Primary output; report appended automatically after each pipeline run |
| **Email** | Gmail MCP (or SMTP) | Sent only when a user triggers it from the dashboard UI |

## Deployment

### Render (backend)

1. Create a new **Web Service** on [render.com](https://render.com), connect your GitHub repo.
2. Set **Root Directory** to the folder that contains the **`Dockerfile`** at the top of that tree (for this repo, that is usually **empty** / repository root — not a subfolder like `WeeklyProductPulse`, unless your Git remote wraps the project in another directory).
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

Python dependencies live in **`requirements-app.txt`** (not `requirements.txt`) so Vercel does **not** auto-detect a Python project at the repo root. The repo uses **npm workspaces**: root **`package.json`** declares `workspaces: ["frontend"]` and there is a **single** `package-lock.json` at the repo root.

**Deploy with Root Directory `frontend` (required):** Vercel’s Next.js runtime expects **`.next`** next to **`package.json`** for the deployed app. Building from the repo root leaves output in **`frontend/.next`** only; copying it to the repo root **breaks** serverless function paths (e.g. `_global-error` Lambdas). So the Vercel project **Root Directory** must be **`frontend`**. This setup is **production-tested** on the main GitHub repo (`deepanjandhwani/WeeklyProductPulse`: path is exactly **`frontend`**, not `WeeklyProductPulse/frontend`).

1. Go to [vercel.com/new](https://vercel.com/new) and import your GitHub repo.
2. **Project → Settings → General → Root Directory** → **`frontend`** (only use a longer path such as `SomeFolder/frontend` if your remote actually nests the app that way).
3. **Build & Development**: leave **Output Directory** empty; **Framework** = **Next.js**. **`frontend/vercel.json`** runs **`cd .. && npm install`** (workspace install from repo root) then **`cd .. && npm run build -w frontend`**.
4. **Node `20`:** **`frontend/.nvmrc`** (and the repo root **`.nvmrc`**) match Vercel’s default when Root Directory is **`frontend`**.
5. In Vercel → **Settings → Environment Variables**, add:

| Key | Value |
|-----|-------|
| `PULSE_API_UPSTREAM` | `https://weeklyproductpulse.onrender.com` (your Render URL, no trailing slash) |

6. Optionally set the same URL in `frontend/.env.local` for local `next dev`.
7. Deploy. All `/api/*` calls from the dashboard are proxied to `PULSE_API_UPSTREAM` via `next.config.ts` rewrites.

> **“No Next.js version detected”:** Set **Root Directory** to **`frontend`** (see above). **`frontend/package.json`** lists **`next`** so detection works once Vercel reads that folder.
>
> **“No fastapi entrypoint found”:** Pull latest `main` (`requirements-app.txt` + Next workspace). Clear any **Framework Override** that forces Python.
>
> **`routes-manifest.json` / `web/static`:** **Output Directory** is set to **`web/static`** (legacy). Clear it in **Project → Settings → Build & Development** (turn off override if needed), keep **Framework Preset** as **Next.js**, then redeploy.
>
> **`.next` not found / `_global-error` Lambda / function path errors:** Set **Root Directory** to **`frontend`** (see above). Do **not** copy **`frontend/.next`** to the repo root — that breaks Vercel’s function paths. If you overrode **Build Command** in the dashboard, clear the override so **`frontend/vercel.json`** is used.

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

**If Actions show red:** Open the failed run → expand the step. **Missing secrets** fails early in “Verify required Action secrets”. **Pipeline / Phase 4** failures are usually API keys, Google Doc append, or missing data — read the log. **Keep Render awake** (`.github/workflows/keep-render-awake.yml`) is best-effort: transient `curl` errors to Render should not fail the job after the latest workflow fix.

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

**Latency:** Gmail MCP runs `npx` and a subprocess; that is slower than plain SMTP. By default the server sends **one recipient per MCP session** (reliable with common Gmail MCP servers). Set **`EMAIL_MCP_BATCH=1`** only if your MCP server supports multiple sends in one session (faster, but can fail on some servers). For the fastest sends in production, use **`EMAIL_TRANSPORT=smtp`** with a transactional provider (SendGrid, SES, Gmail SMTP) instead of MCP.

**Debugging failed sends:** The API returns **502** with a **detail** string from the MCP layer (tool error, missing creds, `npx` failure, etc.). Check **Render → Logs** for the same message and full traceback.

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

- **Nav brand:** The dashboard uses **`frontend/public/assets/images/indmoney-logo.svg`** (served as `/assets/images/indmoney-logo.svg`). Replace that file with your official PNG/SVG if you have a licensed asset; the repo ships a small green “IM” monogram so the header slot is never empty.
- `scripts/run_e2e.sh` uses safe `.env` parsing (handles values with spaces).
- If Google Docs append is requested but fails, Phase 4 fails by design (mandatory).
- Email is sent only from the UI (not auto-sent by the pipeline unless `EMAIL_REPORT_AFTER_PIPELINE=true`).
- The Next.js dashboard shows human-readable date ranges (e.g. "Mar 23 – 29, 2026"), skeleton loading, a success popup after email delivery, and automatically selects the current ISO week if a report exists for it.
- On **Refresh**, the dashboard bypasses the browser cache (`no-store`) to fetch the latest report list from Render.
- `groq>=0.13.1` is required for compatibility with `httpx>=0.28` (older versions crash on empty API keys).
- Render free tier spins down after ~15 min of inactivity. GitHub Actions cron is too unreliable for keepalive — use **cron-job.org** or **Better Stack** (both free) to ping `/api/health` every 5 min. The GitHub Actions backup workflow is already in the repo but delayed runs mean it can't guarantee zero cold starts.
