"""
config.py — Central configuration for WeeklyProductPulse.

All tunable constants live here. Secrets (API keys) are loaded from .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present (local dev). In CI, secrets come from GitHub Secrets.
load_dotenv()

# ── Project Root ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()

# ── Play Store ────────────────────────────────────────────────────────────────
APP_ID = "in.indwealth"                 # IndMoney Play Store package name
REVIEW_LANG = "en"                      # Language filter for reviews
REVIEW_COUNTRY = "in"                   # Country filter (India)
MAX_REVIEWS_PER_WEEK = int(os.getenv("MAX_REVIEWS_PER_WEEK", 3000))

# ── Time Window ───────────────────────────────────────────────────────────────
LOOKBACK_WEEKS = 12                     # How many weeks of reviews to analyse
LOG_RETENTION_WEEKS = 12               # How long to keep log files

# ── Filtering ─────────────────────────────────────────────────────────────────
MIN_WORD_COUNT = 10                     # Skip reviews shorter than this

# ── File Paths ────────────────────────────────────────────────────────────────
DATA_DIR         = BASE_DIR / "data"
CACHE_DIR        = DATA_DIR / "cache"           # Weekly raw CSVs
CONSOLIDATED_DIR = DATA_DIR / "consolidated"    # Merged lookback-window CSVs
TAGGED_DIR       = DATA_DIR / "tagged"          # Theme-tagged CSVs (Phase 2)
REPORTS_DIR      = DATA_DIR / "reports"         # Final pulse reports (Phase 4)

LOGS_DIR         = BASE_DIR / "logs"
RUNS_LOG_DIR     = LOGS_DIR / "runs"            # Per-run .jsonl logs
LLM_AUDIT_DIR    = LOGS_DIR / "llm_audit"       # LLM call audit .jsonl logs

PROMPTS_DIR      = BASE_DIR / "prompts"

# ── Phase 2: Theme Clustering ─────────────────────────────────────────────────
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL       = "llama-3.3-70b-versatile"
BATCH_SIZE       = 80                   # Reviews per Groq API call
MAX_THEMES       = 5                    # Maximum distinct themes to surface
THEME_MERGE_THRESHOLD = 0.75           # Fuzzy ratio to merge near-duplicate theme names (fuzzy fallback)
# Phase 2 reduce: "llm" = Option B (Groq merges raw tags → canonical themes); "fuzzy" = RapidFuzz only
THEME_MERGE_MODE = os.getenv("THEME_MERGE_MODE", "llm").lower()
THEME_MERGE_MAX_UNIQUE_TAGS = int(os.getenv("THEME_MERGE_MAX_UNIQUE_TAGS", "100"))

# ── Phase 3 & 4: Insight + Report ─────────────────────────────────────────────
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
# Override in .env if a model hits quota, e.g. GEMINI_MODEL=gemini-2.0-flash-lite
GEMINI_MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
TOP_THEMES       = 3                    # Number of top themes for the report
QUOTES_PER_REPORT = 3                  # One quote per top theme
TOP_REVIEWS_PER_THEME = 10            # Candidate reviews fed to quote selector
MAX_REPORT_WORDS = 250                 # Hard cap on weekly note word count
# Phase 3: if false, quote LLM must succeed for all themes or no insights file is written (no thumbs-up fallback)
PHASE3_ALLOW_FALLBACK = os.getenv("PHASE3_ALLOW_FALLBACK", "true").lower() in ("1", "true", "yes")
# Phase 3 quote selection: "groq" (default, same stack as Phase 2) | "gemini"
PHASE3_QUOTE_LLM = os.getenv("PHASE3_QUOTE_LLM", "groq").lower()
# Optional Groq model override for Phase 3 only (defaults to GROQ_MODEL)
PHASE3_GROQ_MODEL = os.getenv("PHASE3_GROQ_MODEL", GROQ_MODEL)
# Phase 4 weekly pulse: "groq" (default) | "gemini" (ARCHITECTURE §4.1–4.2)
PHASE4_REPORT_LLM = os.getenv("PHASE4_REPORT_LLM", "groq").lower()
PHASE4_GROQ_MODEL = os.getenv("PHASE4_GROQ_MODEL", GROQ_MODEL)
# Phase 4 fee block: curated JSON at prompts/fee_scenarios.json (exactly one scenario; facts only; no LLM)
FEE_SECTION_ENABLED = os.getenv("FEE_SECTION_ENABLED", "true").lower() in ("1", "true", "yes")
# Optional: must match the single scenario id in fee_scenarios.json if set (otherwise ignored with a warning)
FEE_SCENARIO_ID = os.getenv("FEE_SCENARIO_ID", "").strip()

# Google Docs: optional append after Phase 4 (see docs/GOOGLE_DOCS.md)
GOOGLE_DOCS_DOCUMENT_ID = os.getenv("GOOGLE_DOCS_DOCUMENT_ID", "").strip()
GOOGLE_DOCS_APPEND_ENABLED = os.getenv("GOOGLE_DOCS_APPEND_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)
# Append transport: "direct" = google-api-python-client + service account;
# "mcp" = spawn @a-bonus/google-docs-mcp (OAuth token; needs npx + Node on PATH).
GOOGLE_DOCS_APPEND_TRANSPORT = os.getenv("GOOGLE_DOCS_APPEND_TRANSPORT", "direct").lower()

# ── Retry / Back-off ──────────────────────────────────────────────────────────
MAX_RETRIES      = 3
RETRY_BASE_DELAY = 2                   # Seconds; doubles each attempt

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ── Ensure directories exist on import ───────────────────────────────────────
for _dir in [
    CACHE_DIR, CONSOLIDATED_DIR, TAGGED_DIR, REPORTS_DIR,
    RUNS_LOG_DIR, LLM_AUDIT_DIR, PROMPTS_DIR,
]:
    _dir.mkdir(parents=True, exist_ok=True)
