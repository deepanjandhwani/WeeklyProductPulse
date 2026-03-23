import pytest
import pandas as pd
from phase2_clustering.theme_aggregator import _normalize_tag, cluster_tags

def test_normalize_tag():
    assert _normalize_tag(" UI Bug ") == "Ui Bug"
    assert _normalize_tag("login error") == "Login Error"
    assert _normalize_tag("N/A") == "Uncategorized"
    assert _normalize_tag("") == "Uncategorized"
    assert _normalize_tag(None) == "Uncategorized"

def test_cluster_tags():
    # Simulate a raw series of LLM output tags
    # "Login Error" should be the centroid because it has the most occurrences
    raw_tags = pd.Series([
        "Login Error", "Login Error", "Login Error",
        "login error",
        "Error Login",  # Should merge into "Login Error" due to token sort
        "Login Issue",  # Might merge or not depending on threshold, let's test absolute identical token sorts
        "App Crash", "App Crash",
        "Crash App",    # Should merge into "App Crash"
        "Great UI", 
        "N/A", "Unknown"
    ])
    
    mapping = cluster_tags(raw_tags)
    
    # "Login Error" has 4 direct matches initially, so it's the biggest centroid
    assert mapping["Error Login"] == "Login Error"
    assert mapping["Crash App"] == "App Crash"
    assert "Uncategorized" in mapping.values()

def test_cluster_tags_thresholds():
    # If the threshold is 0.75, "High Brokerage" and "High Brokerage Fees" might merge
    tags = pd.Series([
        "High Brokerage", "High Brokerage", "High Brokerage",
        "High Brokerage Fees",
        "Customer Support", "Customer Support",
        "Bad Customer Support" 
    ])
    
    mapping = cluster_tags(tags)
    
    # "High Brokerage" is the centroid (count=3)
    # The token_sort_ratio between "High Brokerage" and "High Brokerage Fees" is high
    assert mapping["High Brokerage Fees"] == "High Brokerage"
    
    # "Customer Support" is the centroid
    assert mapping["Bad Customer Support"] == "Customer Support"
