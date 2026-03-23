"""
Orchestrate Phase 1 → 4 for scheduled runs (GitHub Actions, systemd, cron).

Environment (typical)
---------------------
* ``GROQ_API_KEY``, ``GEMINI_API_KEY`` — required for LLM phases.
* ``SCHEDULER_PHASE1_MODE`` — ``auto`` (default), ``incremental``, or ``backfill``.
  ``auto`` bootstraps missing lookback weeks and then behaves incrementally.
* ``SCHEDULER_SKIP_BACKFILL`` — if ``1``/``true``, skip ``run_backfill.py`` and use
  ``SCHEDULER_WEEK`` (or current ISO week); requires ``data/consolidated/<week>_full.csv``.
* Google Docs MCP append (optional): ``GOOGLE_CLIENT_ID``, ``GOOGLE_CLIENT_SECRET``,
  token at ``~/.config/google-docs-mcp/token.json`` (CI: write from a secret),
  ``GOOGLE_DOCS_APPEND_TRANSPORT=mcp``, and ``--google-doc-append`` on Phase 4.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _py() -> str:
    return sys.executable


def _run(cmd: list[str], *, extra_env: dict[str, str] | None = None) -> None:
    line = " ".join(cmd)
    print(f"+ {line}", flush=True)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def _current_iso_week() -> str:
    out = subprocess.run(
        [
            _py(),
            "-c",
            "from phase1_ingestion.scraper import get_current_iso_week; "
            "print(get_current_iso_week())",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _phase1_mode() -> str:
    mode = (os.getenv("SCHEDULER_PHASE1_MODE") or "auto").strip().lower()
    if mode not in {"auto", "incremental", "backfill"}:
        print(
            f"warning: unsupported SCHEDULER_PHASE1_MODE={mode!r}; defaulting to 'auto'",
            flush=True,
        )
        return "auto"
    return mode


def _run_phase1_delta(week: str) -> None:
    """Ensure lookback window caches exist, fetching only missing/invalid weeks."""
    from phase1_ingestion.cache_manager import (
        compute_lookback_window,
        expire_old_weeks,
        load_week_cache,
        merge_weekly_csvs,
        save_consolidated,
        save_week_cache,
    )
    from phase1_ingestion.filter import filter_reviews
    from phase1_ingestion.scraper import fetch_reviews_for_week

    window = compute_lookback_window(week)
    missing: list[str] = []
    present: list[str] = []

    for w in window:
        df = load_week_cache(w)
        if df is None:
            missing.append(w)
        else:
            present.append(w)

    if missing:
        mode_name = "bootstrap" if not present else "incremental"
        print(
            f"=== Phase 1 ({mode_name}): need {len(missing)} week(s): {', '.join(missing)} ===",
            flush=True,
        )
        for w in missing:
            raw = fetch_reviews_for_week(w)
            clean, stats = filter_reviews(raw)
            save_week_cache(w, clean)
            print(
                f"phase1: {w} fetched={len(raw)} passed={stats.get('passed', 0)}",
                flush=True,
            )
            # Small delay to reduce pressure on Play Store API.
            time.sleep(1)
    else:
        print("=== Phase 1 (incremental): window already complete; no fetch needed ===", flush=True)

    expired = expire_old_weeks(window)
    if expired:
        print(f"phase1: expired old cache week(s): {', '.join(expired)}", flush=True)

    merged_df = merge_weekly_csvs(window)
    consolidated_path = save_consolidated(merged_df, week)
    print(f"phase1: consolidated ready at {consolidated_path}", flush=True)


def run_scheduled_pipeline() -> int:
    """
    Run the full weekly pipeline for the target ISO week.

    * Without ``SCHEDULER_SKIP_BACKFILL``: runs ``run_backfill.py`` (Play Store fetch +
      consolidate), then phases 2–4 for **current** ISO week (same anchor as backfill).
    * With ``SCHEDULER_SKIP_BACKFILL``: phases 2–4 only for ``SCHEDULER_WEEK`` or current week.
    """
    py = _py()
    skip = os.getenv("SCHEDULER_SKIP_BACKFILL", "").lower() in ("1", "true", "yes")
    phase1_mode = _phase1_mode()

    if skip:
        week = (os.getenv("SCHEDULER_WEEK") or "").strip() or _current_iso_week()
        consolidated = ROOT / "data" / "consolidated" / f"{week}_full.csv"
        if not consolidated.is_file():
            print(
                f"error: SCHEDULER_SKIP_BACKFILL=1 but missing {consolidated}",
                file=sys.stderr,
            )
            return 1
        print(f"=== skip backfill; using existing {consolidated.name} ===", flush=True)
    else:
        week = _current_iso_week()
        if phase1_mode == "backfill":
            print("=== Phase 1 (forced backfill): backfill + consolidate ===", flush=True)
            _run([py, "run_backfill.py"])
        elif phase1_mode == "incremental":
            print("=== Phase 1 (forced incremental): fill missing + consolidate ===", flush=True)
            _run_phase1_delta(week)
        else:
            print("=== Phase 1 (auto): bootstrap/incremental decision by cache state ===", flush=True)
            _run_phase1_delta(week)

    print(f"=== target ISO week: {week} ===", flush=True)

    print("=== Phase 2: tag (map) ===", flush=True)
    _run([py, "-m", "phase2_clustering.tagger", "--week", week])

    print("=== Phase 2: theme reduce ===", flush=True)
    _run([py, "-m", "phase2_clustering.theme_aggregator", "--week", week])

    print("=== Phase 3: insights ===", flush=True)
    _run([py, "-m", "phase3_insights.insight_extractor", "--week", week])

    print("=== Phase 4: report + optional Google Doc append ===", flush=True)
    _run([py, "-m", "phase4_report.report_generator", "--week", week, "--google-doc-append"])

    _maybe_email_weekly_report()

    print("=== scheduler: done ===", flush=True)
    return 0


def _maybe_email_weekly_report() -> None:
    """If ``EMAIL_REPORT_AFTER_PIPELINE=true``, email latest pulse via SMTP (see docs/WEB_DASHBOARD.md)."""
    if os.getenv("EMAIL_REPORT_AFTER_PIPELINE", "").lower() not in ("1", "true", "yes"):
        return
    try:
        from web.services.mailer import send_latest_pulse_email

        iso, recs = send_latest_pulse_email()
        print(f"=== email report sent: {iso} -> {recs} ===", flush=True)
    except Exception as e:
        print(f"warning: EMAIL_REPORT_AFTER_PIPELINE set but send failed: {e}", flush=True)


def main() -> int:
    try:
        return run_scheduled_pipeline()
    except subprocess.CalledProcessError as e:
        print(f"scheduler failed: exit {e.returncode}", file=sys.stderr)
        return e.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
