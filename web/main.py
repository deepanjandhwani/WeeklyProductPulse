"""
FastAPI app: weekly pulse dashboard + email API.

Run locally::

    uvicorn web.main:app --reload --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import os
import re
import smtplib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import config
from fastapi import Body, Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from web.recipients_schema import EmailSendRequest
from web.services import reports as report_svc
from web.services.mailer import markdown_to_html, send_latest_pulse_email, send_week_by_email

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(
    title="WeeklyProductPulse",
    description="Latest weekly pulse viewer + email distribution",
    version="1.0.0",
)

_cors = os.getenv("PULSE_WEB_CORS_ORIGINS", "").strip()
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def require_email_token(
    x_pulse_api_token: str | None = Header(default=None, alias="X-Pulse-API-Token"),
) -> None:
    expected = os.getenv("PULSE_WEB_API_TOKEN", "").strip()
    if not expected:
        return
    if x_pulse_api_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Pulse-API-Token")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "weekly-pulse-web"}


@app.get("/api/reports")
def api_list_reports():
    rows = report_svc.list_pulse_reports()
    return {
        "reports": [
            {
                "iso_week": r.iso_week,
                "file": r.path.name,
                "size_bytes": r.size_bytes,
            }
            for r in rows
        ]
    }


@app.get("/api/reports/latest")
def api_latest():
    latest = report_svc.get_latest_pulse()
    if not latest:
        return JSONResponse(
            status_code=404,
            content={"detail": "No pulse reports found under data/reports/"},
        )
    iso_week, md = latest
    return {
        "iso_week": iso_week,
        "markdown": md,
        "html": markdown_to_html(md),
    }


@app.get("/api/reports/{iso_week}")
def api_report_week(iso_week: str):
    md = report_svc.read_pulse_markdown(iso_week)
    if md is None:
        raise HTTPException(status_code=404, detail=f"No report for {iso_week}")
    return {"iso_week": iso_week, "markdown": md, "html": markdown_to_html(md)}


@app.post("/api/email/send")
def api_send_email(
    _: None = Depends(require_email_token),
    body: EmailSendRequest | None = Body(default=None),
):
    """
    Email the **full** weekly pulse (entire ``*_pulse.md`` as plain text + HTML) via SMTP.

    * ``recipients`` — optional. If provided (from the UI or API), must be one or more valid
      addresses. If omitted, the server uses ``EMAIL_RECIPIENTS`` from the environment.
    """
    body = body or EmailSendRequest()
    # Pydantic EmailStr -> str for SMTP
    rec_list: list[str] | None = None
    if body.recipients is not None:
        rec_list = [str(e) for e in body.recipients]
    try:
        if body.iso_week:
            recs = send_week_by_email(body.iso_week, rec_list)
            return {"ok": True, "iso_week": body.iso_week, "recipients": recs}
        iso_week, recs = send_latest_pulse_email(rec_list)
        return {"ok": True, "iso_week": iso_week, "recipients": recs}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (OSError, smtplib.SMTPException) as e:
        raise HTTPException(status_code=502, detail=f"SMTP error: {e}") from e


_ISO_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


@app.post("/api/reports/upload")
async def api_upload_report(
    _: None = Depends(require_email_token),
    file: UploadFile = ...,
):
    """Accept a ``*_pulse.md`` upload from CI and write it to ``data/reports/``."""
    if not file.filename or not file.filename.endswith("_pulse.md"):
        raise HTTPException(status_code=400, detail="Filename must match <YYYY-Wnn>_pulse.md")

    stem = file.filename.removesuffix("_pulse.md")
    if not _ISO_WEEK_RE.match(stem):
        raise HTTPException(status_code=400, detail=f"Invalid ISO week in filename: {stem}")

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.REPORTS_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"ok": True, "iso_week": stem, "file": file.filename, "size_bytes": len(content)}


# Static dashboard
if STATIC.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC / "assets")), name="assets")


@app.get("/")
def dashboard():
    index = STATIC / "index.html"
    if not index.is_file():
        return JSONResponse(
            status_code=500,
            content={"detail": "Dashboard not built: missing web/static/index.html"},
        )
    return FileResponse(index)
