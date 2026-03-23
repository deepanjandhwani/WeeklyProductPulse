"""
phase3_insights — Phase 3: Insight extraction.

insight_extractor
    Top themes from ``theme_summary.json``, sentiment + top-upvoted candidates (Python),
    Gemini JSON quote selection, regex PII scrub → ``<week>_insights.json``.
"""

from phase3_insights.insight_extractor import extract_insights

__all__ = ["extract_insights"]
