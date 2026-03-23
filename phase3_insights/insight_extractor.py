"""
phase3_insights/insight_extractor.py — Phase 3: Insight extraction (per ARCHITECTURE.md).

Step 3a (Python, no LLM)
-------------------------
* Take top ``TOP_THEMES`` themes from ``<week>_theme_summary.json``.
* Enrich each with sentiment breakdown (positive / neutral / negative by star rating).
* For quote LLM input: take the **top N most-upvoted** reviews per theme
  (``TOP_REVIEWS_PER_THEME``), sorted by ``thumbs_up`` descending.

Step 3b (LLM quote selection)
----------------------------
* Default: **Groq** (same family as Phase 2) — ``PHASE3_QUOTE_LLM=groq``.
* Alternative: **Gemini** — set ``PHASE3_QUOTE_LLM=gemini``.
* Single JSON-mode call: exactly one verbatim quote per theme, PII redacted in-model.
* Post-process: ``phase4_report.pii_scrubber.scrub_pii`` on each quote (safety net).

Output: ``data/tagged/<week>_insights.json``
"""

from __future__ import annotations

import json
import logging
import argparse
from typing import Any

import config
from phase1_ingestion.scraper import get_current_iso_week
from phase4_report.pii_scrubber import scrub_pii
from shared.llm_clients.gemini_client import generate_gemini_json
from shared.llm_clients.groq_client import generate_json_response

logger = logging.getLogger("weekly_pulse")

SYSTEM_PROMPT = """
You are selecting representative user quotes for a weekly executive product report for IndMoney (Play Store reviews).

Rules:
1. You will receive exactly three themes. Select EXACTLY ONE quote per theme — three quotes total.
2. Each quote MUST be verbatim from one of the candidate review texts provided for that theme (do NOT paraphrase or invent text).
3. REMOVE any PII: names, email addresses, phone numbers, account numbers, transaction IDs, or any personally identifiable information. Replace PII with [REDACTED].
4. Prefer quotes that are vivid, specific, and capture the user's experience.
5. Prefer quotes from reviews with higher thumbs_up (more people agreed).
6. Keep each quote under 50 words. If the original is longer, extract the most impactful sentence or fragment only.
7. For each quote, set "review_id" to the review_id of the candidate review you quoted from (must match exactly one candidate).

Return ONLY a valid JSON object with this exact shape:
{
  "quotes": [
    {
      "theme_name": "string",
      "review_id": "string",
      "quote": "string",
      "rating": number,
      "thumbs_up": number,
      "pii_redacted": true
    }
  ]
}

Use the theme_name strings exactly as provided in the user message. There must be exactly three objects in "quotes", in the same theme order as given.
""".strip()


def _quote_llm_provider(override: str | None) -> str:
    if override is not None:
        return override.strip().lower()
    return getattr(config, "PHASE3_QUOTE_LLM", "groq").lower()


def _run_quote_llm(user_prompt: str, provider: str) -> tuple[dict | None, str, str]:
    """
    Call Groq or Gemini for quote JSON. Returns (response dict or None, provider id, model id).
    """
    p = provider.lower()
    if p in ("gemini", "google"):
        try:
            resp = generate_gemini_json(SYSTEM_PROMPT, user_prompt)
            return resp, "gemini", config.GEMINI_MODEL
        except Exception as e:
            logger.error(f"Gemini quote selection failed: {e}", exc_info=True)
            return None, "gemini", config.GEMINI_MODEL

    # Default: Groq
    try:
        model = getattr(config, "PHASE3_GROQ_MODEL", config.GROQ_MODEL)
        resp = generate_json_response(SYSTEM_PROMPT, user_prompt, model=model)
        return resp, "groq", model
    except Exception as e:
        logger.error(f"Groq quote selection failed: {e}", exc_info=True)
        return None, "groq", getattr(config, "PHASE3_GROQ_MODEL", config.GROQ_MODEL)


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def compute_sentiment(reviews: list[dict]) -> dict[str, int]:
    """Positive (>=4), neutral (3), negative (<=2) — per ARCHITECTURE §3.1."""
    positive = neutral = negative = 0
    for r in reviews:
        rating = _safe_int(r.get("rating"), 0)
        if rating >= 4:
            positive += 1
        elif rating == 3:
            neutral += 1
        else:
            negative += 1
    return {"positive": positive, "neutral": neutral, "negative": negative}


