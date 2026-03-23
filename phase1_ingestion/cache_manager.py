"""
phase1_ingestion/cache_manager.py — Weekly CSV cache for Play Store reviews.

Responsibilities
----------------
* Save a week's filtered reviews to data/cache/<WEEK>.csv
* Load a week's reviews from cache (returns None if missing/corrupt).
* List all currently cached weeks.
* Expire weeks that are no longer in the configured lookback rolling window.
* Merge any N week CSVs into a single consolidated DataFrame.

Cache strategy (architecture §7)
---------------------------------
   Week N   →  fetch fresh from Play Store, save to cache/WEEK.csv
   Week N-1 →  load from cache (do not re-fetch)
   ...
   Week N-k →  load from cache (do not re-fetch)
   Week outside lookback window → expired and deleted

Usage (standalone)
------------------
    python -m phase1_ingestion.cache_manager --list
    python -m phase1_ingestion.cache_manager --expire
"""

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import config
from phase1_ingestion.filter import REVIEW_COLUMNS

logger = logging.getLogger("weekly_pulse")


# ── ISO-week ordering helper ───────────────────────────────────────────────────

def _week_to_date(iso_week: str) -> datetime:
    """Convert '2026-W11' → Monday 00:00 UTC of that week (for comparison)."""
    year, wnum = iso_week.split("-W")
    return datetime.strptime(f"{year}-W{wnum}-1", "%G-W%V-%u").replace(tzinfo=timezone.utc)


def compute_lookback_window(current_week: str) -> list[str]:
    """
    Return a list of the LOOKBACK_WEEKS ISO-week strings ending at current_week (inclusive),
    ordered from oldest → newest.

    E.g. current_week='2026-W11' → ['2026-W02', '2026-W03', ..., '2026-W11']
    """
    anchor = _week_to_date(current_week)
    windows = []
    for offset in range(config.LOOKBACK_WEEKS - 1, -1, -1):
        dt = anchor - timedelta(weeks=offset)
        iso = dt.isocalendar()
        windows.append(f"{iso.year}-W{iso.week:02d}")
    return windows


def compute_10_week_window(current_week: str) -> list[str]:
    """
    Backward-compatible alias for older tests/callers.

    Historically this function name used a fixed "10-week" label. The actual
    behavior now follows ``config.LOOKBACK_WEEKS`` via ``compute_lookback_window``.
    """
    return compute_lookback_window(current_week)


# ── Save ───────────────────────────────────────────────────────────────────────

def save_week_cache(iso_week: str, reviews: list[dict]) -> Path:
    """
    Persist a list of filtered review dicts to data/cache/<iso_week>.csv.

    Args:
        iso_week: e.g. '2026-W11'
        reviews:  List of dicts matching REVIEW_COLUMNS schema.

    Returns:
        Path to the saved CSV file.
    """
    cache_path = Path(config.CACHE_DIR) / f"{iso_week}.csv"

    if not reviews:
        logger.warning(
            f"No reviews to cache for {iso_week} — writing empty CSV.",
            extra={"phase": "cache_manager"},
        )

    df = pd.DataFrame(reviews, columns=REVIEW_COLUMNS)
    df.to_csv(cache_path, index=False, encoding="utf-8")

    file_size_kb = round(cache_path.stat().st_size / 1024, 1)
    logger.info(
        f"Cached {len(reviews)} reviews → {cache_path.name}  ({file_size_kb} KB)",
        extra={
            "phase": "cache_manager",
            "data": {
                "iso_week":    iso_week,
                "review_count": len(reviews),
                "file_path":   str(cache_path),
                "file_size_kb": file_size_kb,
            },
        },
    )
    return cache_path


# ── Load ───────────────────────────────────────────────────────────────────────

def load_week_cache(iso_week: str) -> pd.DataFrame | None:
    """
    Load cached reviews for a given week.

    Returns:
        pd.DataFrame if the cache file exists and is valid, else None.
    """
    cache_path = Path(config.CACHE_DIR) / f"{iso_week}.csv"

    if not cache_path.exists():
        logger.info(
            f"Cache MISS for {iso_week} — file not found.",
            extra={"phase": "cache_manager", "data": {"iso_week": iso_week, "reason": "missing"}},
        )
        return None

    try:
        df = pd.read_csv(cache_path, encoding="utf-8")
        # Validate schema: ensure required columns exist
        missing_cols = [c for c in REVIEW_COLUMNS if c not in df.columns]
        if missing_cols:
            logger.warning(
                f"Cache INVALID for {iso_week} — missing columns: {missing_cols}. Will re-fetch.",
                extra={"phase": "cache_manager", "data": {"iso_week": iso_week, "reason": "corrupt", "missing_cols": missing_cols}},
            )
            return None

        logger.debug(
            f"Cache HIT for {iso_week} — {len(df)} reviews loaded.",
            extra={"phase": "cache_manager", "data": {"iso_week": iso_week, "review_count": len(df)}},
        )
        return df

    except Exception as exc:
        logger.warning(
            f"Cache CORRUPT for {iso_week} — could not parse CSV ({exc}). Will re-fetch.",
            extra={"phase": "cache_manager", "data": {"iso_week": iso_week, "reason": str(exc)}},
        )
        return None


