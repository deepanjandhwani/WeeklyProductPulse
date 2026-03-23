"""
phase2_clustering/theme_aggregator.py — Reduce phase for AI Theme Tagging.

Responsibilities
----------------
* Load parsed AI tags (`data/tagged/<week>_tagged.csv`).
* **Option B (default):** merge raw batch tags into <= MAX_THEMES canonical themes via Groq (LLM reduce).
* **Fallback:** fuzzy string matching (RapidFuzz) when `THEME_MERGE_MODE=fuzzy` or LLM fails.
* Count frequencies of each merged cluster and export JSON for Phase 3.
"""

import json
import logging
import argparse
from pathlib import Path
from rapidfuzz import fuzz, process
import pandas as pd

import config
from phase1_ingestion.scraper import get_current_iso_week
from shared.llm_clients.groq_client import generate_json_response

logger = logging.getLogger("weekly_pulse")

# --- Option B: LLM merge (Groq) — maps each normalized raw tag → canonical theme ---
_LLM_MERGE_SYSTEM_TEMPLATE = """
You merge duplicate theme labels produced by batched tagging for IndMoney (in.indwealth), a fintech app.

Input is a JSON object with key "tags": a list of objects, each with:
- "tag": exact theme string from the tagger (preserve casing/spacing as given)
- "count": integer review count for that tag
- "example_snippet": short user quote illustrating the tag (may be empty)

Task:
1. Produce at most {max_themes} canonical product theme names (2–4 words, Title Case).
2. Map EVERY input "tag" to exactly one canonical theme. Use the EXACT "tag" string as each mapping key.
3. Merge synonyms and near-duplicates (e.g. "Login Error" and "Error Login").
4. Do NOT merge clearly opposite sentiments (e.g. "Great UI" vs "Bad UI").
5. Map "Uncategorized" / empty / null-like tags to "Uncategorized".

Return ONLY valid JSON with this exact shape:
{{
  "mapping": {{
    "<exact tag from input>": "<canonical theme name>",
    ...
  }}
}}
""".strip()


def _llm_merge_system_prompt() -> str:
    return _LLM_MERGE_SYSTEM_TEMPLATE.format(max_themes=config.MAX_THEMES)

def _normalize_tag(tag: str) -> str:
    """Basic clean up before fuzzy matching to improve accuracy."""
    if not isinstance(tag, str):
        return "Uncategorized"
    
    clean = tag.strip().title()
    if clean.lower() in ["none", "n/a", "null", "no theme", "uncategorized", ""]:
        return "Uncategorized"
    return clean

def _is_opposite_sentiment(a: str, b: str) -> bool:
    """Prevent strings sharing a root noun with opposite adjectives from merging."""
    positive = {"good", "great", "best", "excellent", "super", "nice", "awesome"}
    negative = {"bad", "worst", "poor", "terrible", "horrible", "awful", "disappointing"}
    
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    
    if (a_words & positive and b_words & negative) or (a_words & negative and b_words & positive):
        return True
    return False

def cluster_tags(raw_tags_series: pd.Series) -> dict[str, str]:
    """
    Given a Series of all tags (one per review), find the most common ones
    and merge less common fuzzy matches into them.
    
    Returns:
        A mapping dict: { "Original Tag": "Merged Centroid Tag" }
    """
    # 1. Clean and count exact matches first
    value_counts = raw_tags_series.apply(_normalize_tag).value_counts()
    
    # 2. Iterate from most popular to least popular to form centroids
    centroids = []
    mapping = {}
    
    threshold = config.THEME_MERGE_THRESHOLD * 100  # RapidFuzz uses 0-100 scale
    
    for tag in value_counts.index:
        if tag == "Uncategorized":
            mapping[tag] = tag
            continue
            
        # Is this tag similar to an existing, more popular centroid?
        # We use token_sort_ratio to ignore word order ("Error Login" == "Login Error")
        if centroids:
            # process.extractOne returns (match_string, score, index)
            best_match = process.extractOne(
                tag, 
                centroids, 
                scorer=fuzz.token_sort_ratio
            )
            
            if best_match and best_match[1] >= threshold:
                # Merge into existing larger centroid only if sentiments do not clash
                if not _is_opposite_sentiment(tag, best_match[0]):
                    mapping[tag] = best_match[0]
                    continue
                
        # If no good match, it becomes a new centroid
        centroids.append(tag)
        mapping[tag] = tag

    return mapping


