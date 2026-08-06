from __future__ import annotations

import pandas as pd


import random
import json
from pathlib import Path
from datetime import datetime, UTC
import logging

logger = logging.getLogger("corruption")


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate controlled data corruption on the clean dataset.

    Scenarios:
    1. Blank Summary: Set summary = "" (and summary_chars = 0).
    2. Stale Date: Set published = "2000-01-01" and recalculate age_days.
    3. Duplicate Records: Duplicate selected records (keep same paper_id).
    4. Add Noise: Insert nonsense text into summary and text_for_embedding.
    """
    # 1. Seed random
    random.seed(42)

    # 2. Select 10-30% of papers to corrupt
    n_papers = len(df)
    k = max(1, int(n_papers * 0.2))  # ~20%

    # Select random indices
    corrupted_indices = random.sample(range(n_papers), k)

    # 3. Check overlap with test set
    output_log_path = Path(output_log_path)
    test_set_path = output_log_path.parent.parent / "eval" / "test_set.json"
    if not test_set_path.exists():
        test_set_path = Path("data/eval/test_set.json")

    gt_ids = set()
    if test_set_path.exists():
        try:
            with open(test_set_path, "r", encoding="utf-8") as f:
                test_set = json.load(f)
                for q in test_set:
                    gt_ids.update(q.get("ground_truth_doc_ids", []))
        except Exception as e:
            logger.warning(f"Could not load test set for overlap check: {e}")

    # Check if we have overlap
    corrupted_paper_ids = [df.iloc[idx]["paper_id"] for idx in corrupted_indices]
    overlap = set(corrupted_paper_ids) & gt_ids
    if not overlap:
        raise Exception(
            f"No overlap between corrupted papers {corrupted_paper_ids} and evaluation set ground truth {gt_ids}."
        )

    # 4. Apply corruptions
    corruption_types = ["duplicate", "stale_date", "blank_summary", "add_noise"]
    corruption_log = []
    new_rows = []

    df_corrupted = df.copy()
    applied_corruptions = set()

    for i, idx in enumerate(corrupted_indices):
        paper_id = df_corrupted.iloc[idx]["paper_id"]
        corr_type = corruption_types[i % len(corruption_types)]
        applied_corruptions.add(corr_type)

        corruption_log.append({"paper_id": paper_id, "corruption": corr_type})

        if corr_type == "blank_summary":
            df_corrupted.at[idx, "summary"] = ""
            df_corrupted.at[idx, "summary_chars"] = 0

        elif corr_type == "stale_date":
            df_corrupted.at[idx, "published"] = "2000-01-01"
            # Calculate age_days relative to now
            run_date_naive = datetime.now(UTC).replace(tzinfo=None)
            pub_naive = datetime(2000, 1, 1)
            age_days = (run_date_naive - pub_naive).days
            df_corrupted.at[idx, "age_days"] = age_days

        elif corr_type == "duplicate":
            row_to_duplicate = df_corrupted.iloc[idx].copy()
            new_rows.append(row_to_duplicate)

        elif corr_type == "add_noise":
            noise = " %%%% lorem123 ### RANDOM ### xyzxyzxyz"
            df_corrupted.at[idx, "summary"] = df_corrupted.at[idx, "summary"] + noise
            df_corrupted.at[idx, "summary_chars"] = len(df_corrupted.at[idx, "summary"])

    # 5. Rebuild text_for_embedding for existing rows
    for idx in range(len(df_corrupted)):
        title = df_corrupted.iloc[idx]["title"]
        authors = df_corrupted.iloc[idx]["authors_joined"]
        summary = df_corrupted.iloc[idx]["summary"]
        df_corrupted.at[idx, "text_for_embedding"] = f"Title: {title} | Authors: {authors} | Summary: {summary}"

    # Append the duplicate rows
    if new_rows:
        df_duplicates = pd.DataFrame(new_rows)
        # Rebuild text_for_embedding for duplicated rows
        for idx in range(len(df_duplicates)):
            title = df_duplicates.iloc[idx]["title"]
            authors = df_duplicates.iloc[idx]["authors_joined"]
            summary = df_duplicates.iloc[idx]["summary"]
            df_duplicates.iloc[idx, df_duplicates.columns.get_loc("text_for_embedding")] = (
                f"Title: {title} | Authors: {authors} | Summary: {summary}"
            )
        df_corrupted = pd.concat([df_corrupted, df_duplicates], ignore_index=True)

    # Save corruption log
    output_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_log_path, "w", encoding="utf-8") as f:
        json.dump(corruption_log, f, ensure_ascii=False, indent=2)

    # Logs
    print("Loaded clean dataset")
    print(f"Selected {n_papers} papers")
    if "blank_summary" in applied_corruptions:
        print("Applied blank summary")
    if "duplicate" in applied_corruptions:
        print("Applied duplicate")
    if "stale_date" in applied_corruptions:
        print("Applied stale date")
    if "add_noise" in applied_corruptions:
        print("Applied add noise")
    print("Saved corrupted dataset")
    print("Saved corruption log")

    logger.info("Loaded clean dataset")
    logger.info(f"Selected {n_papers} papers")
    if "blank_summary" in applied_corruptions:
        logger.info("Applied blank summary")
    if "duplicate" in applied_corruptions:
        logger.info("Applied duplicate")
    if "stale_date" in applied_corruptions:
        logger.info("Applied stale date")
    if "add_noise" in applied_corruptions:
        logger.info("Applied add noise")
    logger.info("Saved corrupted dataset")
    logger.info("Saved corruption log")

    return df_corrupted
