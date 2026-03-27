# Deploy WeeklyProductPulse backend on Hugging Face Spaces (demos)

Use this for **short demos**. Free Spaces may **sleep** after inactivity (first request can take 30–60s). Files under `data/reports/` are **not durable** on free tier unless you enable paid persistent storage.

## Prerequisites

- Hugging Face account ([huggingface.co](https://huggingface.co))
- GitHub repo with this project (same layout as production: `Dockerfile` at the **root of the repo** you connect to the Space)
- For **email in the demo**: prefer `EMAIL_TRANSPORT=smtp` with a transactional provider, or skip email and only show the report UI

## Step 1 — Create a Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. **Owner:** your user or org.
3. **Space name:** e.g. `weekly-product-pulse-api`.
4. **License:** your choice.
5. **SDK:** **Docker**.
6. **Visibility:** **Public** (simplest for Vercel + browser demos) or **Private** (then you must handle auth yourself).
7. Click **Create Space**.

## Step 2 — Connect your GitHub repository

1. In the Space → **Settings** → **Repository**.
2. Connect **GitHub** and select the repo that contains this app.
3. Set **Branch** to `main` (or your default branch).

**Monorepo note:** Hugging Face builds from the **repository root**. Your `Dockerfile` must live at the root of the linked repo. If your app lives in a subfolder, either:

- move/copy the `Dockerfile` (and build context) to the repo root, or  
- use a dedicated small repo that only contains this app folder.

## Step 3 — Space README (optional but nice)

At the repo root, you can add a `README.md` with YAML front matter so the Space card looks good:

```markdown
---
title: Weekly Product Pulse API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

FastAPI backend for the Weekly Product Pulse demo (reports + optional email).
```

## Step 4 — Port (automatic)

Spaces set **`PORT=7860`** for Docker. This project’s `entrypoint.sh` runs:

`uvicorn ... --port "${PORT:-8000}"`

So on HF you **do not** need to change code — Uvicorn listens on **7860** automatically.

## Step 5 — Variables & secrets (Space settings)

In the Space → **Settings** → **Variables and secrets**, add the same kinds of values you use on Railway (names only; paste real values in the UI):

**Minimum for “report viewer” demo**

- `GROQ_API_KEY` — if anything in the web layer touches Groq (usually not for read-only report view).
- Optional: seed `data/reports/*.md` in the image or upload via `POST /api/reports/upload` after deploy.

**If you use report upload from GitHub Actions (usually skip for demo)**

- `PULSE_WEB_API_TOKEN` — protect upload + email.
- `GMAIL_MCP_CREDENTIALS_JSON`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — only if `EMAIL_TRANSPORT=mcp`.

**Demo tip:** leave `PULSE_WEB_API_TOKEN` **empty** so the Vercel UI does not need a token for read-only flows; **do not** expose a public Space with upload/email enabled without a token.

## Step 6 — Build & logs

1. Space → **Logs** (or **Build** tab) and wait for **Build succeeded**.
2. Open the Space URL. HF shows the Space page; your API is still at paths like `/api/health`, `/api/reports`.

**Health check**

- `https://<your-subdomain>.hf.space/api/health`  
  (exact subdomain is on the Space page — pattern is usually `https://USER-SPACENAME.hf.space`)

## Step 7 — Point Vercel at the Space

1. Copy the Space **API base URL** (same origin as above, no trailing slash).
2. In your repo `vercel.json`, set the rewrite destination to:

`https://YOUR-SUBDOMAIN.hf.space/api/:path*`

3. Push to GitHub so Vercel redeploys.

## Step 8 — Warm up before a live demo

Open the Space URL (or hit `/api/health`) **1–2 minutes** before presenting so the container is awake.

## Limitations (demos)

| Topic | Notes |
|--------|--------|
| Sleep / cold start | First request after idle can be slow on free tier. |
| Disk | Reports may disappear on restart unless you use persistent storage (paid) or re-upload. |
| MCP email | Spawning `npx` + OAuth is fragile on Spaces; prefer SMTP for demos or disable email. |
| Timeouts | Very long MCP calls might hit platform limits; keep demos to “load report + refresh”. |

## Quick checklist

- [ ] Docker Space created, repo linked, build green  
- [ ] `/api/health` returns JSON  
- [ ] `vercel.json` rewrite points to `https://…hf.space`  
- [ ] Demo warmed up before the meeting  
