"""
Discover and load Phase 4 Markdown pulse reports from ``data/reports/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import config

_PULSE_RE = re.compile(r"^(\d{4})-W(\d{2})_pulse\.md$")


@dataclass(frozen=True)
class PulseReportMeta:
    iso_week: str
    path: Path
    size_bytes: int


def _week_sort_key(iso_week: str) -> tuple[int, int]:
    m = re.match(r"^(\d{4})-W(\d{2})$", iso_week)
    if not m:
        return (0, 0)
    return int(m.group(1)), int(m.group(2))


def list_pulse_reports() -> list[PulseReportMeta]:
    """All ``*_pulse.md`` files under ``REPORTS_DIR``, newest ISO week last."""
    out: list[PulseReportMeta] = []
    if not config.REPORTS_DIR.is_dir():
        return out
    for p in sorted(config.REPORTS_DIR.glob("*_pulse.md")):
        m = _PULSE_RE.match(p.name)
        if not m:
            continue
        iso_week = f"{m.group(1)}-W{m.group(2)}"
        try:
            st = p.stat()
        except OSError:
            continue
        out.append(PulseReportMeta(iso_week=iso_week, path=p, size_bytes=st.st_size))
    out.sort(key=lambda x: _week_sort_key(x.iso_week))
    return out


def read_pulse_markdown(iso_week: str) -> str | None:
    path = config.REPORTS_DIR / f"{iso_week}_pulse.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def get_latest_pulse() -> tuple[str, str] | None:
    """
    Return ``(iso_week, markdown)`` for the most recent pulse file, or ``None``.
    """
    reports = list_pulse_reports()
    if not reports:
        return None
    last = reports[-1]
    text = read_pulse_markdown(last.iso_week)
    if text is None:
        return None
    return last.iso_week, text