def _build_tag_counts_and_examples(df: pd.DataFrame) -> tuple[pd.Series, dict[str, str]]:
    """Per-normalized-tag counts and one example review snippet per tag."""
    df = df.copy()
    df["normalized_raw_tag"] = df["theme_tag"].apply(_normalize_tag)
    counts = df["normalized_raw_tag"].value_counts()
    examples: dict[str, str] = {}
    for tag in counts.index:
        sub = df[df["normalized_raw_tag"] == tag]
        if sub.empty:
            examples[tag] = ""
            continue
        text = str(sub.iloc[0].get("review_text", "") or "")[:220]
        examples[tag] = text
    return counts, examples


def merge_tags_with_llm(
    value_counts: pd.Series,
    tag_examples: dict[str, str],
) -> dict[str, str] | None:
    """
    Option B: ask Groq to map each raw tag string to a canonical theme (<= MAX_THEMES distinct).

    Tags beyond THEME_MERGE_MAX_UNIQUE_TAGS are assigned to the nearest canonical theme via fuzzy match.
    """
    full_keys = list(value_counts.index)  # sorted by frequency descending
    if not full_keys:
        return {}

    keys_for_llm = full_keys[: config.THEME_MERGE_MAX_UNIQUE_TAGS]
    tags_payload = [
        {
            "tag": tag,
            "count": int(value_counts[tag]),
            "example_snippet": tag_examples.get(tag, "")[:220],
        }
        for tag in keys_for_llm
    ]
    user_obj = {
        "tags": tags_payload,
        "max_canonical_themes": config.MAX_THEMES,
    }
    user_prompt = json.dumps(user_obj, ensure_ascii=False)

    try:
        resp = generate_json_response(_llm_merge_system_prompt(), user_prompt)
    except Exception as e:
        logger.error(f"LLM theme merge failed: {e}", exc_info=True)
        return None

    if not resp or not isinstance(resp, dict):
        logger.error("LLM theme merge: empty or non-object response")
        return None
    mapping_raw = resp.get("mapping")
    if not isinstance(mapping_raw, dict):
        logger.error("LLM theme merge: missing or invalid 'mapping'")
        return None

    out: dict[str, str] = {}

    def _resolve_value(v) -> str:
        if v is None:
            return "Uncategorized"
        s = str(v).strip()
        return s if s else "Uncategorized"

    # Map keys we sent to the LLM (exact or case-insensitive key match)
    for tag in keys_for_llm:
        if tag in mapping_raw:
            out[tag] = _resolve_value(mapping_raw[tag])
            continue
        matched_val = None
        for mk, mv in mapping_raw.items():
            if str(mk).strip() == tag or str(mk).strip().lower() == tag.lower():
                matched_val = mv
                break
        if matched_val is not None:
            out[tag] = _resolve_value(matched_val)
        else:
            logger.warning(f"LLM theme merge: missing mapping for tag {tag!r}")
            return None

    # Assign remaining tags (if any) to nearest canonical theme name
    canonical_pool = sorted({v for v in out.values() if v.lower() != "uncategorized"})
    if not canonical_pool:
        canonical_pool = ["General Feedback"]

    for tag in full_keys:
        if tag in out:
            continue
        best = process.extractOne(tag, canonical_pool, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= 55:
            out[tag] = best[0]
        else:
            out[tag] = tag

    # Enforce <= MAX_THEMES distinct canonical values (excluding Uncategorized)
    canon_set = {v for k, v in out.items() if v.lower() != "uncategorized"}
    if len(canon_set) > config.MAX_THEMES:
        logger.warning(
            f"LLM merge produced {len(canon_set)} canonical themes (> {config.MAX_THEMES}); using fuzzy fallback."
        )
        return None

    return out


def generate_theme_summary(iso_week: str, *, merge_mode_override: str | None = None) -> Path | None:
    """Group reviews by merged themes (LLM reduce by default) and export JSON for Phase 3.

    merge_mode_override: if ``"fuzzy"``, skip Groq merge; if ``None``, use ``config.THEME_MERGE_MODE``.
    """
    
    tagged_path = config.TAGGED_DIR / f"{iso_week}_tagged.csv"
    if not tagged_path.exists():
        logger.error(f"Tagged data not found: {tagged_path}. Please run Tagger Map phase first.")
        return None
        
    df = pd.read_csv(tagged_path)

    value_counts, tag_examples = _build_tag_counts_and_examples(df)
    merge_mode_used = "fuzzy"

    mode = (merge_mode_override or getattr(config, "THEME_MERGE_MODE", "llm")).lower()
    if mode == "llm":
        llm_mapping = merge_tags_with_llm(value_counts, tag_examples)
        if llm_mapping is not None:
            mapping = llm_mapping
            merge_mode_used = "llm"
        else:
            logger.warning("LLM theme merge unavailable; falling back to fuzzy clustering.")
            mapping = cluster_tags(df["theme_tag"])
    else:
        mapping = cluster_tags(df["theme_tag"])

    # Apply mapping to normalized tags
    df["normalized_raw_tag"] = df["theme_tag"].apply(_normalize_tag)
    df["merged_theme"] = df["normalized_raw_tag"].map(mapping)
    
    # Count final themes
    theme_counts = df["merged_theme"].value_counts()
    
    # Take the top N (excluding Uncategorized if possible, unless it's dominant)
    valid_themes = theme_counts.drop("Uncategorized", errors="ignore")
    top_theme_names = valid_themes.head(config.MAX_THEMES).index.tolist()
    
    summary = {
        "iso_week": iso_week,
        "total_reviews": len(df),
        "theme_merge_mode": merge_mode_used,
        "themes": []
    }
    
    for theme in top_theme_names:
        theme_df = df[df["merged_theme"] == theme]
        
        # Sort reviews within the theme by rating (worst first) and upvotes (highest first)
        theme_df = theme_df.sort_values(by=["rating", "thumbs_up_count"], ascending=[True, False])
        
        reviews_list = []
        for _, row in theme_df.iterrows():
            reviews_list.append({
                "review_id": row["review_id"],
                "rating": int(row["rating"]),
                "thumbs_up": int(row["thumbs_up_count"]),
                "text": str(row["review_text"])
            })
            
        summary["themes"].append({
            "theme_name": theme,
            "review_count": len(theme_df),
            "reviews": reviews_list
        })
        
    output_path = config.TAGGED_DIR / f"{iso_week}_theme_summary.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Phase 2 Reduce Step complete. Identified {len(summary['themes'])} top themes -> {output_path.name}")
    return output_path

if __name__ == "__main__":
    from shared.logger import init_logger
    
    parser = argparse.ArgumentParser(description="Phase 2 Reduce: Merge AI Themes")
    parser.add_argument("--week", default=get_current_iso_week(), help="ISO week target")
    parser.add_argument("--log-level", default=config.LOG_LEVEL)
    parser.add_argument(
        "--fuzzy",
        action="store_true",
        help="Use fuzzy (RapidFuzz) merge only; skip Groq LLM reduce",
    )
    args = parser.parse_args()

    init_logger(f"aggregator_{args.week}", args.week, args.log_level)
    generate_theme_summary(args.week, merge_mode_override="fuzzy" if args.fuzzy else None)
