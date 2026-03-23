#!/usr/bin/env bash
# End-to-end weekly pipeline: Phase 1 (optional) → 2 → 3 → 4 (+ MCP Google Doc append).
#
# Usage (from repo root — the folder that contains .env and phase*_ packages):
#   chmod +x scripts/run_e2e.sh
#   ./scripts/run_e2e.sh
#
# Skip the long Play Store backfill if you already have data/consolidated/<WEEK>_full.csv:
#   SKIP_BACKFILL=1 WEEK=2026-W12 ./scripts/run_e2e.sh
#
# Requires: .env with GROQ_API_KEY, GEMINI_API_KEY, GOOGLE_* for MCP append;
#           npx + ~/.config/google-docs-mcp/token.json for MCP append.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  # Parse .env safely without executing shell syntax.
  # Supports values containing spaces/special chars (e.g. SMTP_FROM display names).
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Trim leading/trailing whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    [[ "${line:0:1}" == "#" ]] && continue

    # Accept KEY=VALUE (and optional export KEY=VALUE)
    if [[ "$line" == export[[:space:]]* ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    [[ "$line" != *=* ]] && continue

    local key="${line%%=*}"
    local val="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#"${key%%[![:space:]]*}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"

    # Strip optional surrounding quotes
    if [[ "${val:0:1}" == "'" && "${val: -1}" == "'" ]]; then
      val="${val:1:${#val}-2}"
    elif [[ "${val:0:1}" == "\"" && "${val: -1}" == "\"" ]]; then
      val="${val:1:${#val}-2}"
    fi

    if [[ -n "$key" ]]; then
      export "$key=$val"
    fi
  done < "$env_file"
}

load_env_file ".env"

# After backfill, consolidated file is always named for *current* ISO week (see run_backfill.py).
if [[ "${SKIP_BACKFILL:-0}" != "1" ]]; then
  echo "=== Phase 1: fetch lookback window + consolidate (this can take many minutes) ==="
  "$PY" run_backfill.py
  WEEK="$("$PY" -c "from phase1_ingestion.scraper import get_current_iso_week; print(get_current_iso_week())")"
else
  WEEK="${WEEK:-$("$PY" -c "from phase1_ingestion.scraper import get_current_iso_week; print(get_current_iso_week())")}"
  CONS="data/consolidated/${WEEK}_full.csv"
  if [[ ! -f "$CONS" ]]; then
    echo "SKIP_BACKFILL=1 but missing $CONS — set WEEK=... to match an existing consolidated file, or run without SKIP_BACKFILL."
    exit 1
  fi
  echo "=== Phase 1: skipped (using existing $CONS) ==="
fi

echo "=== Target ISO week: $WEEK ==="

echo "=== Phase 2: tag (map) ==="
"$PY" -m phase2_clustering.tagger --week "$WEEK"

echo "=== Phase 2: theme reduce ==="
"$PY" -m phase2_clustering.theme_aggregator --week "$WEEK"

echo "=== Phase 3: insights + quotes ==="
"$PY" -m phase3_insights.insight_extractor --week "$WEEK"

echo "=== Phase 4: report + optional Google Doc append (MCP) ==="
export GOOGLE_DOCS_APPEND_TRANSPORT="${GOOGLE_DOCS_APPEND_TRANSPORT:-mcp}"
"$PY" -m phase4_report.report_generator --week "$WEEK" --google-doc-append

echo ""
echo "=== Done. Outputs under data/reports/ and data/tagged/ for week $WEEK ==="
