"""
phase1_ingestion/scraper.py — Play Store review fetcher for IndMoney (in.indwealth).

Responsibilities
----------------
* Fetch reviews for a given ISO-week date range using google-play-scraper.
* Sort by NEWEST so recent chronological feedback is captured first.
* Return raw review dicts — filtering is the responsibility of filter.py.

Usage (standalone)
------------------
    python -m phase1_ingestion.scraper --week 2026-W11
    python -m phase1_ingestion.scraper --week 2026-W11 --log-level DEBUG
"""

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from google_play_scraper import Sort, reviews as gps_reviews
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

import config
from shared.logger import init_logger

logger = logging.getLogger("weekly_pulse")


# ── ISO-week helpers ───────────────────────────────────────────────────────────

def iso_week_to_date_range(iso_week: str) -> tuple[datetime, datetime]:
    """
    Convert an ISO-week string (e.g. '2026-W11') to a (start, end) datetime pair.

    Returns:
        start: Monday 00:00:00 UTC of that week
        end:   Sunday 23:59:59 UTC of that week
    """
    year, week_num = iso_week.split("-W")
    # %G-%V-%u: ISO year, ISO week number, weekday (1=Monday)
    start = datetime.strptime(f"{year}-W{week_num}-1", "%G-W%V-%u").replace(
        tzinfo=timezone.utc
    )
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start, end


def get_current_iso_week() -> str:
    """Return the current ISO-week string, e.g. '2026-W11'."""
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


# ── Retry-aware fetch wrapper ──────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(config.MAX_RETRIES + 1),
    wait=wait_exponential(multiplier=config.RETRY_BASE_DELAY, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _fetch_page(
    continuation_token,
    count: int,
) -> tuple[list[dict], object]:
    """
    Fetch one page of reviews from the Play Store with automatic retry on failure.

    Args:
        continuation_token: Token from the previous page (None for first page).
        count:              Max reviews to fetch in this page request.

    Returns:
        (reviews_list, next_continuation_token)
    """
    result, next_token = gps_reviews(
        config.APP_ID,
        lang=config.REVIEW_LANG,
        country=config.REVIEW_COUNTRY,
        sort=Sort.NEWEST,
        count=count,
        continuation_token=continuation_token,
    )
    return result, next_token


# ── Main scraper ───────────────────────────────────────────────────────────────

def fetch_reviews_for_week(iso_week: str) -> list[dict]:
    """
    Fetch all Play Store reviews that fall within the given ISO week.

    Strategy
    --------
    * Scraper sorts by NEWEST, capturing the absolutely latest chronological
      feedback across the designated window of time.
    * We paginate until we've gathered `config.MAX_REVIEWS_PER_WEEK` reviews
      OR exhaust all pages. We then keep only those whose timestamp falls
      within [week_start, week_end].  (The library doesn't support date-range
      filtering natively, so we filter client-side.)
    * A short sleep between pages (1 s) helps avoid Play Store throttling.

    Args:
        iso_week: e.g. '2026-W11'

    Returns:
        List of raw review dicts straight from google-play-scraper.
        Keys include: reviewId, userName, content, score, thumbsUpCount,
                      at (datetime), replyContent, repliedAt.
    """
    week_start, week_end = iso_week_to_date_range(iso_week)

    logger.info(
        f"Scraping Play Store · week={iso_week} · range=[{week_start.date()}, {week_end.date()}]",
        extra={
            "phase": "scraper",
            "data": {
                "iso_week":     iso_week,
                "app_id":       config.APP_ID,
                "week_start":   str(week_start.date()),
                "week_end":     str(week_end.date()),
                "max_reviews":  config.MAX_REVIEWS_PER_WEEK,
            },
        },
    )

    all_raw: list[dict] = []
    token = None
    page_size = 200        # fetch 200 per request (library upper limit ~100-200)
    total_fetched = 0

    while total_fetched < config.MAX_REVIEWS_PER_WEEK:
        try:
            batch, token = _fetch_page(token, count=page_size)
        except Exception as exc:
            logger.error(
                f"Failed to fetch page after retries: {exc}",
                exc_info=True,
                extra={"phase": "scraper"},
            )
            break

        if not batch:
            logger.debug("No more reviews from Play Store — stopping pagination.", extra={"phase": "scraper"})
            break

        all_raw.extend(batch)
        total_fetched += len(batch)

        logger.debug(
            f"Fetched page · reviews_this_page={len(batch)} · total_so_far={total_fetched}",
            extra={"phase": "scraper", "data": {"page_reviews": len(batch), "total": total_fetched}},
        )

        # If no continuation token, we've reached the end of available reviews
        if token is None:
            break

        # Polite delay between pages
        time.sleep(1)

    # ── Filter to the target week window ──────────────────────────────────────
    week_reviews = [
        r for r in all_raw
        if r.get("at") and week_start <= _to_utc(r["at"]) <= week_end
    ]

    logger.info(
        f"Scrape complete · total_fetched={total_fetched} · in_week_window={len(week_reviews)}",
        extra={
            "phase": "scraper",
            "data": {
                "iso_week":       iso_week,
                "total_fetched":  total_fetched,
                "in_week_window": len(week_reviews),
            },
        },
    )

    return week_reviews


def _to_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC). Play Store returns naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── CLI entry-point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Play Store reviews for a given ISO week.")
    parser.add_argument("--week", default=get_current_iso_week(), help="ISO week, e.g. 2026-W11")
    parser.add_argument("--log-level", default=config.LOG_LEVEL, help="Logging level")
    args = parser.parse_args()

    _run_id = f"dev_{args.week}"
    init_logger(_run_id, args.week, args.log_level)

    raw = fetch_reviews_for_week(args.week)
    print(f"\nFetched {len(raw)} raw reviews for {args.week}")
    if raw:
        sample = raw[0]
        print(f"Sample: \u2605{sample.get('score')} | \U0001f44d{sample.get('thumbsUpCount')} | {sample.get('content', '')[:80]}")
