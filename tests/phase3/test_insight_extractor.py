"""Unit tests for Phase 3 insight extraction (Python helpers, no live Gemini)."""

from phase3_insights.insight_extractor import (
    compute_sentiment,
    avg_rating,
    top_reviews_by_thumbs_up,
    _build_user_prompt,
    _fallback_from_candidates,
    _is_valid_theme_quote,
)


def test_compute_sentiment():
    reviews = [
        {"rating": 5},
        {"rating": 4},
        {"rating": 3},
        {"rating": 2},
        {"rating": 1},
    ]
    s = compute_sentiment(reviews)
    assert s["positive"] == 2
    assert s["neutral"] == 1
    assert s["negative"] == 2


def test_avg_rating():
    assert avg_rating([{"rating": 4}, {"rating": 2}]) == 3.0
    assert avg_rating([]) == 0.0


def test_top_reviews_by_thumbs_up():
    reviews = [
        {"review_id": "a", "thumbs_up": 1, "rating": 5, "text": "x"},
        {"review_id": "b", "thumbs_up": 10, "rating": 1, "text": "y"},
        {"review_id": "c", "thumbs_up": 5, "rating": 3, "text": "z"},
    ]
    top = top_reviews_by_thumbs_up(reviews, 2)
    assert [r["review_id"] for r in top] == ["b", "c"]


def test_build_user_prompt_contains_theme_and_candidates():
    themes_payload = [
        {
            "theme_name": "Test Theme",
            "review_count": 2,
            "avg_rating": 3.5,
            "sentiment": {"positive": 1, "neutral": 0, "negative": 1},
            "candidates": [
                {"review_id": "r1", "rating": 1, "thumbs_up": 9, "text": "hello"},
            ],
        }
    ]
    text = _build_user_prompt(themes_payload)
    assert "Test Theme" in text
    assert "r1" in text
    assert "hello" in text


def test_fallback_from_candidates():
    cands = [
        {"text": "low", "thumbs_up": 1, "rating": 5, "review_id": "x"},
        {"text": "high", "thumbs_up": 99, "rating": 2, "review_id": "y"},
    ]
    fb = _fallback_from_candidates(cands)
    assert fb["review_id"] == "y"
    assert "high" in fb["quote"]


def test_is_valid_theme_quote():
    candidates = [
        {"review_id": "r1", "text": "a"},
        {"review_id": "r2", "text": "b"},
    ]
    assert _is_valid_theme_quote({"review_id": "r1", "quote": "quoted text"}, candidates)
    assert not _is_valid_theme_quote({"review_id": "rx", "quote": "quoted text"}, candidates)
    assert not _is_valid_theme_quote({"review_id": "r1", "quote": ""}, candidates)
