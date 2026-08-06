from __future__ import annotations

from datetime import datetime, UTC
import json
import logging
from pathlib import Path
import re
import pandas as pd

from ingestion.crossref import PaperRecord

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Remove HTML/XML tags, normalize whitespaces and newlines."""
    if not text:
        return ""
    # Remove HTML/XML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Replace newlines/tabs with space
    text = re.sub(r"\s+", " ", text)
    # Strip whitespace
    return text.strip()


def parse_date(date_str: str) -> pd.Timestamp:
    """Parse date string into a timestamp, handling YYYY-MM and YYYY fallbacks."""
    if not date_str or date_str == "NaT":
        return pd.NaT
    
    date_str = date_str.strip()
    
    # Try YYYY-MM-DD
    match_ymd = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    if match_ymd:
        try:
            return pd.to_datetime(date_str)
        except Exception:
            return pd.NaT

    # Try YYYY-MM
    match_ym = re.match(r"^(\d{4})-(\d{2})$", date_str)
    if match_ym:
        try:
            return pd.to_datetime(f"{date_str}-01")
        except Exception:
            return pd.NaT

    # Try YYYY
    match_y = re.match(r"^(\d{4})$", date_str)
    if match_y:
        try:
            return pd.to_datetime(f"{date_str}-01-01")
        except Exception:
            return pd.NaT

    return pd.NaT


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into a dataframe ready for embedding.

    Pseudo-code:
    1. Normalize title, summary, authors, categories.
    2. Parse published/updated date.
    3. Tinh age_days.
    4. Tao cot helper:
       - authors_joined
       - categories_joined
       - summary_chars
       - text_for_embedding
    5. Drop duplicates va filter row xau.
    6. Sort dataframe va return.
    """
    logger.info(f"Loaded records count: {len(records)}")

    cleaned_data = []
    dropped_invalid = 0
    cleaned_xml_count = 0

    for r in records:
        # Step 2: Drop record if title is empty or abstract/summary < 100 characters
        if not r.title or not r.summary or len(r.summary) < 100:
            dropped_invalid += 1
            continue

        # Step 3: Normalize text
        title_clean = clean_text(r.title)
        summary_clean = clean_text(r.summary)
        
        if title_clean != r.title or summary_clean != r.summary:
            cleaned_xml_count += 1

        # Step 4: Authors
        authors_joined = ", ".join(r.authors) if r.authors else ""

        # Step 5: Categories
        categories_joined = ", ".join(r.categories) if r.categories else ""

        # Step 6: Published date parsing
        pub_ts = parse_date(r.published)
        
        # Step 7: Age days
        age_days = pd.NA
        if pd.notna(pub_ts):
            # Calculate today - published
            # Normalize run_date to date (timezone-naive or same zone)
            run_date_naive = run_date.replace(tzinfo=None)
            pub_naive = pub_ts.to_pydatetime().replace(tzinfo=None)
            age_days = (run_date_naive - pub_naive).days

        # Step 8: text_for_embedding format
        text_for_embedding = f"Title: {title_clean} | Authors: {authors_joined} | Summary: {summary_clean}"

        cleaned_data.append({
            "paper_id": r.paper_id,
            "title": title_clean,
            "summary": summary_clean,
            "authors": r.authors,
            "authors_joined": authors_joined,
            "categories": r.categories,
            "categories_joined": categories_joined,
            "primary_category": r.primary_category,
            "published": pub_ts,
            "updated": r.updated,
            "abs_url": r.abs_url,
            "pdf_url": r.pdf_url,
            "comment": r.comment,
            "age_days": age_days,
            "summary_chars": len(summary_clean),
            "text_for_embedding": text_for_embedding
        })

    logger.info(f"Dropped invalid rows: {dropped_invalid}")
    logger.info(f"Cleaned XML tags / normalized text in {cleaned_xml_count} records")
    logger.info("Generated authors_joined")
    logger.info("Generated categories_joined")

    df = pd.DataFrame(cleaned_data)
    if df.empty:
        return df

    # Calculate age_days and format published back to YYYY-MM-DD
    logger.info("Calculated age_days")

    # Drop duplicates by paper_id (keep first)
    initial_len = len(df)
    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    duplicate_count = initial_len - len(df)
    if duplicate_count > 0:
        logger.info(f"Dropped {duplicate_count} duplicate paper_id records")

    # Format 'published' as YYYY-MM-DD string or 'NaT'
    df["published"] = df["published"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "NaT")

    # Sort by published date descending
    df = df.sort_values(by="published", ascending=False).reset_index(drop=True)

    return df


if __name__ == "__main__":
    # Standard python logging configuration
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    from core.config import load_settings
    from ingestion.crossref import load_raw_records
    
    settings = load_settings()
    raw_path = settings.paths.raw_records_json
    if not raw_path.exists():
        logger.error(f"Raw records file {raw_path} does not exist. Please run crossref ingestion first.")
    else:
        records = load_raw_records(raw_path)
        run_date = datetime.now(UTC)
        df = build_clean_dataframe(records, run_date)
        
        # Save output files
        settings.paths.clean_csv.parent.mkdir(parents=True, exist_ok=True)
        
        # Save CSV
        df.to_csv(settings.paths.clean_csv, index=False, encoding="utf-8")
        logger.info(f"Saved CSV to {settings.paths.clean_csv}")
        
        # Save JSON
        df_json = df.copy()
        # JSON output should contain primitive types for authors/categories
        df_json.to_json(settings.paths.clean_json, orient="records", force_ascii=False, indent=2)
        logger.info(f"Saved JSON to {settings.paths.clean_json}")
