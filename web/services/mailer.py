"""
Send weekly pulse reports via SMTP (Gmail, SendGrid SMTP, Amazon SES, etc.).
"""

from __future__ import annotations

import os
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

import markdown

from web.services.reports import get_latest_pulse, read_pulse_markdown


def _env_clean(name: str, default: str = "") -> str:
    """Read env var; strip whitespace and optional wrapping quotes (common .env mistakes)."""
    raw = os.getenv(name, default)
    if raw is None:
        return ""
    v = str(raw).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


def _recipients_from_env() -> list[str]:
    raw = os.getenv("EMAIL_RECIPIENTS", "").strip()
    if not raw:
        return []
    return [e.strip() for e in raw.split(",") if e.strip()]


def markdown_to_html(md: str) -> str:
    """Convert Markdown to a styled HTML fragment (tables supported via extra)."""
    html = markdown.markdown(md, extensions=["extra"])
    html = re.sub(
        r"<h4>(\d+)\.\s*(.*?)\s*\((\d+)\s*reviews\s*·\s*([\d.]+%)\s*·\s*★([\d.]+)\)</h4>",
        r'<div class="theme-card"><div class="theme-header"><span class="theme-rank">\1</span>'
        r'<span class="theme-name">\2</span></div>'
        r'<div class="theme-stats"><span class="stat"><strong>\3</strong> reviews</span>'
        r'<span class="stat"><strong>\4</strong> share</span>'
        r'<span class="stat"><strong>★\5</strong> avg</span></div></div>',
        html,
    )
    return html


def _display_name_from_email(email: str) -> str:
    """
    Derive a user-friendly name from an email local-part.

    Examples:
    - "deepanjan0611@gmail.com" -> "Deepanjan"
    - "lead.pm@company.com" -> "Lead Pm"
    """
    local = (email or "").split("@", 1)[0]
    if not local:
        return "User"
    # Normalize separators and drop obvious numeric suffixes.
    cleaned = re.sub(r"[._\-+]+", " ", local)
    cleaned = re.sub(r"\d+$", "", cleaned).strip()
    if not cleaned:
        cleaned = local
    return " ".join(part.capitalize() for part in cleaned.split()) or "User"


def send_pulse_email(
    *,
    iso_week: str,
    markdown_body: str,
    recipients: Iterable[str],
    subject_prefix: str = "Weekly Product Pulse",
) -> None:
    """Send report email via configured transport (SMTP default, MCP optional)."""
    recs = [r for r in recipients if r]
    if not recs:
        raise ValueError("No email recipients configured")

    transport = _env_clean("EMAIL_TRANSPORT", "smtp").lower()
    if transport not in ("smtp", "mcp"):
        raise ValueError("EMAIL_TRANSPORT must be 'smtp' or 'mcp'")

    host = _env_clean("SMTP_HOST")
    try:
        port = int(_env_clean("SMTP_PORT") or "587")
    except ValueError:
        port = 587
    user = _env_clean("SMTP_USER")
    password = _env_clean("SMTP_PASSWORD")
    from_addr = _env_clean("SMTP_FROM") or user
    use_tls = _env_clean("SMTP_USE_TLS") or "true"
    use_tls = use_tls.lower() in ("1", "true", "yes")

    if transport == "smtp" and (not host or not from_addr):
        raise ValueError("SMTP_HOST and SMTP_FROM must be set to send email")

    # Errno 8 "nodename nor servname ..." = DNS cannot resolve host — usually typo or empty host
    if any(c in host for c in (" ", "\n", "\t")):
        raise ValueError(
            "SMTP_HOST must be a single hostname (e.g. smtp.gmail.com) with no spaces"
        )

    html_body = markdown_to_html(markdown_body)
    wrapped_template = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a2e; line-height:1.5; max-width:720px; margin:0 auto; padding:16px; }}
h1 {{ font-size:1.35rem; color:#0f3460; }}
h2 {{ font-size:1.1rem; margin-top:1.25em; }}
blockquote {{ border-left:4px solid #e94560; margin:0.5em 0; padding-left:12px; color:#444; }}
code {{ background:#f4f4f8; padding:2px 6px; border-radius:4px; }}
hr {{ border:none; border-top:1px solid #ddd; margin:1.5em 0; }}
</style></head><body>
__GREETING_HTML__
{html_body}
</body></html>"""

    def _personalized_content(recipient: str) -> tuple[str, str]:
        display_name = _display_name_from_email(recipient)
        greeting_plain = f"Dear {display_name},\n\n"
        greeting_html = f"<p><strong>Dear {display_name},</strong></p>"
        html = wrapped_template.replace("__GREETING_HTML__", greeting_html)
        return greeting_plain + markdown_body, html

    if transport == "mcp":
        from shared.mcp_email_send import send_email_via_mcp

        for recipient in recs:
            plain_body, html_body = _personalized_content(recipient)
            ok = send_email_via_mcp(
                to_email=recipient,
                subject=f"{subject_prefix} — {iso_week}",
                text_body=plain_body,
                html_body=html_body,
            )
            if not ok:
                raise RuntimeError(f"MCP email send failed for recipient: {recipient}")
        return

    try:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            # Send one personalized message per recipient.
            for recipient in recs:
                plain_body, html_body = _personalized_content(recipient)
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"{subject_prefix} — {iso_week}"
                msg["From"] = from_addr
                msg["To"] = recipient
                msg.attach(MIMEText(plain_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))
                smtp.sendmail(from_addr, [recipient], msg.as_string())
    except OSError as e:
        if getattr(e, "errno", None) == 8 or "nodename nor servname" in str(e).lower():
            raise OSError(
                f"Cannot resolve SMTP server hostname {host!r}. "
                "Check SMTP_HOST in .env (e.g. smtp.gmail.com), no typos/spaces, "
                "and that your network/DNS works."
            ) from e
        raise


def send_latest_pulse_email(recipients: list[str] | None = None) -> tuple[str, list[str]]:
    """
    Load the latest ``*_pulse.md`` and email it.

    Returns ``(iso_week, list of recipient emails)``.
    """
    latest = get_latest_pulse()
    if not latest:
        raise FileNotFoundError("No pulse report found in data/reports/")
    iso_week, md = latest
    recs = recipients if recipients is not None else _recipients_from_env()
    send_pulse_email(iso_week=iso_week, markdown_body=md, recipients=recs)
    return iso_week, list(recs)


def send_week_by_email(iso_week: str, recipients: list[str] | None = None) -> list[str]:
    md = read_pulse_markdown(iso_week)
    if md is None:
        raise FileNotFoundError(f"No report for {iso_week}")
    recs = recipients if recipients is not None else _recipients_from_env()
    send_pulse_email(iso_week=iso_week, markdown_body=md, recipients=recs)
    return list(recs)
