"""
phase4_report/report_generator.py — Phase 4: Weekly pulse Markdown (ARCHITECTURE §4).

* Step 4a–4b: Single JSON-mode LLM call (Groq default or Gemini) → overview, theme
  analyses, 3 action ideas.
* Step 4.3: Regex PII safety net via ``pii_scrubber.scrub_pii``.
* Fee block: curated ``prompts/fee_scenarios.json`` (see ``fee_scenarios.py``).

Output: ``data/reports/<week>_pulse.md``
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config
from phase4_report.fee_scenarios import render_fee_section_markdown, select_fee_scenario
from phase4_report.gdoc_payload import (
    build_gdoc_payload,
    format_payload_as_doc_section,
    save_gdoc_payload,
)
from phase4_report.pii_scrubber import PII_PATTERNS, scrub_pii
from shared.llm_clients.gemini_client import generate_gemini_json
from shared.llm_clients.groq_client import generate_json_response

logger = logging.getLogger("weekly_pulse")

SYSTEM_PROMPT = """
You are a product analyst writing a weekly voice-of-customer report for the IndMoney leadership team.

You will receive structured data for this ISO week: top themes, review counts, quotes, and optional week-over-week notes.

Return ONLY valid JSON with this exact shape:
{
  "overview": "string — one-line summary of overall sentiment and tone",
  "themes": [
    {
      "analysis": "string — 2-4 sentences: what users are saying and why it matters"
    }
  ],
  "action_ideas": [
    {
      "theme": "string — must match one of the top theme names",
      "title": "string — short action title",
      "description": "string — specific, implementable in 1-2 sprints",
      "rationale": "string — one sentence why"
    }
  ]
}

