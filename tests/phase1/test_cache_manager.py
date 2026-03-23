"""
tests/phase1/test_cache_manager.py — Unit tests for phase1_ingestion/cache_manager.py

Uses a temporary directory so no real data/cache/ files are touched.

Run with:  pytest tests/phase1/test_cache_manager.py -v
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import config

# ── Monkeypatch config paths before importing cache_manager ───────────────────
# We redirect all cache/log dirs to a tmp directory so tests are hermetic.

@pytest.fixture(autouse=True)
def patch_config_dirs(tmp_path, monkeypatch):
    """Redirect all file-system paths in config to a temp directory."""
    import config
    monkeypatch.setattr(config, "CACHE_DIR",        tmp_path / "cache")
    monkeypatch.setattr(config, "CONSOLIDATED_DIR", tmp_path / "consolidated")
    monkeypatch.setattr(config, "TAGGED_DIR",       tmp_path / "tagged")
    monkeypatch.setattr(config, "REPORTS_DIR",      tmp_path / "reports")
    monkeypatch.setattr(config, "RUNS_LOG_DIR",     tmp_path / "logs/runs")
    monkeypatch.setattr(config, "LLM_AUDIT_DIR",    tmp_path / "logs/llm_audit")
    for d in [
        config.CACHE_DIR, config.CONSOLIDATED_DIR, config.TAGGED_DIR,
        config.REPORTS_DIR, config.RUNS_LOG_DIR, config.LLM_AUDIT_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)


from phase1_ingestion.cache_manager import (
    compute_10_week_window,
    save_week_cache,
    load_week_cache,
    list_cached_weeks,
    expire_old_weeks,
    merge_weekly_csvs,
    save_consolidated,
    _week_to_date,
)
from phase1_ingestion.filter import REVIEW_COLUMNS


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_review(review_id: str = "r1", iso_week: str = "2026-W11") -> dict:
    return {
        "review_id":       review_id,
        "user_name":       "Tester",
        "review_text":     "This is a perfectly valid review text for testing purposes.",
        "rating":          4,
        "thumbs_up_count": 10,
        "review_date":     "2026-03-15",
        "reply_text":      "",
        "word_count":      12,
        "iso_week":        iso_week,
    }


# ── compute_10_week_window (backward-compatible name, dynamic lookback) ──────

def test_window_returns_configured_lookback_weeks():
    window = compute_10_week_window("2026-W11")
    assert len(window) == config.LOOKBACK_WEEKS


def test_window_ends_at_current_week():
    window = compute_10_week_window("2026-W11")
    assert window[-1] == "2026-W11"


def test_window_starts_lookback_minus_one_weeks_before():
    window = compute_10_week_window("2026-W11")
    start_dt = _week_to_date(window[0])
    end_dt = _week_to_date(window[-1])
    assert (end_dt - start_dt).days == 7 * (config.LOOKBACK_WEEKS - 1)


def test_window_is_sorted_oldest_first():
    window = compute_10_week_window("2026-W11")
    dates = [_week_to_date(w) for w in window]
    assert dates == sorted(dates)


def test_window_handles_year_boundary():
    # '2025-W02' — window should cross into 2024
    window = compute_10_week_window("2025-W02")
    assert window[0].startswith("2024-")


# ── save_week_cache / load_week_cache ─────────────────────────────────────────

def test_save_creates_csv_file():
    import config
    reviews = [make_review()]
    path = save_week_cache("2026-W11", reviews)
    assert path.exists()
    assert path.name == "2026-W11.csv"


def test_load_returns_dataframe():
    reviews = [make_review()]
    save_week_cache("2026-W11", reviews)
    df = load_week_cache("2026-W11")
    assert df is not None
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1


def test_load_preserves_review_id():
    reviews = [make_review(review_id="abc123")]
    save_week_cache("2026-W11", reviews)
    df = load_week_cache("2026-W11")
    assert df["review_id"].iloc[0] == "abc123"


def test_load_returns_none_for_missing_week():
    result = load_week_cache("2099-W99")
    assert result is None


def test_save_empty_list_creates_empty_csv():
    save_week_cache("2026-W10", [])
    df = load_week_cache("2026-W10")
    assert df is not None
    assert len(df) == 0


# ── list_cached_weeks ─────────────────────────────────────────────────────────

def test_list_empty_cache():
    weeks = list_cached_weeks()
    assert weeks == []


def test_list_returns_saved_weeks():
    save_week_cache("2026-W09", [make_review(iso_week="2026-W09")])
    save_week_cache("2026-W11", [make_review(iso_week="2026-W11")])
    weeks = list_cached_weeks()
    assert "2026-W09" in weeks
    assert "2026-W11" in weeks


def test_list_sorted_oldest_first():
    save_week_cache("2026-W11", [make_review(iso_week="2026-W11")])
    save_week_cache("2026-W09", [make_review(iso_week="2026-W09")])
    weeks = list_cached_weeks()
    assert weeks.index("2026-W09") < weeks.index("2026-W11")


# ── expire_old_weeks ──────────────────────────────────────────────────────────

def test_expire_removes_weeks_outside_window():
    # Choose a clearly old week that sits outside the configured lookback window.
    window = compute_10_week_window("2026-W11")
    oldest_dt = _week_to_date(window[0])
    old_week_dt = oldest_dt - timedelta(weeks=1)
    old_iso = f"{old_week_dt.isocalendar().year}-W{old_week_dt.isocalendar().week:02d}"

    save_week_cache(old_iso, [make_review(iso_week=old_iso)])   # old week
    save_week_cache("2026-W11", [make_review(iso_week="2026-W11")])  # in window
    window = compute_10_week_window("2026-W11")
    expired = expire_old_weeks(window)
    assert old_iso in expired
    assert load_week_cache(old_iso) is None


def test_expire_keeps_weeks_in_window():
    window = compute_10_week_window("2026-W11")
    for w in window:
        save_week_cache(w, [make_review(iso_week=w)])
    expired = expire_old_weeks(window)
    assert len(expired) == 0
    for w in window:
        assert load_week_cache(w) is not None


def test_expire_returns_empty_when_nothing_to_expire():
    window = compute_10_week_window("2026-W11")
    expired = expire_old_weeks(window)
    assert expired == []


# ── merge_weekly_csvs ─────────────────────────────────────────────────────────

def test_merge_returns_dataframe():
    save_week_cache("2026-W10", [make_review("r1", "2026-W10")])
    save_week_cache("2026-W11", [make_review("r2", "2026-W11")])
    df = merge_weekly_csvs(["2026-W10", "2026-W11"])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_merge_deduplicates():
    # Same review_id in two files
    save_week_cache("2026-W10", [make_review("dup_id", "2026-W10")])
    save_week_cache("2026-W11", [make_review("dup_id", "2026-W11")])
    df = merge_weekly_csvs(["2026-W10", "2026-W11"])
    assert len(df) == 1


def test_merge_returns_empty_df_for_missing_all_weeks():
    df = merge_weekly_csvs(["2099-W01", "2099-W02"])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


# ── save_consolidated ─────────────────────────────────────────────────────────

def test_save_consolidated_creates_file():
    df = pd.DataFrame([make_review()])
    path = save_consolidated(df, "2026-W11")
    assert path.exists()
    assert path.name == "2026-W11_full.csv"
