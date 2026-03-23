"""Tests for report discovery (no HTTP)."""

from web.services.reports import list_pulse_reports, read_pulse_markdown


def test_list_pulse_reports_returns_sorted():
    rows = list_pulse_reports()
    assert isinstance(rows, list)
    for r in rows:
        assert r.iso_week
        assert r.path.name.endswith("_pulse.md")


def test_read_pulse_known_week():
    rows = list_pulse_reports()
    if not rows:
        return
    w = rows[-1].iso_week
    md = read_pulse_markdown(w)
    assert md is not None
    assert len(md) > 0
