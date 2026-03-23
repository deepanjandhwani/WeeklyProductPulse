"""Smoke import for scheduler package."""

def test_scheduler_import():
    from scheduler.run_pipeline import ROOT, run_scheduled_pipeline

    assert ROOT.name == "WeeklyProductPulse" or (ROOT / "config.py").is_file()
