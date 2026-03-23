"""Tests for curated fee scenario selection and Markdown (no LLM)."""

import pytest

import phase4_report.fee_scenarios as fs


def test_select_same_iso_week_stable():
    a = fs.select_fee_scenario("2026-W12")
    b = fs.select_fee_scenario("2026-W12")
    assert a is not None and b is not None
    assert a["id"] == b["id"]


def test_fee_json_single_scenario():
    data = fs.load_fee_scenarios_data()
    scenarios = data.get("scenarios") or []
    assert len(scenarios) == 1
    s = scenarios[0]
    bullets = s.get("bullets") or []
    assert 1 <= len(bullets) <= 6
    sources = s.get("sources") or []
    assert len(sources) == 2
    for src in sources:
        assert str(src.get("url", "")).startswith("https://")


def test_different_weeks_same_single_scenario():
    a = fs.select_fee_scenario("2026-W01")
    b = fs.select_fee_scenario("2026-W50")
    assert a is not None and b is not None
    assert a["id"] == b["id"] == "exit_load_mf"


def test_render_contains_last_checked_and_sources():
    s = fs.select_fee_scenario("2026-W01")
    assert s is not None
    md = fs.render_fee_section_markdown(s)
    assert "**Last checked:**" in md
    assert "**Official sources**" in md
    assert md.count("https://") >= 2
    assert "### Fee context (facts only)" in md


def test_override_scenario_id():
    picked = fs.select_fee_scenario("2099-W99", scenario_id="exit_load_mf")
    assert picked is not None
    assert picked["id"] == "exit_load_mf"


def test_section_disabled_returns_none(monkeypatch):
    import config

    monkeypatch.setattr(config, "FEE_SECTION_ENABLED", False)
    assert fs.select_fee_scenario("2026-W12") is None
