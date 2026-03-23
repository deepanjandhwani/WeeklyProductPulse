"""
Curated fee-scenario block for the weekly pulse (facts only, official links from JSON).

``prompts/fee_scenarios.json`` defines **exactly one** scenario (the active fee topic).
Optional ``FEE_SCENARIO_ID`` / ``--fee-scenario-id`` must match that scenario’s ``id`` if set.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger("weekly_pulse")

_FEE_DATA_CACHE: dict[str, Any] | None = None


def _fee_scenarios_path() -> Path:
    return config.PROMPTS_DIR / "fee_scenarios.json"


def load_fee_scenarios_data() -> dict[str, Any]:
    """Load ``prompts/fee_scenarios.json`` (cached)."""
    global _FEE_DATA_CACHE
    if _FEE_DATA_CACHE is not None:
        return _FEE_DATA_CACHE
    path = _fee_scenarios_path()
    if not path.exists():
        logger.error(f"Fee scenarios file not found: {path}")
        _FEE_DATA_CACHE = {"scenarios": []}
        return _FEE_DATA_CACHE
    with open(path, encoding="utf-8") as f:
        _FEE_DATA_CACHE = json.load(f)
    return _FEE_DATA_CACHE


def select_fee_scenario(
    iso_week: str,
    *,
    scenario_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Return the single curated fee scenario, or None if disabled / file empty.

    The JSON is expected to contain **one** object in ``scenarios``. If multiple entries
    exist, only the **first** is used (legacy tolerance).

    If ``scenario_id`` or ``config.FEE_SCENARIO_ID`` is set, it must match the scenario’s
    ``id``; otherwise a warning is logged and the scenario is still returned.
    """
    del iso_week  # API stability; week no longer selects among scenarios
    if not config.FEE_SECTION_ENABLED:
        return None

    data = load_fee_scenarios_data()
    scenarios: list[dict[str, Any]] = list(data.get("scenarios") or [])
    if not scenarios:
        return None

    raw = scenarios[0]
    if len(scenarios) > 1:
        logger.warning(
            "fee_scenarios.json has %d entries; only the first is used. "
            "Keep a single scenario per product policy.",
            len(scenarios),
        )

    want = (scenario_id or config.FEE_SCENARIO_ID or "").strip()
    only_id = str(raw.get("id", ""))
    if want and want != only_id:
        logger.warning(
            "FEE_SCENARIO_ID=%r does not match the single scenario id %r; using the configured scenario.",
            want,
            only_id,
        )

    return _normalize_scenario(raw)


def _normalize_scenario(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure ≤6 bullets, exactly 2 sources with https URLs."""
    bullets = [str(b).strip() for b in (raw.get("bullets") or []) if str(b).strip()]
    bullets = bullets[:6]
    sources: list[dict[str, str]] = []
    for s in (raw.get("sources") or [])[:2]:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label", "")).strip()
        url = str(s.get("url", "")).strip()
        if label and url.startswith("https://"):
            sources.append({"label": label, "url": url})
    while len(sources) < 2:
        sources.append({"label": "Source (configure in fee_scenarios.json)", "url": "https://www.sebi.gov.in/"})

    return {
        "id": str(raw.get("id", "")),
        "category": str(raw.get("category", "")),
        "title": str(raw.get("title", "")).strip() or "Fee scenario",
        "last_checked": str(raw.get("last_checked", "")).strip(),
        "bullets": bullets,
        "sources": sources[:2],
    }


def render_fee_section_markdown(scenario: dict[str, Any]) -> str:
    """Markdown block: heading, last checked, bullets, two official links."""
    title = scenario.get("title", "Fee context")
    last_checked = scenario.get("last_checked", "")
    bullets: list[str] = scenario.get("bullets") or []
    sources: list[dict[str, str]] = scenario.get("sources") or []

    lines: list[str] = [
        "### Fee context (facts only)",
        "",
        f"**Scenario:** {title}",
        "",
    ]
    if last_checked:
        lines.append(f"**Last checked:** {last_checked}")
        lines.append("")

    for b in bullets:
        lines.append(f"- {b}")
    lines.append("")
    lines.append("**Official sources**")
    for i, src in enumerate(sources[:2], start=1):
        label = src.get("label", "Link")
        url = src.get("url", "")
        lines.append(f"{i}. [{label}]({url})")
    lines.append("")
    return "\n".join(lines)
