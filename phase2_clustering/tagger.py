"""
phase2_clustering/tagger.py — Batched Map phase for AI Theme Tagging.

Responsibilities
----------------
* Load the latest consolidated Play Store reviews (Phase 1).
* Split reviews into context-friendly batches (e.g., 50 per batch).
* Ask Groq Llama 3.3 to assign exactly one 1-3 word `theme_tag` to each review.
* Save the output dataset to data/tagged/<week>_tagged.csv.
"""

import json
import logging
import argparse
from pathlib import Path
import pandas as pd
from tqdm import tqdm

import config
from phase1_ingestion.scraper import get_current_iso_week
from shared.llm_clients.groq_client import generate_json_response

logger = logging.getLogger("weekly_pulse")

SYSTEM_PROMPT = """
You are an expert product analyst categorizing user reviews for a finance app (IndMoney).
Your task is to assign exactly ONE strict 1-3 word `theme_tag` to each review provided.
Always use consistent, concise tags (e.g., "Login Error", "High Brokerage", "Great UI", "Customer Support", "App Crash", "Feature Request").

Return ONLY a valid JSON object strictly matching this schema:
{
  "tagged_reviews": [
    {
      "review_id": "string",
      "theme_tag": "string"
    }
  ]
}
"""

def generate_tags_for_batch(batch: pd.DataFrame) -> list[dict]:
    """Ask Groq to process a single batch of reviews."""
    
    # Prepare minimal representation for the LLM to save tokens
    prompt_data = []
    for _, row in batch.iterrows():
        prompt_data.append({
            "review_id": row["review_id"],
            "rating": row["rating"],
            "text": row["review_text"]
        })
    
    user_prompt = json.dumps(prompt_data, ensure_ascii=False)
    
    try:
        response = generate_json_response(SYSTEM_PROMPT, user_prompt)
        if response and "tagged_reviews" in response:
            tagged = response["tagged_reviews"]
            if not isinstance(tagged, list):
                logger.error("Groq returned non-list tagged_reviews payload.")
                return []
            return tagged
        else:
            logger.error(f"Groq did not return 'tagged_reviews' array. Response keys: {response.keys() if response else 'None'}")
            return []
    except Exception as e:
        logger.error(f"Batch generation failed: {e}", exc_info=True)
        return []


def run_map_phase(iso_week: str) -> Path | None:
    """Read Phase 1 consolidated CSV, tag it via Groq, save to Phase 2 tagged CSV."""
    
    # 1. Locate Phase 1 Input
    consolidated_path = config.CONSOLIDATED_DIR / f"{iso_week}_full.csv"
    if not consolidated_path.exists():
        logger.error(f"Phase 1 data not found: {consolidated_path}. Please run Phase 1 Ingestion first.")
        return None
        
    df = pd.read_csv(consolidated_path)
    logger.info(f"Loaded {len(df)} reviews from Phase 1 target: {consolidated_path.name}")
    
    # 2. Batch Processing
    batch_size = config.BATCH_SIZE
    all_tags = []
    
    # Iterate through chunks
    num_batches = (len(df) + batch_size - 1) // batch_size
    logger.info(f"Splitting into {num_batches} batches (max {batch_size} reviews/batch) to avoid LLM context loss.")
    
    for i in tqdm(range(num_batches), desc="Calling Groq LLM"):
        start_idx = i * batch_size
        end_idx = start_idx + batch_size
        batch_df = df.iloc[start_idx:end_idx]
        
        tags = generate_tags_for_batch(batch_df)
        all_tags.extend(tags)
    
    if not all_tags:
        logger.error("Failed to generate any tags. Check API keys or rate limits.")
        return None
        
    # 3. Merge results with original dataframe
    tags_df = pd.DataFrame(all_tags)
    if not {"review_id", "theme_tag"}.issubset(tags_df.columns):
        logger.error("Tagger response missing required columns: review_id/theme_tag")
        return None

    # Keep only known review IDs and de-duplicate any repeated model outputs.
    expected_ids = set(df["review_id"].astype(str))
    tags_df["review_id"] = tags_df["review_id"].astype(str)
    tags_df["theme_tag"] = tags_df["theme_tag"].astype(str)
    unknown_ids = set(tags_df["review_id"]) - expected_ids
    if unknown_ids:
        logger.warning(f"Tagger returned {len(unknown_ids)} unknown review_id(s); ignoring them.")
    tags_df = tags_df[tags_df["review_id"].isin(expected_ids)]
    tags_df = tags_df.drop_duplicates(subset=["review_id"], keep="first")
    
    # It is possible the LLM lost/skipped a review or hallucinated an ID. Merge strictly on review_id.
    tagged_full_df = pd.merge(df, tags_df, on="review_id", how="left")
    
    # Fill any reviews the LLM skipped with a default tag
    missing_count = tagged_full_df["theme_tag"].isna().sum()
    if missing_count > 0:
        logger.warning(f"LLM failed to tag {missing_count} reviews. Filling with 'Uncategorized'.")
        tagged_full_df["theme_tag"].fillna("Uncategorized", inplace=True)
        
    # 4. Save Phase 2 Output
    output_path = config.TAGGED_DIR / f"{iso_week}_tagged.csv"
    tagged_full_df.to_csv(output_path, index=False, encoding="utf-8")
    
    size_kb = round(output_path.stat().st_size / 1024, 1)
    logger.info(f"Phase 2 Map Step complete. Saved -> {output_path.name} ({size_kb} KB)")
    
    return output_path


if __name__ == "__main__":
    from shared.logger import init_logger
    
    parser = argparse.ArgumentParser(description="Phase 2 Tagging: Assign AI Themes to Reviews")
    parser.add_argument("--week", default=get_current_iso_week(), help="ISO week target")
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    args = parser.parse_args()

    init_logger(f"tagger_{args.week}", args.week, args.log_level)
    run_map_phase(args.week)
