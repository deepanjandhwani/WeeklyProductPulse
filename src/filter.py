"""
src/filter.py — Review cleaning and filtering for WeeklyProductPulse.

Responsibilities
----------------
* Apply the ≥10-word constraint (architecture C2).
* Enforce the 10-week date window (architecture C5).
* Normalise raw Play Store dicts into the canonical review schema.
* Return clean records ready for CSV persistence.

Usage (standalone)
------------------
    python -m src.filter --week 2026-W11
"""

import argparse
import logging
from datetime import datetime, timedelta, timezone

import config

logger = logging.getLogger("weekly_pulse")


# ── Schema constants ───────────────────────────────────────────────────────────

REVIEW_COLUMNS = [
    "review_id",
    "user_name",        # Kept internally; NEVER surfaces in LLM output or reports
    "review_text",
    "rating",
    "thumbs_up_count",
    "review_date",      # YYYY-MM-DD string
    "reply_text",
    "word_count",
    "iso_week",         # e.g. '2026-W11'
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime, even if the input is naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_week_label(dt: datetime) -> str:
    """Return ISO-week label string for a given datetime, e.g. '2026-W11'."""
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _word_count(text: str) -> int:
    """Count whitespace-delimited words in text."""
    return len(text.split())


# ── Main filter function ───────────────────────────────────────────────────────

def filter_reviews(
    raw_reviews: list[dict],
    *,
    cutoff_date: datetime | None = None,
) -> tuple[list[dict], dict]:
    """
    Clean and filter raw Play Store review dicts into the canonical schema.

    Filtering rules applied:
    1. Skip reviews with fewer than `config.MIN_WORD_COUNT` words  (C2).
    2. Skip reviews older than `config.LOOKBACK_WEEKS` weeks       (C5).
    3. Skip reviews with missing or empty review text.

    Args:
        raw_reviews:  List of raw dicts from google-play-scraper.
        cutoff_date:  Earliest allowed review date (UTC). Defaults to
                      `now - LOOKBACK_WEEKS weeks`. Pass explicitly in tests.

    Returns:
        (filtered_reviews, stats_dict)
        filtered_reviews — list of dicts matching REVIEW_COLUMNS schema.
        stats_dict — counts for logging & debugging.
    """
    if cutoff_date is None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=config.LOOKBACK_WEEKS)

    filtered: list[dict] = []
    stats = {
        "input_count":      len(raw_reviews),
        "skipped_no_text":  0,
        "skipped_too_short": 0,
        "skipped_too_old":  0,
        "passed":           0,
    }

    for r in raw_reviews:
        text: str = (r.get("content") or "").strip()

        # ── Guard 1: empty review text ─────────────────────────────────────────
        if not text:
            stats["skipped_no_text"] += 1
            logger.debug(
                f"Skipped review (no text): id={r.get('reviewId')}",
                extra={"phase": "filter"},
            )
            continue

        wc = _word_count(text)

        # ── Guard 2: too short (C2) ────────────────────────────────────────────
        if wc < config.MIN_WORD_COUNT:
            stats["skipped_too_short"] += 1
            logger.debug(
                f"Skipped review (too short, {wc} words): id={r.get('reviewId')}",
                extra={"phase": "filter"},
            )
            continue

        # ── Guard 3: outside the lookback window (C5) ─────────────────────────
        raw_date: datetime | None = r.get("at")
        if raw_date is None:
            stats["skipped_no_text"] += 1   # count as malformed
            continue
        review_dt = _to_utc(raw_date)
        if review_dt < cutoff_date:
            stats["skipped_too_old"] += 1
            logger.debug(
                f"Skipped review (too old, {review_dt.date()}): id={r.get('reviewId')}",
                extra={"phase": "filter"},
            )
            continue

        # ── Passed all filters — normalise to schema ───────────────────────────
        filtered.append({
            "review_id":       r.get("reviewId", ""),
            "user_name":       r.get("userName", ""),
            "review_text":     text,
            "rating":          int(r.get("score", 3)),
            "thumbs_up_count": int(r.get("thumbsUpCount", 0)),
            "review_date":     review_dt.strftime("%Y-%m-%d"),
            "reply_text":      (r.get("replyContent") or "").strip(),
            "word_count":      wc,
            "iso_week":        _iso_week_label(review_dt),
        })
        stats["passed"] += 1

    logger.info(
        f"Filter complete · "
        f"input={stats['input_count']} · "
        f"passed={stats['passed']} · "
        f"skipped_short={stats['skipped_too_short']} · "
        f"skipped_old={stats['skipped_too_old']} · "
        f"skipped_no_text={stats['skipped_no_text']}",
        extra={"phase": "filter", "data": stats},
    )

    return filtered, stats


# ── CLI entry-point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from src.scraper import fetch_reviews_for_week, get_current_iso_week
    from src.logger import init_logger

    parser = argparse.ArgumentParser(description="Scrape and filter reviews for a given ISO week.")
    parser.add_argument("--week", default=get_current_iso_week(), help="ISO week, e.g. 2026-W11")
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    args = parser.parse_args()

    init_logger(f"dev_{args.week}", args.week, args.log_level)

    raw = fetch_reviews_for_week(args.week)
    clean, stats = filter_reviews(raw)

    print(f"\n=== Filter Results for {args.week} ===")
    print(json.dumps(stats, indent=2))
    if clean:
        sample = clean[0]
        print(f"\nSample filtered review:")
        print(f"  ★{sample['rating']} | 👍{sample['thumbs_up_count']} | {sample['review_text'][:100]}")
