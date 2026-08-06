from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
import pandas as pd

from core.config import load_settings, Settings
from core.utils import read_json, write_json
from ingestion.crossref import fetch_source_records, load_raw_records
from ingestion.cleaning import build_clean_dataframe
from evaluation.testset import build_test_set
from evaluation.metrics import calculate_token_f1, LLMJudge
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question
from observability.quality import run_data_quality_checks, build_freshness_report
from observability.reporting import generate_phase1_report

# Configure logger
logger = logging.getLogger("phase1")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def run(force: bool = False) -> None:
    logger.info("Starting Phase1")
    settings = load_settings()

    # Step 1: Crawl
    raw_response_path = Path(settings.paths.raw_api_response)
    raw_records_path = Path(settings.paths.raw_records_json)

    if force:
        # Delete old artifacts if force=True
        logger.info("Force run: deleting old artifacts...")
        if raw_response_path.exists():
            raw_response_path.unlink()
        if raw_records_path.exists():
            raw_records_path.unlink()
        if Path(settings.paths.clean_csv).exists():
            Path(settings.paths.clean_csv).unlink()
        if Path(settings.paths.clean_json).exists():
            Path(settings.paths.clean_json).unlink()
        if Path(settings.paths.embeddings_json).exists():
            Path(settings.paths.embeddings_json).unlink()
        if Path(settings.paths.eval_testset).exists():
            Path(settings.paths.eval_testset).unlink()
        if Path(settings.paths.baseline_answers).exists():
            Path(settings.paths.baseline_answers).unlink()
        if Path(settings.paths.baseline_metrics).exists():
            Path(settings.paths.baseline_metrics).unlink()

    # Check if raw files exist
    if not raw_response_path.exists() or not raw_records_path.exists():
        logger.info("Fetching raw records from Crossref...")
        records = fetch_source_records(settings)
    else:
        logger.info("Skip crawling")
        records = load_raw_records(raw_records_path)

    logger.info("Loading raw data")

    # Step 2: Cleaning
    clean_json_path = Path(settings.paths.clean_json)
    clean_csv_path = Path(settings.paths.clean_csv)

    if not clean_json_path.exists() or not clean_csv_path.exists():
        logger.info("Cleaning raw records...")
        run_date = datetime.now(UTC)
        df_clean = build_clean_dataframe(records, run_date)
        # Ensure parent directories exist
        clean_json_path.parent.mkdir(parents=True, exist_ok=True)
        # Save CSV
        df_clean.to_csv(clean_csv_path, index=False, encoding="utf-8")
        # Save JSON
        df_clean.to_json(clean_json_path, orient="records", force_ascii=False, indent=2)
    else:
        logger.info("Loading cleaned records from existing file...")
        df_clean = pd.read_json(clean_json_path)

    logger.info("Cleaning completed")

    # Step 3: Indexing
    embeddings_json_path = Path(settings.paths.embeddings_json)
    if not embeddings_json_path.exists():
        logger.info("Building ChromaDB index...")
        index = LocalEmbeddingIndex.build(df_clean, settings)
    else:
        logger.info("Loading existing ChromaDB index...")
        index = LocalEmbeddingIndex.load(settings)

    logger.info("Embedding completed")
    logger.info("Indexed into ChromaDB")

    # Step 4: Frozen Evaluation Set
    test_set_path = Path(settings.paths.eval_testset)
    if not test_set_path.exists():
        logger.info("Generating frozen test set...")
        test_set = build_test_set(df_clean, test_set_path)
    else:
        logger.info("Frozen test set already exists.")
        test_set = read_json(test_set_path)

    logger.info("Loaded frozen test set")

    # Step 5: QA Evaluation
    use_llm_judge = os.getenv("USE_LLM_JUDGE", "False").lower() in {"1", "true", "yes"}
    answers = []
    
    total_questions = len(test_set)
    hits = 0
    total_token_f1 = 0.0
    total_latency_ms = 0.0
    
    judge_correct_count = 0
    judge_partial_count = 0
    judge_incorrect_count = 0
    judge_total_count = 0

    for sample in test_set:
        q_id = sample.get("id", "unknown")
        question = sample.get("question", "")
        ground_truth = sample.get("ground_truth", "")
        gt_doc_ids = sample.get("ground_truth_doc_ids", [])
        
        logger.info(f"Evaluating {q_id}")
        
        try:
            start_time = time.perf_counter()
            result = answer_question(question, settings, index)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Prediction from RAG
            prediction = result.answer
            retrieved_ids = result.retrieved_doc_ids
            
            # Hit rate
            hit = len(set(gt_doc_ids) & set(retrieved_ids)) > 0
            if hit:
                hits += 1
                
            # Token F1
            f1 = calculate_token_f1(ground_truth, prediction)
            total_token_f1 += f1
            total_latency_ms += latency_ms
            
            answer_item = {
                "question_id": q_id,
                "question": question,
                "prediction": prediction,
                "ground_truth": ground_truth,
                "retrieved_doc_ids": retrieved_ids,
                "hit": hit,
                "token_f1": round(f1, 4),
                "latency_ms": latency_ms
            }
            
            if use_llm_judge:
                judge_verdict = LLMJudge.evaluate(settings, question, ground_truth, prediction)
                answer_item["judge"] = judge_verdict
                judge_total_count += 1
                if judge_verdict == "Correct":
                    judge_correct_count += 1
                elif judge_verdict == "Partially Correct":
                    judge_partial_count += 1
                else:
                    judge_incorrect_count += 1
                    
            answers.append(answer_item)
            
        except Exception as e:
            logger.error(f"Failed evaluating {q_id}: {e}")
            # Do not stop the pipeline, keep going

    # Save Answers
    answers_output_path = Path(settings.paths.baseline_answers)
    answers_output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(answers_output_path, answers)
    
    # Calculate metrics
    num_questions = len(answers)
    retrieval_hit_rate = hits / num_questions if num_questions > 0 else 0.0
    mean_token_f1 = total_token_f1 / num_questions if num_questions > 0 else 0.0
    mean_latency_ms = total_latency_ms / num_questions if num_questions > 0 else 0.0
    
    metrics = {
        "num_questions": num_questions,
        "retrieval_hit_rate": round(retrieval_hit_rate, 4),
        "mean_token_f1": round(mean_token_f1, 4),
        "mean_latency_ms": int(mean_latency_ms)
    }
    
    if use_llm_judge and judge_total_count > 0:
        metrics["correct_rate"] = round(judge_correct_count / judge_total_count, 4)
        metrics["partial_rate"] = round(judge_partial_count / judge_total_count, 4)
        metrics["incorrect_rate"] = round(judge_incorrect_count / judge_total_count, 4)

    metrics_output_path = Path(settings.paths.baseline_metrics)
    write_json(metrics_output_path, metrics)
    logger.info("Metrics saved")

    # Step 6: Data Quality and Freshness
    quality_results = run_data_quality_checks(df_clean, settings, "baseline")
    freshness_report = build_freshness_report(df_clean, settings, settings.paths.freshness_report)
    logger.info("Quality check completed")

    # Step 7: Markdown Report
    source_summary = {
        "total_papers": len(df_clean),
        "avg_abstract_length": df_clean["summary_chars"].mean() if not df_clean.empty else 0.0,
        "avg_age_days": df_clean["age_days"].mean() if not df_clean.empty and "age_days" in df_clean.columns else 0.0,
        "num_categories": df_clean["primary_category"].nunique() if not df_clean.empty else 0
    }
    
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary,
        metrics,
        quality_results,
        freshness_report
    )
    logger.info("Markdown report saved")
    logger.info("Pipeline finished successfully")

def main() -> None:
    import sys
    force = "--force" in sys.argv or os.getenv("FORCE", "").lower() in {"1", "true", "yes"}
    run(force=force)
