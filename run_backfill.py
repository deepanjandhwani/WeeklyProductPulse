import time
import pandas as pd
from phase1_ingestion.scraper import fetch_reviews_for_week, get_current_iso_week
from phase1_ingestion.filter import filter_reviews
from phase1_ingestion.cache_manager import compute_lookback_window, save_week_cache, merge_weekly_csvs, save_consolidated
from shared.logger import init_logger
import config

week = get_current_iso_week()
init_logger(f"backfill_{week}", week, "INFO")

print(f"--- STARTING {config.LOOKBACK_WEEKS}-WEEK BACKFILL ---")
# Get the last N weeks (from oldest to current week)
window = compute_lookback_window(week)
print(f"Target window: {window}\n")

for target_week in window:
    print(f"Fetching reviews for {target_week}...")
    raw = fetch_reviews_for_week(target_week)
    
    print(f"Filtering {len(raw)} raw reviews...")
    clean, stats = filter_reviews(raw)
    
    print(f"Saving to cache...")
    save_week_cache(target_week, clean)
    print(f"  → Passed: {stats['passed']} | Too short: {stats['skipped_too_short']} | Out of range: {stats['skipped_too_old']}\n")
    
    # Sleep to be polite to the Play Store API
    time.sleep(2)

print(f"--- CONSOLIDATING {config.LOOKBACK_WEEKS} WEEKS ---")
merged_df = merge_weekly_csvs(window)
consolidated_path = save_consolidated(merged_df, week)

print(f"\n✅ Total {config.LOOKBACK_WEEKS}-week dataset ready at: \n{consolidated_path}\n({len(merged_df)} total cleaned reviews)")
