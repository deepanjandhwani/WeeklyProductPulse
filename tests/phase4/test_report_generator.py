"""Unit tests for Phase 4 helpers (no live LLM)."""

from phase4_report.report_generator import (
    iso_week_date_range,
    previous_iso_week,
    _pct,
    _weighted_avg_rating,
    _validate_llm_payload,
)


def test_iso_week_date_range():
    s = iso_week_date_range("2026-W12")
    assert "2026" in s or "March" in s
    assert "–" in s


def test_previous_iso_week():
    assert previous_iso_week("2026-W12") == "2026-W11"


def test_pct():
    assert _pct(25, 100) == 25.0
    assert _pct(0, 0) == 0.0


def test_weighted_avg_rating():
    themes = [
        {"review_count": 10, "avg_rating": 4.0},
        {"review_count": 10, "avg_rating": 2.0},
    ]
    assert _weighted_avg_rating(themes) == 3.0


def test_validate_llm_payload_rejects_duplicate_action_themes():
    payload = {
        "overview": "ok",
        "themes": [{"analysis": "a"}, {"analysis": "b"}, {"analysis": "c"}],
        "action_ideas": [
            {"theme": "A", "title": "t1", "description": "d1", "rationale": "r1"},
            {"theme": "A", "title": "t2", "description": "d2", "rationale": "r2"},
            {"theme": "B", "title": "t3", "description": "d3", "rationale": "r3"},
        ],
    }
    assert _validate_llm_payload(payload, 3, ["A", "B", "C"]) is None


def test_validate_llm_payload_rejects_unknown_action_theme():
    payload = {
        "overview": "ok",
        "themes": [{"analysis": "a"}, {"analysis": "b"}, {"analysis": "c"}],
        "action_ideas": [
            {"theme": "A", "title": "t1", "description": "d1", "rationale": "r1"},
            {"theme": "B", "title": "t2", "description": "d2", "rationale": "r2"},
            {"theme": "X", "title": "t3", "description": "d3", "rationale": "r3"},
        ],
    }
    assert _validate_llm_payload(payload, 3, ["A", "B", "C"]) is None
