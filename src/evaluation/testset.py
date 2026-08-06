from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
import pandas as pd

from core.config import load_settings

logger = logging.getLogger(__name__)


def validate_test_set(test_set: list[dict[str, Any]], valid_paper_ids: set[str]) -> None:
    """Validate the generated test set according to strict rules.

    Raises Exception if any validation rule is violated.
    """
    seen_ids = set()
    seen_questions = set()

    for idx, item in enumerate(test_set):
        # 1. Check ID
        q_id = item.get("id")
        if not q_id:
            raise ValueError(f"Question at index {idx} has no ID.")
        if q_id in seen_ids:
            raise ValueError(f"Duplicate ID found: {q_id}")
        seen_ids.add(q_id)

        # 2. Check Question Type
        q_type = item.get("question_type")
        if q_type != "factual":
            raise ValueError(f"Invalid question_type: {q_type}. Must be 'factual'.")

        # 3. Check Question
        question = item.get("question")
        if not question or not question.strip():
            raise ValueError(f"Question with ID {q_id} has empty question field.")
        if question in seen_questions:
            raise ValueError(f"Duplicate question found: '{question}'")
        seen_questions.add(question)

        # 4. Check Ground Truth
        ground_truth = item.get("ground_truth")
        if not ground_truth or not ground_truth.strip():
            raise ValueError(f"Question with ID {q_id} has empty ground_truth.")

        # 5. Check Ground Truth Doc IDs
        doc_ids = item.get("ground_truth_doc_ids")
        if not isinstance(doc_ids, list) or not doc_ids:
            raise ValueError(f"Question with ID {q_id} must have non-empty ground_truth_doc_ids list.")
        
        for doc_id in doc_ids:
            if doc_id not in valid_paper_ids:
                raise ValueError(f"Question with ID {q_id} references non-existent paper_id: {doc_id}")

    logger.info("Validated dataset successfully.")


def build_test_set(df: pd.DataFrame, output_path: Path) -> list[dict[str, Any]]:
    """Create evaluation set from cleaned dataframe.

    Saves the JSON file to output_path and returns the test set list.
    """
    if len(df) < 5:
        raise ValueError(f"Insufficient papers in dataset (found {len(df)}, need at least 5) to build a test set.")

    test_set: list[dict[str, Any]] = []
    valid_paper_ids = set(df["paper_id"].astype(str))

    question_count = 0
    paper_index = 0
    max_attempts = len(df) * 10
    attempts = 0

    while question_count < 10 and attempts < max_attempts:
        attempts += 1
        row = df.iloc[paper_index]
        paper_id = str(row["paper_id"])
        title = str(row["title"]).strip()
        
        # We start with the preferred type, but if it fails, try other types
        preferred_type = question_count % 5
        
        for offset in range(5):
            q_type = (preferred_type + offset) % 5
            
            # Type 1: Authors
            if q_type == 0:
                authors_str = str(row.get("authors_joined", "")).strip()
                if authors_str and authors_str != "nan" and authors_str != "":
                    question = f"Ai là tác giả của bài báo \"{title}\"?"
                    if not any(item["question"] == question for item in test_set):
                        test_set.append({
                            "id": f"q{question_count + 1}",
                            "question_type": "factual",
                            "question": question,
                            "ground_truth": authors_str,
                            "ground_truth_doc_ids": [paper_id]
                        })
                        logger.info(f"Generated question q{question_count + 1} (Authors) for paper {paper_id}")
                        question_count += 1
                        break
            
            # Type 2: Journal
            elif q_type == 1:
                journal_str = str(row.get("comment", "")).strip()
                if journal_str and journal_str != "nan" and journal_str != "":
                    question = f"Bài báo \"{title}\" được đăng trên tạp chí nào?"
                    if not any(item["question"] == question for item in test_set):
                        test_set.append({
                            "id": f"q{question_count + 1}",
                            "question_type": "factual",
                            "question": question,
                            "ground_truth": journal_str,
                            "ground_truth_doc_ids": [paper_id]
                        })
                        logger.info(f"Generated question q{question_count + 1} (Journal) for paper {paper_id}")
                        question_count += 1
                        break
            
            # Type 3: Date/Published
            elif q_type == 2:
                pub_str = str(row.get("published", "")).strip()
                if pub_str and pub_str != "nan" and pub_str != "NaT" and pub_str != "":
                    question = f"Bài báo \"{title}\" được xuất bản khi nào?"
                    if not any(item["question"] == question for item in test_set):
                        test_set.append({
                            "id": f"q{question_count + 1}",
                            "question_type": "factual",
                            "question": question,
                            "ground_truth": pub_str,
                            "ground_truth_doc_ids": [paper_id]
                        })
                        logger.info(f"Generated question q{question_count + 1} (Published) for paper {paper_id}")
                        question_count += 1
                        break
            
            # Type 4: Category
            elif q_type == 3:
                cat_str = str(row.get("categories_joined", "")).strip()
                if not cat_str or cat_str == "nan":
                    cat_str = str(row.get("primary_category", "")).strip()
                if cat_str and cat_str != "nan" and cat_str != "":
                    question = f"Bài báo \"{title}\" thuộc lĩnh vực nào?"
                    if not any(item["question"] == question for item in test_set):
                        test_set.append({
                            "id": f"q{question_count + 1}",
                            "question_type": "factual",
                            "question": question,
                            "ground_truth": cat_str,
                            "ground_truth_doc_ids": [paper_id]
                        })
                        logger.info(f"Generated question q{question_count + 1} (Category) for paper {paper_id}")
                        question_count += 1
                        break
            
            # Type 5: Abstract
            elif q_type == 4:
                summary_str = str(row.get("summary", "")).strip()
                if summary_str and summary_str != "nan" and summary_str != "":
                    first_sentence = summary_str.split(".")[0].strip()
                    if len(first_sentence) > 10:
                        question = f"Nghiên cứu \"{title}\" tập trung vào vấn đề gì?"
                        if not any(item["question"] == question for item in test_set):
                            test_set.append({
                                "id": f"q{question_count + 1}",
                                "question_type": "factual",
                                "question": question,
                                "ground_truth": first_sentence + ".",
                                "ground_truth_doc_ids": [paper_id]
                            })
                            logger.info(f"Generated question q{question_count + 1} (Abstract) for paper {paper_id}")
                            question_count += 1
                            break

        paper_index += 1
        if paper_index >= len(df):
            paper_index = 0

    # Validate
    validate_test_set(test_set, valid_paper_ids)

    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved test_set.json to {output_path}")
    return test_set


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    settings = load_settings()
    clean_json_path = settings.paths.clean_json
    output_path = settings.paths.eval_testset

    logger.info(f"Loading papers from {clean_json_path}")
    df_clean = pd.read_json(clean_json_path)

    test_set = build_test_set(df_clean, output_path)

    # Print summary statistics
    total_papers = len(df_clean)
    total_questions = len(test_set)
    
    used_papers = {doc_id for q in test_set for doc_id in q["ground_truth_doc_ids"]}
    coverage = (len(used_papers) / total_papers) * 100 if total_papers > 0 else 0.0

    print("\n" + "="*40)
    print("EVALUATION TEST SET GENERATION SUMMARY")
    print("="*40)
    print(f"Total Papers:            {total_papers}")
    print(f"Total Questions:         {total_questions}")
    print(f"Coverage (% papers used): {coverage:.2f}%")
    print(f"Output Path:             {output_path}")
    print("="*40 + "\n")
