"""
phase1_ingestion — Data acquisition layer.

Modules
-------
scraper        : Fetches reviews from Google Play Store (in.indwealth).
filter         : Cleans and validates raw reviews (≥10 words, lookback window).
cache_manager  : Manages weekly CSV partitions and the consolidated lookback file.
"""
