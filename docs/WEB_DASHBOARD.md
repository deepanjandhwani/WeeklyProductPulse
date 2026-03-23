# Web dashboard & email distribution

## What it does

- **Backend (FastAPI):** lists pulse reports from `data/reports/`, serves the latest (or chosen week) as Markdown + HTML, and sends email via **SMTP**.
- **Frontend:** static dashboard at `/` — dark UI, week selector, **Email participants** button.

## Run locally

From the project root (folder with `config.py`):

```bash
pip install -r requirements.txt
uvicorn web.main:app --reload --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080/**

## Environment variables

### SMTP (required to send email)

| Variable | Example |
|----------|---------|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your mailbox |
| `SMTP_PASSWORD` | app password (not your normal Gmail password) |
| `SMTP_FROM` | display from-address (defaults to `SMTP_USER`) |
| `SMTP_USE_TLS` | `true` (default) |

### Recipients

| Variable | Example |
|----------|---------|
| `EMAIL_RECIPIENTS` | `pm@company.com,lead@company.com` |

### Optional security

| Variable | Purpose |
|----------|---------|
| `PULSE_WEB_API_TOKEN` | If set, `POST /api/email/send` requires header `X-Pulse-API-Token: <token>` |
| `PULSE_WEB_CORS_ORIGINS` | Comma-separated origins if you host the API separately from the UI |

### Auto-email after pipeline

| Variable | Purpose |
|----------|---------|
| `EMAIL_REPORT_AFTER_PIPELINE` | Set to `true` to send the latest pulse by email at the end of `python -m scheduler` (needs SMTP + `EMAIL_RECIPIENTS`). |

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/reports` | List all `*_pulse.md` weeks |
| `GET` | `/api/reports/latest` | Latest week: `markdown` + `html` |
| `GET` | `/api/reports/{iso_week}` | One week |
| `POST` | `/api/email/send` | Sends the **full** report (entire `*_pulse.md` as **plain text + HTML** multipart). Body JSON: `recipients` — **array of emails** or a single comma-separated string (validated with Pydantic `EmailStr`). Optional `iso_week`; if omitted, uses latest file. If `recipients` is omitted or empty, falls back to `EMAIL_RECIPIENTS` in the environment. |

### Example (curl)

```bash
curl -s -X POST http://127.0.0.1:8080/api/email/send \
  -H "Content-Type: application/json" \
  -d '{"iso_week":"2026-W12","recipients":["pm@company.com","lead@company.com"]}'
```

## Production notes

- Run behind HTTPS (reverse proxy).
- Use a dedicated SMTP user / transactional provider (SendGrid, SES, etc.).
- Do not expose the dashboard on the public internet without auth; add a reverse-proxy auth layer or VPN.
