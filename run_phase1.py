from datetime import datetime
import json
from phase1_ingestion.scraper import fetch_reviews_for_week, get_current_iso_week
from phase1_ingestion.filter import filter_reviews
from phase1_ingestion.cache_manager import save_week_cache
from shared.logger import init_logger
import config

week = get_current_iso_week()
init_logger(f"dev_{week}", week, "INFO")
raw = fetch_reviews_for_week(week)
clean, stats = filter_reviews(raw)
saved_path = save_week_cache(week, clean)

print(f"\nSaved CSV path: {saved_path}")
print(f"Stats: {json.dumps(stats, indent=2)}")

import pandas as pd
df = pd.read_csv(saved_path)
print("\n--- SAMPLE ROW FROM CSV ---")
print(df.head(1).T)
