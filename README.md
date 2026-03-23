# WeeklyProductPulse

WeeklyProductPulse is an end-to-end Voice-of-Customer pipeline for IndMoney Play Store reviews.

- Ingests a rolling 12-week window of reviews
- Clusters themes (Phase 2), extracts insights/quotes (Phase 3), generates weekly report (Phase 4)
- Optionally appends to Google Docs via MCP
- Supports SMTP email delivery
- Includes FastAPI dashboard for viewing/sending reports

See `ARCHITECTURE.md` for full design details.

## Recommended Deployment (Free/Low-Cost)

### 1) Web app hosting (FastAPI + dashboard)

Use an always-on VM (recommended: Oracle Cloud Always Free ARM VM).

Reason:
- Full control over outbound SMTP
- Can install both Python and Node (`npx` required for Google Docs MCP append)
- No cold starts for dashboard

### 2) Scheduler hosting

Use GitHub Actions cron for scheduled pipeline runs (`python -m scheduler`).

Reason:
- Built-in cron
- Easy secrets management
- Good fit for batch runs

## Production Topology

- **VM**: runs FastAPI app (`uvicorn web.main:app`)
- **GitHub Actions**: runs scheduled pipeline (`python -m scheduler`)
- **Google Docs**: appended by Phase 4 using MCP transport
- **SMTP provider**: used for email sends (UI/manual and optional post-pipeline)

## VM Setup (Oracle Ubuntu example)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

```bash
git clone https://github.com/deepanjandhwani/WeeklyProductPulse.git
cd WeeklyProductPulse/WeeklyProductPulse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill .env with real values
```

Start web app:

```bash
.venv/bin/uvicorn web.main:app --host 0.0.0.0 --port 8000
```

Then run behind Nginx + TLS (recommended for production).

## Required Environment Variables

Core:
- `GROQ_API_KEY`
- `GEMINI_API_KEY` (if using Gemini paths)

Google Docs append:
- `GOOGLE_DOCS_APPEND_ENABLED=true`
- `GOOGLE_DOCS_APPEND_TRANSPORT=mcp`
- `GOOGLE_DOCS_DOCUMENT_ID`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

SMTP:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_USE_TLS=true`

Optional:
- `EMAIL_REPORT_AFTER_PIPELINE=true`
- `EMAIL_RECIPIENTS=email1@company.com,email2@company.com`

## GitHub Actions Scheduler Setup

Workflow: `.github/workflows/scheduled-pulse.yml`

Configure repository secrets:
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_DOCS_DOCUMENT_ID`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_DOCS_MCP_TOKEN_JSON` (OAuth token JSON for MCP)

Optional repository variables:
- `SCHEDULER_PHASE1_MODE=auto` (recommended)
- `SCHEDULER_SKIP_BACKFILL` (normally unset)

## Run Commands

Local scheduler run:

```bash
python -m scheduler
```

E2E script:

```bash
./scripts/run_e2e.sh
```

Fast re-test phases 2-4:

```bash
SKIP_BACKFILL=1 WEEK=2026-W12 ./scripts/run_e2e.sh
```

## Notes

- `scripts/run_e2e.sh` uses safe `.env` parsing (handles values with spaces, e.g. `SMTP_FROM` display names).
- If Google Docs append is requested but fails, Phase 4 fails by design.
- For SMTP issues on managed PaaS, consider moving to an HTTPS email API provider.
