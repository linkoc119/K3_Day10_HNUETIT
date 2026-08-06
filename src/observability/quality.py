from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings


import json
from pathlib import Path
from typing import Any
import pandas as pd

from core.config import Settings


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run data quality checks for completeness, uniqueness, and freshness, and save JSON reports.

    Checks:
    1. Completeness: fields 'title', 'summary' (abstract), and 'paper_id' must not be missing/empty.
    2. Uniqueness: 'paper_id' (and 'doi' if present) must not be duplicated.
    3. Freshness: 'age_days' must be >= 0 and 'published' date format must be valid (not 'NaT' or null).
    """
    quality_dir = Path(settings.paths.quality_dir)
    quality_dir.mkdir(parents=True, exist_ok=True)

    # Determine filename prefix based on report_name (use empty prefix for baseline)
    prefix = ""
    if report_name and report_name != "baseline":
        prefix = f"{report_name}_"

    results = {}

    # --- 1. Completeness Check ---
    completeness_status = "PASS"
    completeness_reasons = []

    # If DataFrame is empty, it fails completeness check
    if df.empty:
        completeness_status = "FAIL"
        completeness_reasons.append("DataFrame is empty.")
    else:
        # Check missing or empty title
        missing_title = df["title"].isna().sum() + (df["title"].astype(str).str.strip() == "").sum()
        if missing_title > 0:
            completeness_status = "FAIL"
            completeness_reasons.append(f"Found {missing_title} missing or empty title values.")
        
        # Check missing or empty summary (representing abstract)
        missing_summary = df["summary"].isna().sum() + (df["summary"].astype(str).str.strip() == "").sum()
        if missing_summary > 0:
            completeness_status = "FAIL"
            completeness_reasons.append(f"Found {missing_summary} missing or empty summary values.")
            
        # Check missing or empty paper_id
        missing_paper_id = df["paper_id"].isna().sum() + (df["paper_id"].astype(str).str.strip() == "").sum()
        if missing_paper_id > 0:
            completeness_status = "FAIL"
            completeness_reasons.append(f"Found {missing_paper_id} missing or empty paper_id values.")

    if completeness_status == "PASS":
        completeness_reasons.append("All records contain non-empty title, summary, and paper_id fields.")

    completeness_report = {
        "status": completeness_status,
        "reasons": completeness_reasons,
        "reason": "; ".join(completeness_reasons)
    }
    completeness_path = quality_dir / f"{prefix}completeness.json"
    with open(completeness_path, "w", encoding="utf-8") as f:
        json.dump(completeness_report, f, ensure_ascii=False, indent=2)
    results["completeness"] = completeness_report

    # --- 2. Uniqueness Check ---
    uniqueness_status = "PASS"
    uniqueness_reasons = []

    if df.empty:
        uniqueness_reasons.append("DataFrame is empty, no duplicates possible.")
    else:
        # Check uniqueness of paper_id
        duplicate_paper_ids = df["paper_id"].duplicated().sum()
        if duplicate_paper_ids > 0:
            uniqueness_status = "FAIL"
            uniqueness_reasons.append(f"Found {duplicate_paper_ids} duplicate paper_id values.")
        
        # Check uniqueness of doi if doi column exists
        if "doi" in df.columns:
            duplicate_dois = df["doi"].duplicated().sum()
            if duplicate_dois > 0:
                uniqueness_status = "FAIL"
                uniqueness_reasons.append(f"Found {duplicate_dois} duplicate doi values.")
        else:
            uniqueness_reasons.append("doi column not present, paper_id represents DOI.")

    if uniqueness_status == "PASS":
        uniqueness_reasons.append("All paper_ids (and DOIs if present) are unique.")

    uniqueness_report = {
        "status": uniqueness_status,
        "reasons": uniqueness_reasons,
        "reason": "; ".join(uniqueness_reasons)
    }
    uniqueness_path = quality_dir / f"{prefix}uniqueness.json"
    with open(uniqueness_path, "w", encoding="utf-8") as f:
        json.dump(uniqueness_report, f, ensure_ascii=False, indent=2)
    results["uniqueness"] = uniqueness_report

    # --- 3. Freshness Check ---
    freshness_status = "PASS"
    freshness_reasons = []

    if df.empty:
        freshness_status = "FAIL"
        freshness_reasons.append("DataFrame is empty.")
    else:
        # Check published date format errors (marked as 'NaT' or NaN)
        invalid_published = df["published"].isna().sum() + (df["published"].astype(str) == "NaT").sum()
        if invalid_published > 0:
            freshness_status = "FAIL"
            freshness_reasons.append(f"Found {invalid_published} records with missing or invalid published dates.")

        # Check age_days >= 0 (only for non-null/valid dates)
        if "age_days" in df.columns:
            # Drop null age_days to check values
            valid_age_days = df["age_days"].dropna()
            negative_age = (valid_age_days < 0).sum()
            if negative_age > 0:
                freshness_status = "FAIL"
                freshness_reasons.append(f"Found {negative_age} records with negative age_days.")
            
            # Check if any record is older than freshness threshold
            threshold = settings.freshness_threshold_days
            stale_count = (valid_age_days > threshold).sum()
            if stale_count > 0:
                freshness_status = "FAIL"
                freshness_reasons.append(f"Found {stale_count} records older than freshness threshold of {threshold} days.")
        else:
            freshness_status = "FAIL"
            freshness_reasons.append("Column 'age_days' is missing from the dataset.")

    if freshness_status == "PASS":
        freshness_reasons.append("All published dates are valid, age_days values are >= 0, and no stale records found.")

    freshness_report = {
        "status": freshness_status,
        "reasons": freshness_reasons,
        "reason": "; ".join(freshness_reasons)
    }
    freshness_path = quality_dir / f"{prefix}freshness.json"
    with open(freshness_path, "w", encoding="utf-8") as f:
        json.dump(freshness_report, f, ensure_ascii=False, indent=2)
    results["freshness"] = freshness_report

    return results


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Compile freshness report JSON and save it.

    Report contents:
    - latest_published: latest published date in YYYY-MM-DD
    - oldest_published: oldest published date in YYYY-MM-DD
    - stale_rows: count of papers with age_days > freshness_threshold_days
    - total_rows: total number of papers
    - is_fresh: true if there are no stale rows (or using appropriate domain heuristic)
    """
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if df.empty:
        report = {
            "latest_published": "N/A",
            "oldest_published": "N/A",
            "stale_rows": 0,
            "total_rows": 0,
            "is_fresh": False,
        }
    else:
        # Filter out invalid dates for min/max
        valid_dates = df[df["published"] != "NaT"]["published"].dropna()
        latest_pub = valid_dates.max() if not valid_dates.empty else "N/A"
        oldest_pub = valid_dates.min() if not valid_dates.empty else "N/A"

        threshold = settings.freshness_threshold_days
        stale_count = 0
        if "age_days" in df.columns:
            stale_count = int((df["age_days"].dropna() > threshold).sum())

        total_rows = len(df)
        is_fresh = stale_count == 0

        report = {
            "latest_published": str(latest_pub),
            "oldest_published": str(oldest_pub),
            "stale_rows": stale_count,
            "total_rows": total_rows,
            "is_fresh": bool(is_fresh),
        }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report