def avg_rating(reviews: list[dict]) -> float:
    if not reviews:
        return 0.0
    s = sum(_safe_int(r.get("rating"), 0) for r in reviews)
    return round(s / len(reviews), 2)


def top_reviews_by_thumbs_up(reviews: list[dict], limit: int) -> list[dict]:
    """Top ``limit`` reviews by thumbs_up descending (tie-break: higher rating)."""
    if not reviews:
        return []
    sorted_reviews = sorted(
        reviews,
        key=lambda r: (-_safe_int(r.get("thumbs_up"), 0), -_safe_int(r.get("rating"), 0)),
    )
    return sorted_reviews[:limit]


def _build_user_prompt(themes_payload: list[dict]) -> str:
    """Human-readable block matching ARCHITECTURE §3.2 style."""
    lines: list[str] = []
    for i, t in enumerate(themes_payload, start=1):
        name = t["theme_name"]
        rc = t["review_count"]
        ar = t["avg_rating"]
        sent = t["sentiment"]
        lines.append(
            f'Theme {i}: "{name}" ({rc} reviews, avg {ar}★)'
        )
        lines.append(
            f"  Sentiment: positive={sent['positive']}, neutral={sent['neutral']}, negative={sent['negative']}"
        )
        lines.append("  Top reviews (by thumbs up):")
        for c in t["candidates"]:
            rid = c.get("review_id", "")
            rating = _safe_int(c.get("rating"), 0)
            tu = _safe_int(c.get("thumbs_up"), 0)
            text = (c.get("text") or "").replace("\n", " ").strip()
            lines.append(f'  - [{rid}] ★{rating} | 👍 {tu} | "{text}"')
        lines.append("")
    return "\n".join(lines).strip()


def _normalize_quote_entry(q: dict) -> dict[str, Any]:
    """Accept either theme_name or theme from model output."""
    name = q.get("theme_name") or q.get("theme") or ""
    return {
        "theme_name": str(name).strip(),
        "review_id": str(q.get("review_id", "") or "").strip(),
        "quote": str(q.get("quote", "") or "").strip(),
        "rating": _safe_int(q.get("rating"), -1),
        "thumbs_up": _safe_int(q.get("thumbs_up"), 0),
        "pii_redacted": bool(q.get("pii_redacted", False)),
    }


def _match_quote_to_theme(
    theme_name: str,
    quotes_by_theme: dict[str, dict],
) -> dict | None:
    if theme_name in quotes_by_theme:
        return quotes_by_theme[theme_name]
    tn_lower = theme_name.lower().strip()
    for k, v in quotes_by_theme.items():
        if k.lower().strip() == tn_lower:
            return v
    return None


def _fallback_from_candidates(candidates: list[dict]) -> dict[str, Any]:
    """Pick highest thumbs_up review as quote source."""
    if not candidates:
        return {
            "quote": "",
            "rating": -1,
            "thumbs_up": 0,
            "review_id": "",
        }
    best = max(candidates, key=lambda r: _safe_int(r.get("thumbs_up"), 0))
    text = str(best.get("text", "") or "")
    # Trim for display similar to LLM constraint
    words = text.split()
    if len(words) > 50:
        text = " ".join(words[:50]) + "…"
    return {
        "quote": text,
        "rating": _safe_int(best.get("rating"), -1),
        "thumbs_up": _safe_int(best.get("thumbs_up"), 0),
        "review_id": str(best.get("review_id", "") or ""),
    }


