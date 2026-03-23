import json
from datetime import datetime

import pandas as pd
from phase1_ingestion.scraper import fetch_reviews_for_week, get_current_iso_week
from phase1_ingestion.filter import filter_reviews
from phase1_ingestion.cache_manager import save_week_cache
from shared.logger import init_logger
import config

week = get_current_iso_week()
init_logger(f"dev_{week}", week, "INFO")

print(f"Fetching reviews for {week}...")
raw = fetch_reviews_for_week(week)

print(f"Filtering {len(raw)} raw reviews...")
clean, stats = filter_reviews(raw)

print(f"Saving to cache...")
saved_path = save_week_cache(week, clean)

print(f"\n--- Output Saved to: {saved_path} ---")
print(f"Filter Stats: {json.dumps(stats, indent=2)}")

if clean:
    df = pd.read_csv(saved_path)
    print("\n--- SAMPLE ROW FROM SAVED CSV ---")
    print(df.head(1).T)
else:
    print("\nNo reviews passed the filters, CSV is empty.")
