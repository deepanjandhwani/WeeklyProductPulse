"""
src/logger.py — Structured JSON logger for WeeklyProductPulse.

Two distinct loggers:
  1. Pipeline logger  → logs/runs/run_<WEEK>.jsonl  (one file per weekly run)
  2. LLM audit logger → logs/llm_audit/<provider>_<WEEK>.jsonl  (per LLM provider)

Console output is human-readable; file output is one JSON object per line
(JSON Lines / JSONL format) so logs are easily grep-able and machine-parseable.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── JSON Formatter ─────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Serialises each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "phase":     getattr(record, "phase", "orchestrator"),
            "run_id":    getattr(record, "run_id", None),
            "event":     record.getMessage(),
        }
        # Attach any structured payload passed via extra={"data": {...}}
        if hasattr(record, "data"):
            entry["data"] = record.data
        # Attach exception info if present
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


# ── Human-Readable Console Formatter ──────────────────────────────────────────

_CONSOLE_FMT = "%(asctime)s [%(levelname)-8s] %(message)s"
_DATE_FMT    = "%Y-%m-%d %H:%M:%S"


# ── Public Factory Functions ───────────────────────────────────────────────────

def init_logger(
    run_id: str,
    week: str,
    log_level: str = "INFO",
) -> logging.Logger:
    """
    Initialise (or reinitialise) the main pipeline logger.

    Args:
        run_id:    Unique identifier for this pipeline run, e.g. 'run_2026-W11_20260315T2300'.
        week:      ISO-week string, e.g. '2026-W11'. Used to name the log file.
        log_level: Logging level string (DEBUG / INFO / WARNING / ERROR / CRITICAL).

    Returns:
        Configured Logger instance attached to 'weekly_pulse'.
    """
    from config import RUNS_LOG_DIR  # imported here to avoid circular deps

    logger = logging.getLogger("weekly_pulse")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    # ── Console handler (human-readable) ──────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))
    logger.addHandler(console_handler)

    # ── File handler (JSON Lines) ──────────────────────────────────────────────
    log_file = Path(RUNS_LOG_DIR) / f"run_{week}.jsonl"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    # Stamp every record from this logger with the run_id via a Filter
    class RunIDFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.run_id = run_id  # type: ignore[attr-defined]
            return True

    logger.addFilter(RunIDFilter())

    logger.info(
        "Logger initialised",
        extra={"phase": "orchestrator", "data": {"run_id": run_id, "week": week, "log_level": log_level}},
    )
    return logger


def get_llm_audit_logger(provider: str, week: str) -> logging.Logger:
    """
    Return a dedicated DEBUG-level logger for LLM prompt/response audit trails.

    Args:
        provider:  'groq' or 'gemini'.
        week:      ISO-week string, e.g. '2026-W11'.

    Returns:
        Logger instance named 'llm_audit.<provider>'.
    """
    from config import LLM_AUDIT_DIR  # imported here to avoid circular deps

    name = f"llm_audit.{provider}"
    audit_logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if audit_logger.handlers:
        return audit_logger

    audit_logger.setLevel(logging.DEBUG)
    audit_logger.propagate = False  # Don't bubble up to root / pipeline logger

    log_file = Path(LLM_AUDIT_DIR) / f"{provider}_{week}.jsonl"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(JSONFormatter())
    audit_logger.addHandler(handler)

    return audit_logger


# ── LLM Call Helper ────────────────────────────────────────────────────────────

def log_llm_call(
    audit_logger: logging.Logger,
    *,
    provider:      str,
    phase:         str,
    model:         str,
    prompt:        str,
    response:      str,
    input_tokens:  int,
    output_tokens: int,
    latency_ms:    int,
    status:        str,           # 'success' | 'rate_limited' | 'parse_error' | 'timeout'
    error:         str | None = None,
    batch_num:     int | None = None,
) -> None:
    """Log a single LLM API interaction to the audit trail."""
    audit_logger.debug(
        "llm_call",
        extra={
            "phase": phase,
            "data": {
                "provider":        provider,
                "model":           model,
                # Truncate long prompts/responses to keep file sizes manageable
                "prompt_preview":  prompt[:500] + "…" if len(prompt) > 500 else prompt,
                "response_preview": response[:500] + "…" if len(response) > 500 else response,
                "input_tokens":    input_tokens,
                "output_tokens":   output_tokens,
                "total_tokens":    input_tokens + output_tokens,
                "latency_ms":      latency_ms,
                "status":          status,
                "error":           error,
                "batch_num":       batch_num,
            },
        },
    )


# ── Run Summary Helper ─────────────────────────────────────────────────────────

def log_run_summary(
    logger: logging.Logger,
    *,
    run_id: str,
    week:   str,
    stats:  dict[str, Any],
) -> None:
    """
    Log a structured end-of-pipeline summary.

    Expected keys in stats:
        duration_sec, reviews_scraped, reviews_filtered, reviews_cached,
        reviews_new, groq_calls, groq_tokens, groq_avg_latency_ms,
        gemini_calls, gemini_tokens, theme_count, top_3, pii_redactions,
        report_words, report_path, errors, retries
    """
    status = "SUCCESS" if not stats.get("errors") else "PARTIAL"
    logger.info(
        f"── Run Summary ── Week {week} ── Status: {status}",
        extra={
            "phase":  "orchestrator",
            "run_id": run_id,
            "data":   {"week": week, "status": status, **stats},
        },
    )

    # Pretty-print to console as well
    sep = "─" * 52
    lines = [
        sep,
        f"  Run ID           : {run_id}",
        f"  Week             : {week}",
        f"  Duration         : {stats.get('duration_sec', '?')}s",
        f"  Reviews (total)  : {stats.get('reviews_filtered', '?')}  "
        f"({stats.get('reviews_cached', '?')} cached + {stats.get('reviews_new', '?')} new)",
        f"  Groq API calls   : {stats.get('groq_calls', '?')}  "
        f"({stats.get('groq_tokens', '?')} tokens)",
        f"  Gemini API calls : {stats.get('gemini_calls', '?')}  "
        f"({stats.get('gemini_tokens', '?')} tokens)",
        f"  Themes found     : {stats.get('theme_count', '?')}  "
        f"→ Top 3: {stats.get('top_3', ['?', '?', '?'])}",
        f"  PII redactions   : {stats.get('pii_redactions', '?')}",
        f"  Report           : {stats.get('report_words', '?')} words → {stats.get('report_path', '?')}",
        f"  Errors           : {stats.get('errors', 0)}  | Retries: {stats.get('retries', 0)}",
        f"  Status           : {'✅' if status == 'SUCCESS' else '⚠️ '} {status}",
        sep,
    ]
    for line in lines:
        logger.info(line)


# ── Log Rotation / Cleanup ─────────────────────────────────────────────────────

def cleanup_old_logs(retention_weeks: int = 12) -> None:
    """
    Delete log files for runs older than `retention_weeks`.
    Filename format expected: run_<YYYY>-W<WW>.jsonl or <provider>_<YYYY>-W<WW>.jsonl
    """
    from config import RUNS_LOG_DIR, LLM_AUDIT_DIR

    from datetime import timedelta
    cutoff = datetime.now() - timedelta(weeks=retention_weeks)

    deleted = 0
    for log_dir in [Path(RUNS_LOG_DIR), Path(LLM_AUDIT_DIR)]:
        for log_file in log_dir.glob("*.jsonl"):
            # Extract the YYYY-Www segment from filenames like 'run_2026-W01.jsonl'
            stem_parts = log_file.stem.split("_")
            week_str = next((p for p in stem_parts if p.startswith("20")), None)
            if not week_str:
                continue
            try:
                # %G-W%V-%u → ISO year / week / weekday (Monday=1)
                file_date = datetime.strptime(week_str + "-1", "%G-W%V-%u")
            except ValueError:
                continue
            if file_date < cutoff:
                log_file.unlink()
                deleted += 1

    root_logger = logging.getLogger("weekly_pulse")
    root_logger.info(
        "Log cleanup complete",
        extra={"data": {"deleted_files": deleted, "retention_weeks": retention_weeks}},
    )