Rules:
1. There must be exactly as many objects in "themes" as themes in the user message (same order).
2. There must be exactly 3 objects in "action_ideas", each tied to a distinct top theme.
3. The overview plus all theme analyses combined must be at most 250 words total.
4. Professional, accessible tone. Zero PII in the output (no names, emails, phones, account numbers).
5. Do not invent statistics; only use numbers provided in the user message.
""".strip()


def iso_week_date_range(iso_week: str) -> str:
    """Human-readable range for ISO week label, e.g. ``2026-W12`` → ``March 16–March 22, 2026``."""
    parts = iso_week.split("-W")
    if len(parts) != 2:
        return iso_week
    y, w = int(parts[0]), int(parts[1])
    d0 = date.fromisocalendar(y, w, 1)
    d1 = d0 + timedelta(days=6)
    return f"{d0.strftime('%B %d')}–{d1.strftime('%B %d, %Y')}"


def previous_iso_week(iso_week: str) -> str | None:
    parts = iso_week.split("-W")
    if len(parts) != 2:
        return None
    y, w = int(parts[0]), int(parts[1])
    d = date.fromisocalendar(y, w, 1) - timedelta(days=7)
    py, pw, _ = d.isocalendar()
    return f"{py}-W{pw:02d}"


def _weighted_avg_rating(themes: list[dict]) -> float:
    if not themes:
        return 0.0
    num = sum(int(t.get("review_count", 0)) * float(t.get("avg_rating", 0)) for t in themes)
    den = sum(int(t.get("review_count", 0)) for t in themes)
    if not den:
        return 0.0
    return round(num / den, 2)


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * count / total, 1)


def _count_pii_matches(text: str) -> tuple[int, int]:
    """Returns (total matches, number of patterns that matched at least once)."""
    if not text:
        return 0, 0
    patterns_hit = 0
    total = 0
    for pattern, _ in PII_PATTERNS:
        m = len(re.findall(pattern, text))
        if m:
            patterns_hit += 1
            total += m
    return total, patterns_hit


def _build_user_prompt(
    iso_week: str,
    insights: dict[str, Any],
    prev_insights: dict[str, Any] | None,
) -> str:
    total = int(insights.get("total_reviews") or 0)
    themes = insights.get("top_themes") or []
    w_avg = _weighted_avg_rating(themes)

    lines: list[str] = []
    lines.append(f"Week: {iso_week} ({iso_week_date_range(iso_week)})")
    lines.append(f"Total reviews analyzed (this week window): {total}")
    lines.append(f"Approx. weighted average rating across top themes: {w_avg}★")

    if prev_insights:
        pt = prev_insights.get("top_themes") or []
        prev_total = int(prev_insights.get("total_reviews") or 0)
        prev_w = _weighted_avg_rating(pt)
        lines.append(
            f"Previous week reference: {prev_insights.get('iso_week', '?')} — "
            f"{prev_total} reviews, weighted avg {prev_w}★"
        )
        prev_names = [str(t.get("theme_name", "")) for t in pt[: config.TOP_THEMES]]
        cur_names = [str(t.get("theme_name", "")) for t in themes]
        dropped = [n for n in prev_names if n and n not in cur_names]
        new_entrants = [n for n in cur_names if n and n not in prev_names]
        if dropped:
            lines.append(f"Themes that dropped out of top {len(themes)} vs prior week: {', '.join(dropped)}")
        if new_entrants:
            lines.append(f"New or re-entered themes in top {len(themes)}: {', '.join(new_entrants)}")
    else:
        lines.append("Week-over-week: no prior week insights file found; omit deep WoW commentary.")

    lines.append("")
    lines.append("Top themes (in order):")
    for i, t in enumerate(themes, start=1):
        name = t.get("theme_name", "")
        rc = int(t.get("review_count", 0))
        ar = float(t.get("avg_rating", 0))
        pct = _pct(rc, total)
        quote = str(t.get("representative_quote", "") or "").replace("\n", " ")
        sent = t.get("sentiment") or {}
        lines.append(f'{i}. "{name}" — {rc} reviews ({pct}% of weekly total) — avg {ar}★')
        lines.append(
            f"   Sentiment split: positive={sent.get('positive', 0)}, "
            f"neutral={sent.get('neutral', 0)}, negative={sent.get('negative', 0)}"
        )
        lines.append(f'   Representative quote: "{quote}"')

    return "\n".join(lines).strip()


def _report_llm_provider(override: str | None) -> str:
    if override is not None:
        return override.strip().lower()
    return getattr(config, "PHASE4_REPORT_LLM", "groq").lower()


def _run_report_llm(user_prompt: str, provider: str) -> tuple[dict | None, str, str]:
    p = provider.lower()
    if p in ("gemini", "google"):
        try:
            resp = generate_gemini_json(SYSTEM_PROMPT, user_prompt)
            return resp, "gemini", config.GEMINI_MODEL
        except Exception as e:
            logger.error(f"Gemini report LLM failed: {e}", exc_info=True)
            return None, "gemini", config.GEMINI_MODEL

    model = getattr(config, "PHASE4_GROQ_MODEL", config.GROQ_MODEL)
    try:
        resp = generate_json_response(SYSTEM_PROMPT, user_prompt, model=model)
        return resp, "groq", model
    except Exception as e:
        logger.error(f"Groq report LLM failed: {e}", exc_info=True)
        return None, "groq", model


def _validate_llm_payload(
    raw: dict[str, Any] | None,
    num_themes: int,
    top_theme_names: list[str] | None = None,
) -> dict[str, Any] | None:
    if not raw or not isinstance(raw, dict):
        return None
    overview = raw.get("overview")
    themes = raw.get("themes")
    actions = raw.get("action_ideas")
    if not isinstance(overview, str) or not overview.strip():
        return None
    if not isinstance(themes, list) or len(themes) != num_themes:
        return None
    for t in themes:
        if not isinstance(t, dict) or not str(t.get("analysis", "")).strip():
            return None
    if not isinstance(actions, list) or len(actions) != 3:
        return None
    normalized_top = {str(x).strip().lower() for x in (top_theme_names or []) if str(x).strip()}
    seen_action_themes: set[str] = set()
    for a in actions:
        if not isinstance(a, dict):
            return None
        for k in ("theme", "title", "description", "rationale"):
            if not str(a.get(k, "")).strip():
                return None
        at = str(a.get("theme", "")).strip().lower()
        if at in seen_action_themes:
            return None
        seen_action_themes.add(at)
        if normalized_top and at not in normalized_top:
            return None
    return raw


def _word_count_note(overview: str, theme_analyses: list[str]) -> int:
    text = overview + " " + " ".join(theme_analyses)
    return len(text.split())


def _render_markdown(
    iso_week: str,
    insights: dict[str, Any],
    llm: dict[str, Any],
    *,
    phase3_llm: str,
    phase4_llm: str,
    phase4_model: str,
    fee_section_markdown: str | None = None,
) -> str:
    total = int(insights.get("total_reviews") or 0)
    themes = insights.get("top_themes") or []
    overview = str(llm.get("overview", "")).strip()
    analyses = [str(x.get("analysis", "")).strip() for x in (llm.get("themes") or [])]
    actions = llm.get("action_ideas") or []

    header_range = iso_week_date_range(iso_week)
    lines: list[str] = [
        "# 📊 WeeklyProductPulse — IndMoney",
        f"## Week {iso_week} | {header_range}",
        "",
        "### 📈 Overview",
        overview,
        "",
        "### 🔍 Top Themes",
        "",
    ]

    for i, t in enumerate(themes):
        name = str(t.get("theme_name", ""))
        rc = int(t.get("review_count", 0))
        ar = float(t.get("avg_rating", 0))
        pct = _pct(rc, total)
        quote = str(t.get("representative_quote", "") or "").strip()
        analysis = analyses[i] if i < len(analyses) else ""
        lines.append(f"#### {i + 1}. {name} ({rc} reviews · {pct}% · ★{ar})")
        lines.append(f"> \"{quote}\"")
        lines.append("")
        lines.append(analysis)
        lines.append("")

    lines.append("### 💡 Action Ideas")
    for j, a in enumerate(actions, start=1):
        th = str(a.get("theme", ""))
        title = str(a.get("title", ""))
        desc = str(a.get("description", ""))
        rat = str(a.get("rationale", ""))
        body = f"**[{th}] — {title}**: {desc.strip()} Rationale: {rat.strip()}"
        if not body.endswith("."):
            body += "."
        lines.append(f"{j}. {body}")

    if fee_section_markdown:
        lines.append("")
        lines.append(fee_section_markdown.rstrip())
        lines.append("")

    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    ts = now_ist.strftime("%Y-%m-%d %H:%M IST")
    powered = f"{phase3_llm} (quotes) + {phase4_llm} ({phase4_model})"
    lines.extend(
        [
            "",
            "---",
            f"*Generated on {ts} · {total:,} reviews analyzed · Powered by {powered}*",
            "",
        ]
    )
    return "\n".join(lines)


def generate_weekly_report(
    iso_week: str,
    *,
    report_llm_provider: str | None = None,
    fee_scenario_id: str | None = None,
    google_doc_append: bool | None = None,
) -> Path | None:
    """
    Read ``<week>_insights.json``, call report LLM, scrub PII, write ``<week>_pulse.md``.

    Also writes ``<week>_gdoc_payload.json`` for Google Docs (MCP / API). Optional
    append to a Google Doc when ``GOOGLE_DOCS_APPEND_ENABLED`` and credentials are set.

    ``google_doc_append``: override append (``True``/``False``); ``None`` uses config.

    Returns path to the Markdown file, or None on failure.
    """
    provider = _report_llm_provider(report_llm_provider)
    do_gdoc_append = (
        config.GOOGLE_DOCS_APPEND_ENABLED if google_doc_append is None else google_doc_append
    )
    insights_path = config.TAGGED_DIR / f"{iso_week}_insights.json"
    if not insights_path.exists():
        logger.error(f"Phase 4: insights file not found: {insights_path}")
        return None

    with open(insights_path, encoding="utf-8") as f:
        insights: dict[str, Any] = json.load(f)

    themes = insights.get("top_themes") or []
    if not themes:
        logger.error("Phase 4: no top_themes in insights JSON.")
        return None

    prev_week = previous_iso_week(iso_week)
    prev_insights: dict[str, Any] | None = None
    if prev_week:
        ppath = config.TAGGED_DIR / f"{prev_week}_insights.json"
        if ppath.exists():
            with open(ppath, encoding="utf-8") as pf:
                prev_insights = json.load(pf)

    user_prompt = _build_user_prompt(iso_week, insights, prev_insights)
    est_tokens = max(1, (len(SYSTEM_PROMPT) + len(user_prompt)) // 4)

    logger.info(
        "report_generation_start",
        extra={
            "phase": "report_generator",
            "data": {
                "iso_week": iso_week,
                "quote_llm": provider,
                "input_token_est": est_tokens,
            },
        },
    )

    raw, _p, model_used = _run_report_llm(user_prompt, provider)
    llm_payload = _validate_llm_payload(
        raw,
        len(themes),
        top_theme_names=[str(t.get("theme_name", "")) for t in themes],
    )
    if llm_payload is None:
        logger.error("Phase 4: report LLM returned invalid or incomplete JSON.")
        return None

    overview = str(llm_payload.get("overview", ""))
    analyses = [str(x.get("analysis", "")) for x in (llm_payload.get("themes") or [])]
    wc = _word_count_note(overview, analyses)
    under_cap = wc <= config.MAX_REPORT_WORDS
    logger.info(
        "report_generated",
        extra={
            "phase": "report_generator",
            "data": {
                "iso_week": iso_week,
                "word_count": wc,
                "under_250_limit": under_cap,
            },
        },
    )
    if not under_cap:
        logger.warning(
            f"Weekly note body is {wc} words (limit {config.MAX_REPORT_WORDS}); "
            "consider tightening prompts or regenerating."
        )

    q3 = str(insights.get("quote_llm") or "").strip().lower()
    if not q3:
        m = str(insights.get("model") or "")
        q3 = "gemini" if "gemini" in m.lower() else "groq"
    phase3_llm = q3

    fee_section_md: str | None = None
    fee_pick = select_fee_scenario(iso_week, scenario_id=fee_scenario_id)
    if fee_pick:
        fee_section_md = render_fee_section_markdown(fee_pick)
        logger.info(
            "fee_scenario_selected",
            extra={
                "phase": "report_generator",
                "data": {
                    "iso_week": iso_week,
                    "fee_scenario_id": fee_pick.get("id"),
                    "fee_category": fee_pick.get("category"),
                },
            },
        )

    md_before = _render_markdown(
        iso_week,
        insights,
        llm_payload,
        phase3_llm=phase3_llm,
        phase4_llm=provider,
        phase4_model=model_used,
        fee_section_markdown=fee_section_md,
    )

    matches, pat_hit = _count_pii_matches(md_before)
    md_after = scrub_pii(md_before)
    redactions = matches  # upper bound; scrub may merge overlaps
    logger.info(
        "pii_scrub_applied",
        extra={
            "phase": "report_generator",
            "data": {
                "iso_week": iso_week,
                "redactions_count": redactions,
                "patterns_matched": pat_hit,
            },
        },
    )

    out_path = config.REPORTS_DIR / f"{iso_week}_pulse.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as wf:
        wf.write(md_after)

    size_kb = round(out_path.stat().st_size / 1024, 1)
    logger.info(
        "report_saved",
        extra={
            "phase": "report_generator",
            "data": {
                "iso_week": iso_week,
                "file_path": str(out_path),
                "file_size_kb": size_kb,
            },
        },
    )

    gdoc_payload = build_gdoc_payload(iso_week, md_after, fee_pick)
    gdoc_path = save_gdoc_payload(iso_week, gdoc_payload)
    logger.info(
        "gdoc_payload_saved",
        extra={
            "phase": "report_generator",
            "data": {"iso_week": iso_week, "path": str(gdoc_path)},
        },
    )

    if do_gdoc_append and config.GOOGLE_DOCS_DOCUMENT_ID:
        formatted = format_payload_as_doc_section(gdoc_payload)
        transport = getattr(config, "GOOGLE_DOCS_APPEND_TRANSPORT", "direct").lower()
        if transport == "mcp":
            from shared.mcp_google_docs_append import try_append_via_mcp

            ok = try_append_via_mcp(config.GOOGLE_DOCS_DOCUMENT_ID, formatted)
        else:
            from shared.google_docs_client import try_append_payload

            ok = try_append_payload(config.GOOGLE_DOCS_DOCUMENT_ID, formatted)

        if ok:
            logger.info(
                "google_docs_append_ok",
                extra={
                    "phase": "report_generator",
                    "data": {
                        "document_id": config.GOOGLE_DOCS_DOCUMENT_ID,
                        "transport": transport,
                    },
                },
            )
        else:
            logger.error(
                "Phase 4 failed: Google Docs append was requested but did not succeed."
            )
            return None
    elif do_gdoc_append and not config.GOOGLE_DOCS_DOCUMENT_ID:
        logger.error(
            "Phase 4 failed: Google Docs append was requested but GOOGLE_DOCS_DOCUMENT_ID is empty."
        )
        return None

    logger.info(f"Phase 4 complete. Saved -> {out_path.name}")
    return out_path


if __name__ == "__main__":
    from phase1_ingestion.scraper import get_current_iso_week
    from shared.logger import init_logger

    parser = argparse.ArgumentParser(description="Phase 4: Generate weekly pulse Markdown report")
    parser.add_argument("--week", default=get_current_iso_week(), help="ISO week, e.g. 2026-W12")
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    parser.add_argument(
        "--provider",
        choices=("groq", "gemini"),
        default=None,
        help="Report LLM: groq (default) or gemini (overrides PHASE4_REPORT_LLM)",
    )
    parser.add_argument(
        "--fee-scenario-id",
        default=None,
        help="Pin fee block scenario id from prompts/fee_scenarios.json (overrides FEE_SCENARIO_ID)",
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--google-doc-append",
        action="store_true",
        help="Append to Google Doc (needs GOOGLE_DOCS_DOCUMENT_ID + credentials)",
    )
    g.add_argument(
        "--no-google-doc-append",
        action="store_true",
        help="Skip Google Doc append even if enabled in .env",
    )
    args = parser.parse_args()
    init_logger(f"report_generator_{args.week}", args.week, args.log_level)
    gdoc_override: bool | None = None
    if args.google_doc_append:
        gdoc_override = True
    elif args.no_google_doc_append:
        gdoc_override = False
    out = generate_weekly_report(
        args.week,
        report_llm_provider=args.provider,
        fee_scenario_id=args.fee_scenario_id,
        google_doc_append=gdoc_override,
    )
    sys.exit(0 if out is not None else 1)
