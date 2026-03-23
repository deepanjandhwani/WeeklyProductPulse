"""Tests for Google Docs payload JSON (no API calls)."""

from phase4_report.gdoc_payload import build_gdoc_payload, format_payload_as_doc_section


def test_build_gdoc_payload_shape():
    fee = {
        "title": "Test fee",
        "bullets": ["a", "b"],
        "sources": [
            {"label": "L1", "url": "https://example.com/1"},
            {"label": "L2", "url": "https://example.com/2"},
        ],
    }
    p = build_gdoc_payload("2026-W12", "# Hello\n", fee)
    assert p["iso_week"] == "2026-W12"
    assert p["date"]
    assert p["weekly_pulse"] == "# Hello\n"
    assert p["fee_scenario"] == "Test fee"
    assert p["explanation_bullets"] == ["a", "b"]
    assert len(p["source_links"]) == 2
    assert p["source_links"][0]["url"].startswith("https://")


def test_build_gdoc_payload_no_fee():
    p = build_gdoc_payload("2026-W12", "x", None)
    assert p["fee_scenario"] == ""
    assert p["explanation_bullets"] == []
    assert p["source_links"] == []


def test_format_payload_contains_sections():
    p = build_gdoc_payload(
        "2026-W12",
        "# Md",
        {
            "title": "T",
            "bullets": ["one"],
            "sources": [{"label": "S", "url": "https://x.com"}],
        },
    )
    text = format_payload_as_doc_section(p)
    assert "2026-W12" in text
    assert "# Md" in text
    assert "T" in text
    assert "one" in text
    assert "https://x.com" in text