def _llm_quotes_complete_for_themes(
    themes_payload: list[dict],
    quotes_by_theme: dict[str, dict],
) -> bool:
    """True if every theme has a non-empty LLM quote."""
    for tp in themes_payload:
        name = tp["theme_name"]
        picked = _match_quote_to_theme(name, quotes_by_theme)
        if not picked or not str(picked.get("quote", "")).strip():
            return False
    return True


def _is_valid_theme_quote(picked: dict, candidates: list[dict]) -> bool:
    """
    Validate a model-selected quote for a theme.

    A valid quote must include non-empty text and, when review_id is provided,
    it must match one of the candidate review IDs for that theme.
    """
    if not picked or not str(picked.get("quote", "")).strip():
        return False
    rid = str(picked.get("review_id", "") or "").strip()
    if not rid:
        return False
    candidate_ids = {str(c.get("review_id", "") or "").strip() for c in candidates}
    return rid in candidate_ids


def extract_insights(
    iso_week: str,
    *,
    allow_fallback: bool | None = None,
    quote_llm_provider: str | None = None,
) -> Any | None:
    """
    Run Phase 3: enrich top themes, call Groq or Gemini for quotes, apply PII scrub, write insights JSON.
    Returns path to ``<week>_insights.json`` or None on failure.

    If ``allow_fallback`` is False (or ``config.PHASE3_ALLOW_FALLBACK`` is False), the quote LLM must
    return a valid quote for every theme; otherwise returns None and does not write the file.

    ``quote_llm_provider``: ``\"groq\"`` | ``\"gemini\"`` — overrides ``config.PHASE3_QUOTE_LLM``.
    """
    allow_fb = config.PHASE3_ALLOW_FALLBACK if allow_fallback is None else allow_fallback
    llm_provider = _quote_llm_provider(quote_llm_provider)
    summary_path = config.TAGGED_DIR / f"{iso_week}_theme_summary.json"

    if not summary_path.exists():
        logger.error(f"Cannot extract insights. File not found: {summary_path}")
        return None

    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_themes = data.get("themes", [])[: config.TOP_THEMES]
    if not raw_themes:
        logger.error("No themes found in summary to extract insights from.")
        return None

    # --- Step 3a: enrich (Python only) ---
    themes_payload: list[dict] = []
    total_candidates = 0

    for theme in raw_themes:
        reviews = list(theme.get("reviews") or [])
        sentiment = compute_sentiment(reviews)
        ar = avg_rating(reviews)
        candidates = top_reviews_by_thumbs_up(reviews, config.TOP_REVIEWS_PER_THEME)
        total_candidates += len(candidates)

        # Normalize candidate keys for the model (text field)
        norm_candidates = []
        for c in candidates:
            norm_candidates.append({
                "review_id": str(c.get("review_id", "")),
                "rating": _safe_int(c.get("rating"), 0),
                "thumbs_up": _safe_int(c.get("thumbs_up"), 0),
                "text": str(c.get("text", "") or ""),
            })

        themes_payload.append({
            "theme_name": theme["theme_name"],
            "review_count": int(theme["review_count"]),
            "avg_rating": ar,
            "sentiment": sentiment,
            "candidates": norm_candidates,
        })

    logger.info(
        "quote_selection_start",
        extra={
            "phase": "insight_extractor",
            "data": {
                "iso_week": iso_week,
                "num_themes": len(themes_payload),
                "num_candidate_reviews": total_candidates,
                "quote_llm": llm_provider,
            },
        },
    )

    user_prompt = _build_user_prompt(themes_payload)

    # --- Step 3b: Groq or Gemini ---
    response, _prov_used, model_used = _run_quote_llm(user_prompt, llm_provider)

    if response is None and not allow_fb:
        logger.error(
            f"Phase 3 aborted: {llm_provider} quote LLM call failed and fallback is disabled."
        )
        return None

    quotes_list: list[dict] = []
    if response and isinstance(response, dict) and "quotes" in response:
        raw_quotes = response["quotes"]
        if isinstance(raw_quotes, list):
            quotes_list = [_normalize_quote_entry(q) for q in raw_quotes if isinstance(q, dict)]

    quotes_by_theme = {q["theme_name"]: q for q in quotes_list if q.get("theme_name")}

    if not allow_fb and not _llm_quotes_complete_for_themes(themes_payload, quotes_by_theme):
        logger.error(
            "Phase 3 aborted: quote LLM did not return a complete, valid quote for each theme "
            "(fallback disabled). Check logs and retry."
        )
        return None

    insights_top_themes: list[dict] = []
    redaction_count = 0

    for tp in themes_payload:
        name = tp["theme_name"]
        candidates = tp["candidates"]
        picked = _match_quote_to_theme(name, quotes_by_theme)

        if not _is_valid_theme_quote(picked or {}, candidates):
            if not allow_fb:
                # Should not reach: validated above
                logger.error(f"Internal error: missing quote for theme {name!r}")
                return None
            logger.warning(
                f"Invalid/missing LLM quote for theme {name!r}; using fallback from candidates."
            )
            fb = _fallback_from_candidates(candidates)
            quote_text = fb["quote"]
            q_rating = fb["rating"]
            q_thumbs = fb["thumbs_up"]
            llm_pii = False
        else:
            quote_text = picked["quote"]
            q_rating = picked["rating"]
            q_thumbs = picked["thumbs_up"]
            llm_pii = picked.get("pii_redacted", False)

        before_scrub = quote_text
        quote_text = scrub_pii(quote_text)
        scrub_changed = before_scrub != quote_text
        if scrub_changed:
            redaction_count += 1

        insights_top_themes.append({
            "theme_name": name,
            "review_count": tp["review_count"],
            "avg_rating": tp["avg_rating"],
            "sentiment": tp["sentiment"],
            "representative_quote": quote_text,
            "quote_rating": q_rating,
            "quote_thumbs_up": q_thumbs,
            "pii_redacted": bool(llm_pii or scrub_changed),
        })

    out_payload = {
        "iso_week": iso_week,
        "total_reviews": data.get("total_reviews"),
        "phase": "phase3_insight_extraction",
        "quote_llm": llm_provider,
        "model": model_used,
        "top_themes": insights_top_themes,
    }

    out_path = config.TAGGED_DIR / f"{iso_week}_insights.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, indent=2, ensure_ascii=False)

    logger.info(
        "quotes_selected",
        extra={
            "phase": "insight_extractor",
            "data": {
                "iso_week": iso_week,
                "quotes": [t["theme_name"] for t in insights_top_themes],
                "pii_redactions": redaction_count,
                "output_path": str(out_path),
            },
        },
    )
    logger.info(f"Phase 3 Insight Extraction complete. Saved -> {out_path.name}")
    return out_path


if __name__ == "__main__":
    import sys

    from shared.logger import init_logger

    parser = argparse.ArgumentParser(description="Phase 3: Extract user quotes via Gemini")
    parser.add_argument("--week", default=get_current_iso_week(), help="ISO week target")
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Require quote LLM to succeed for every theme; do not write file on failure (overrides PHASE3_ALLOW_FALLBACK)",
    )
    parser.add_argument(
        "--provider",
        choices=("groq", "gemini"),
        default=None,
        help="Quote LLM: groq (default) or gemini (overrides PHASE3_QUOTE_LLM)",
    )
    args = parser.parse_args()

    init_logger(f"insight_extractor_{args.week}", args.week, args.log_level)
    out = extract_insights(
        args.week,
        allow_fallback=False if args.no_fallback else None,
        quote_llm_provider=args.provider,
    )
    sys.exit(0 if out is not None else 1)
