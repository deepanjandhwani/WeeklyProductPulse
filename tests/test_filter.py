"""
tests/test_filter.py — Unit tests for src/filter.py

Run with:  pytest tests/test_filter.py -v
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.filter import filter_reviews, REVIEW_COLUMNS, _word_count, _iso_week_label


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_raw(
    text: str = "This is a sample review with enough words for the test",
    score: int = 4,
    thumbs: int = 5,
    days_ago: int = 3,
    review_id: str = "rev_001",
) -> dict:
    """Build a minimal raw Play Store review dict."""
    return {
        "reviewId":      review_id,
        "userName":      "Test User",
        "content":       text,
        "score":         score,
        "thumbsUpCount": thumbs,
        "at":            datetime.now(timezone.utc) - timedelta(days=days_ago),
        "replyContent":  None,
    }


# ── Word count helper ──────────────────────────────────────────────────────────

def test_word_count_basic():
    assert _word_count("hello world") == 2

def test_word_count_extra_spaces():
    assert _word_count("  hello   world  ") == 2

def test_word_count_single():
    assert _word_count("hello") == 1

def test_word_count_empty():
    assert _word_count("") == 0


# ── ISO week label ─────────────────────────────────────────────────────────────

def test_iso_week_label_format():
    dt = datetime(2026, 3, 15, tzinfo=timezone.utc)  # 2026-W11
    label = _iso_week_label(dt)
    assert label == "2026-W11"


# ── filter_reviews — passed cases ─────────────────────────────────────────────

def test_valid_review_passes():
    raw = [make_raw()]
    result, stats = filter_reviews(raw)
    assert len(result) == 1
    assert stats["passed"] == 1
    assert stats["skipped_too_short"] == 0
    assert stats["skipped_too_old"] == 0


def test_output_has_correct_schema():
    raw = [make_raw()]
    result, _ = filter_reviews(raw)
    record = result[0]
    for col in REVIEW_COLUMNS:
        assert col in record, f"Missing column: {col}"


def test_word_count_stored_correctly():
    text = "one two three four five six seven eight nine ten eleven"
    raw = [make_raw(text=text)]
    result, _ = filter_reviews(raw)
    assert result[0]["word_count"] == 11


def test_rating_stored_correctly():
    raw = [make_raw(score=2)]
    result, _ = filter_reviews(raw)
    assert result[0]["rating"] == 2


def test_thumbs_up_stored_correctly():
    raw = [make_raw(thumbs=42)]
    result, _ = filter_reviews(raw)
    assert result[0]["thumbs_up_count"] == 42


def test_review_date_format():
    raw = [make_raw(days_ago=1)]
    result, _ = filter_reviews(raw)
    # Should be YYYY-MM-DD
    date_str = result[0]["review_date"]
    assert len(date_str) == 10
    assert date_str[4] == "-" and date_str[7] == "-"


# ── filter_reviews — skipped cases ────────────────────────────────────────────

def test_skips_review_fewer_than_10_words():
    raw = [make_raw(text="Too short")]   # 2 words
    result, stats = filter_reviews(raw)
    assert len(result) == 0
    assert stats["skipped_too_short"] == 1


def test_skips_review_exactly_9_words():
    raw = [make_raw(text="one two three four five six seven eight nine")]  # 9
    result, stats = filter_reviews(raw)
    assert len(result) == 0
    assert stats["skipped_too_short"] == 1


def test_passes_review_exactly_10_words():
    raw = [make_raw(text="one two three four five six seven eight nine ten")]  # 10
    result, stats = filter_reviews(raw)
    assert len(result) == 1
    assert stats["passed"] == 1


def test_skips_review_older_than_10_weeks():
    raw = [make_raw(days_ago=80)]   # ~11.4 weeks
    result, stats = filter_reviews(raw)
    assert len(result) == 0
    assert stats["skipped_too_old"] == 1


def test_skips_review_with_no_text():
    raw = [make_raw(text="")]
    result, stats = filter_reviews(raw)
    assert len(result) == 0
    assert stats["skipped_no_text"] == 1


def test_skips_review_with_none_text():
    raw = [{
        "reviewId": "x", "userName": "u", "content": None,
        "score": 4, "thumbsUpCount": 0,
        "at": datetime.now(timezone.utc) - timedelta(days=1),
        "replyContent": None,
    }]
    result, stats = filter_reviews(raw)
    assert len(result) == 0


def test_skips_review_missing_date():
    raw = [{
        "reviewId": "x", "userName": "u",
        "content": "This review has plenty of words to pass the word count filter",
        "score": 4, "thumbsUpCount": 0,
        "at": None, "replyContent": None,
    }]
    result, stats = filter_reviews(raw)
    assert len(result) == 0


# ── Mixed batch ────────────────────────────────────────────────────────────────

def test_mixed_batch_correct_counts():
    raw = [
        make_raw(text="Too short", review_id="r1"),
        make_raw(days_ago=100, review_id="r2"),          # too old
        make_raw(review_id="r3"),                         # valid
        make_raw(text="", review_id="r4"),                # no text
        make_raw(score=1, thumbs=99, review_id="r5"),     # valid
    ]
    result, stats = filter_reviews(raw)
    assert stats["passed"] == 2
    assert stats["skipped_too_short"] == 1
    assert stats["skipped_too_old"] == 1
    assert stats["skipped_no_text"] == 1
    assert len(result) == 2


# ── Custom cutoff date ────────────────────────────────────────────────────────

def test_custom_cutoff_date():
    """Passing an explicit cutoff allows testing without depending on wall time."""
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    raw = [
        make_raw(days_ago=1, review_id="recent"),      # passes regardless
        {
            "reviewId": "old", "userName": "u",
            "content": "This is a valid review with many words to pass the filter",
            "score": 3, "thumbsUpCount": 0,
            "at": datetime(2025, 12, 1, tzinfo=timezone.utc),  # before cutoff
            "replyContent": None,
        },
    ]
    result, stats = filter_reviews(raw, cutoff_date=cutoff)
    assert stats["passed"] == 1
    assert stats["skipped_too_old"] == 1
    assert result[0]["review_id"] == "recent"
