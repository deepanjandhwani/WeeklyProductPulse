"""
tests/test_scraper.py — Unit tests for src/scraper.py helper functions.

Note: The actual Play Store fetch (fetch_reviews_for_week) is NOT tested here
because it makes a live network call. Run integration tests manually:
    python -m src.scraper --week 2026-W11

Run unit tests with:  pytest tests/test_scraper.py -v
"""

from datetime import datetime, timezone

import pytest

from src.scraper import iso_week_to_date_range, get_current_iso_week, _to_utc


# ── iso_week_to_date_range ─────────────────────────────────────────────────────

def test_iso_week_start_is_monday():
    start, _ = iso_week_to_date_range("2026-W11")
    assert start.weekday() == 0, "Start should be Monday (weekday=0)"


def test_iso_week_end_is_sunday():
    _, end = iso_week_to_date_range("2026-W11")
    assert end.weekday() == 6, "End should be Sunday (weekday=6)"


def test_iso_week_range_is_7_days():
    start, end = iso_week_to_date_range("2026-W11")
    delta = end - start
    assert delta.days == 6, "Range should span 6 days (Mon → Sun)"


def test_iso_week_dates_are_utc():
    start, end = iso_week_to_date_range("2026-W11")
    assert start.tzinfo is not None, "Start should be timezone-aware"
    assert end.tzinfo is not None, "End should be timezone-aware"


def test_iso_week_known_dates():
    """2026-W11 starts on Monday 9 March 2026 and ends on Sunday 15 March 2026."""
    start, end = iso_week_to_date_range("2026-W11")
    assert start.date().isoformat() == "2026-03-09"
    assert end.date().isoformat() == "2026-03-15"


def test_iso_week_year_boundary():
    """2025-W01 starts on Monday 30 Dec 2024 (ISO week crossing year boundary)."""
    start, _ = iso_week_to_date_range("2025-W01")
    assert start.date().isoformat() == "2024-12-30"


def test_iso_week_invalid_format_raises():
    with pytest.raises((ValueError, AttributeError)):
        iso_week_to_date_range("2026-11")   # missing 'W'


# ── get_current_iso_week ──────────────────────────────────────────────────────

def test_get_current_iso_week_format():
    week = get_current_iso_week()
    assert "-W" in week, "Should contain '-W'"
    parts = week.split("-W")
    assert len(parts) == 2
    assert parts[0].isdigit() and len(parts[0]) == 4, "Year should be 4 digits"
    assert parts[1].isdigit() and 1 <= int(parts[1]) <= 53, "Week should be 1-53"


# ── _to_utc ───────────────────────────────────────────────────────────────────

def test_to_utc_naive_gets_utc():
    naive = datetime(2026, 3, 15, 12, 0, 0)   # no tzinfo
    result = _to_utc(naive)
    assert result.tzinfo is not None
    assert result.year == 2026 and result.month == 3 and result.day == 15


def test_to_utc_aware_stays_utc():
    aware = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = _to_utc(aware)
    assert result == aware


def test_to_utc_preserves_time():
    naive = datetime(2026, 3, 15, 8, 30, 0)
    result = _to_utc(naive)
    assert result.hour == 8 and result.minute == 30
