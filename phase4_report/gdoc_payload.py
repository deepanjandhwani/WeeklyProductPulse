"""
Build a stable JSON payload for Google Docs (MCP, API, or manual paste).

Written to ``data/reports/<iso_week>_gdoc_payload.json`` after each successful Phase 4 run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def build_gdoc_payload(
    iso_week: str,
    pulse_markdown: str,
    fee: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Shape (flat keys for tooling):

    * ``date`` — run date (UTC) ``YYYY-MM-DD``
    * ``weekly_pulse`` — full pulse Markdown (PII-scrubbed)
    * ``fee_scenario`` — scenario title string (empty if fee block off)
    * ``explanation_bullets`` — list of fee bullet strings
    * ``source_links`` — list of ``{"label", "url"}`` objects

    Also includes ``iso_week`` and ``generated_at_utc`` for auditing.
    """
    now = datetime.now(timezone.utc)
    bullets: list[str] = []
    links: list[dict[str, str]] = []
    fee_title = ""

    if fee:
        fee_title = str(fee.get("title", "") or "").strip()
        bullets = [str(b).strip() for b in (fee.get("bullets") or []) if str(b).strip()]
        for s in fee.get("sources") or []:
            if isinstance(s, dict) and s.get("url"):
                links.append(
                    {
                        "label": str(s.get("label", "")).strip(),
                        "url": str(s.get("url", "")).strip(),
                    }
                )

    return {
        "iso_week": iso_week,
        "date": now.date().isoformat(),
        "generated_at_utc": now.isoformat(),
        "weekly_pulse": pulse_markdown,
        "fee_scenario": fee_title,
        "explanation_bullets": bullets,
        "source_links": links,
    }


def save_gdoc_payload(iso_week: str, payload: dict[str, Any]) -> Path:
    path = config.REPORTS_DIR / f"{iso_week}_gdoc_payload.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def format_payload_as_doc_section(payload: dict[str, Any]) -> str:
    """Human-readable block for Google Docs append (API or copy-paste)."""
    lines: list[str] = [
        f"━━ WeeklyProductPulse — {payload.get('iso_week', '')} | {payload.get('date', '')} ━━",
        "",
        payload.get("weekly_pulse") or "",
        "",
        "— Fee scenario (facts) —",
        str(payload.get("fee_scenario") or "(fee section disabled or unavailable)"),
        "",
    ]
    for b in payload.get("explanation_bullets") or []:
        lines.append(f"• {b}")
    lines.append("")
    lines.append("— Official sources —")
    for i, s in enumerate(payload.get("source_links") or [], start=1):
        if isinstance(s, dict):
            lines.append(f"{i}. {s.get('label', '')} — {s.get('url', '')}")
        else:
            lines.append(f"{i}. {s}")
    lines.append("")
    return "\n".join(lines)
