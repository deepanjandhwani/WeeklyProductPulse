"""
Scheduler service — single entry point for cron / GitHub Actions.

Run: ``python -m scheduler`` from the project root (same directory as ``config.py``).
"""

from .run_pipeline import main, run_scheduled_pipeline

__all__ = ["main", "run_scheduled_pipeline"]