# ── List ───────────────────────────────────────────────────────────────────────

def list_cached_weeks() -> list[str]:
    """
    Return a sorted list of ISO-week strings for which valid cache CSVs exist.
    E.g. ['2026-W02', '2026-W03', ..., '2026-W10']
    """
    cache_dir = Path(config.CACHE_DIR)
    weeks = []
    for f in cache_dir.glob("*.csv"):
        # Filename format: 2026-W11.csv
        stem = f.stem  # e.g. '2026-W11'
        if "-W" in stem:
            weeks.append(stem)
    weeks.sort(key=_week_to_date)
    logger.debug(
        f"Found {len(weeks)} cached weeks: {weeks}",
        extra={"phase": "cache_manager", "data": {"cached_weeks": weeks}},
    )
    return weeks


# ── Expire ────────────────────────────────────────────────────────────────────

def expire_old_weeks(current_window: list[str]) -> list[str]:
    """
    Delete cache files for weeks that are no longer in the lookback window.

    Args:
        current_window: The list of week-strings that should be kept.

    Returns:
        List of expired week strings that were deleted.
    """
    cache_dir = Path(config.CACHE_DIR)
    all_cached = list_cached_weeks()
    expired: list[str] = []

    for week in all_cached:
        if week not in current_window:
            cache_path = cache_dir / f"{week}.csv"
            cache_path.unlink(missing_ok=True)
            expired.append(week)
            logger.info(
                f"Expired cache for {week} (outside lookback window).",
                extra={
                    "phase": "cache_manager",
                    "data": {"expired_week": week, "file": str(cache_path)},
                },
            )

    if not expired:
        logger.debug("No cache files to expire.", extra={"phase": "cache_manager"})

    return expired


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_weekly_csvs(weeks: list[str]) -> pd.DataFrame:
    """
    Load and merge CSVs for the given week list into a single DataFrame.

    Weeks missing from cache will be logged as warnings (caller is responsible
    for ensuring all required weeks are fetched before calling this).

    Args:
        weeks: Ordered list of ISO-week strings to merge (oldest → newest).

    Returns:
        Combined pd.DataFrame with all reviews, sorted by review_date ascending.
    """
    frames: list[pd.DataFrame] = []
    for week in weeks:
        df = load_week_cache(week)
        if df is not None and not df.empty:
            frames.append(df)
        else:
            logger.warning(
                f"Week {week} missing from cache — it will be absent from the consolidated file.",
                extra={"phase": "cache_manager"},
            )

    if not frames:
        logger.error(
            "No data available — all week caches are empty or missing!",
            extra={"phase": "cache_manager"},
        )
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    merged = pd.concat(frames, ignore_index=True)
    # De-duplicate by review_id in case the same review appears in multiple week files
    before = len(merged)
    merged.drop_duplicates(subset=["review_id"], keep="first", inplace=True)
    dupes_removed = before - len(merged)

    # Sort chronologically
    merged.sort_values("review_date", ascending=True, inplace=True)
    merged.reset_index(drop=True, inplace=True)

    logger.info(
        f"Merged {len(weeks)} weeks → {len(merged)} reviews  "
        f"(deduped {dupes_removed})",
        extra={
            "phase": "cache_manager",
            "data": {
                "weeks_merged":    len(weeks),
                "total_reviews":   len(merged),
                "dupes_removed":   dupes_removed,
            },
        },
    )
    return merged


def save_consolidated(df: pd.DataFrame, iso_week: str) -> Path:
    """
    Save the merged DataFrame to data/consolidated/<iso_week>_full.csv.

    Returns:
        Path to the saved file.
    """
    path = Path(config.CONSOLIDATED_DIR) / f"{iso_week}_full.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    size_kb = round(path.stat().st_size / 1024, 1)
    logger.info(
        f"Consolidated CSV saved → {path.name}  ({size_kb} KB, {len(df)} reviews)",
        extra={
            "phase": "cache_manager",
            "data": {"file_path": str(path), "review_count": len(df), "size_kb": size_kb},
        },
    )
    return path


# ── CLI entry-point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from shared.logger import init_logger
    from phase1_ingestion.scraper import get_current_iso_week

    parser = argparse.ArgumentParser(description="WeeklyProductPulse — Cache Manager CLI")
    parser.add_argument("--list",   action="store_true", help="List all cached weeks")
    parser.add_argument("--expire", action="store_true", help="Expire weeks outside the lookback window")
    parser.add_argument("--week",   default=get_current_iso_week(), help="Current ISO week (for expiry)")
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    args = parser.parse_args()

    init_logger(f"dev_{args.week}", args.week, args.log_level)

    if args.list:
        cached = list_cached_weeks()
        print(f"\nCached weeks ({len(cached)}):", cached or "(none)")

    if args.expire:
        window = compute_lookback_window(args.week)
        print(f"\nCurrent lookback window: {window}")
        expired = expire_old_weeks(window)
        print(f"Expired: {expired or '(nothing to expire)'}")
