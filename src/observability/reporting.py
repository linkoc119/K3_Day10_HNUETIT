from __future__ import annotations

from typing import Any


import json
from pathlib import Path
from typing import Any


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Generate Markdown report for baseline phase (Phase 1)."""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract information with defaults
    total_papers = source_summary.get("total_papers", 0)
    avg_abstract_len = source_summary.get("avg_abstract_length", 0.0)
    avg_age = source_summary.get("avg_age_days", 0.0)
    num_categories = source_summary.get("num_categories", 0)

    hit_rate = metrics.get("retrieval_hit_rate", 0.0)
    mean_retrieved_docs = metrics.get("mean_retrieved_docs", 4.0)  # default top_k is 4
    
    mean_f1 = metrics.get("mean_token_f1", 0.0)
    mean_latency = metrics.get("mean_latency_ms", 0.0)

    # LLM Judge metrics
    has_judge = "correct_rate" in metrics or "judge_accuracy" in metrics
    correct_rate = metrics.get("correct_rate") or metrics.get("judge_accuracy", 0.0)
    mean_judge_score = metrics.get("mean_judge_score")

    # Quality statuses
    q_completeness = quality.get("completeness", {}).get("status", "N/A")
    q_uniqueness = quality.get("uniqueness", {}).get("status", "N/A")
    q_freshness = quality.get("freshness", {}).get("status", "N/A")

    # Overall Quality
    overall_quality = "PASS" if (q_completeness == "PASS" and q_uniqueness == "PASS" and q_freshness == "PASS") else "FAIL"

    # Conclusion
    conclusion = f"""Baseline retrieval đạt {hit_rate * 100:.1f}%.
Token F1 đạt {mean_f1:.2f}.
Data quality {overall_quality}.

Đây sẽ là mốc benchmark để so sánh với các cải tiến Retrieval ở các checkpoint tiếp theo."""

    md_content = f"""# Phase 1 Baseline Pipeline Report

## Dataset Summary

| Metric | Value |
| :--- | :--- |
| **Total Papers** | {total_papers} |
| **Average Abstract Length (chars)** | {avg_abstract_len:.1f} |
| **Average Age (days)** | {avg_age:.1f} |
| **Number of Categories** | {num_categories} |

## Retrieval Performance

* **Hit Rate:** {hit_rate * 100:.1f}%
* **Mean Retrieved Docs:** {mean_retrieved_docs:.1f}

## QA Performance

* **Mean Token F1:** {mean_f1:.2f}
* **Mean Latency:** {mean_latency:.1f} ms

"""

    if has_judge:
        md_content += f"""## LLM Judge

* **Correct Rate:** {correct_rate * 100:.1f}%
"""
        if mean_judge_score is not None:
            md_content += f"* **Mean Judge Score:** {mean_judge_score:.2f} / 5.0\n"
        md_content += "\n"

    md_content += f"""## Data Quality checks

| Check | Status | Details |
| :--- | :--- | :--- |
| **Completeness** | **{q_completeness}** | {quality.get("completeness", {}).get("reason", "")} |
| **Uniqueness** | **{q_uniqueness}** | {quality.get("uniqueness", {}).get("reason", "")} |
| **Freshness** | **{q_freshness}** | {quality.get("freshness", {}).get("reason", "")} |

## Kết luận

{conclusion}
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Generate comparative Markdown report comparing baseline, corrupted, and repaired pipelines."""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Compare key metrics
    def get_val(d, key, default=0.0):
        return d.get(key, default) if d else default

    md_content = f"""# Data Quality Corruption & Repair Report

Comparing system performance under data corruption and after data lineage/quality repair.

## Performance Metrics Comparison

| Metric | Baseline (Clean) | Corrupted | Repaired |
| :--- | :---: | :---: | :---: |
| **Retrieval Hit Rate** | {get_val(baseline_metrics, "retrieval_hit_rate")*100:.1f}% | {get_val(corrupted_metrics, "retrieval_hit_rate")*100:.1f}% | {get_val(repaired_metrics, "retrieval_hit_rate")*100:.1f}% |
| **Mean Token F1** | {get_val(baseline_metrics, "mean_token_f1"):.3f} | {get_val(corrupted_metrics, "mean_token_f1"):.3f} | {get_val(repaired_metrics, "mean_token_f1"):.3f} |
| **Mean Latency (ms)** | {get_val(baseline_metrics, "mean_latency_ms"):.1f} | {get_val(corrupted_metrics, "mean_latency_ms"):.1f} | {get_val(repaired_metrics, "mean_latency_ms"):.1f} |

## Data Quality Status Comparison

| Check | Corrupted Status | Repaired Status |
| :--- | :---: | :---: |
| **Completeness** | **{corrupted_quality.get("completeness", {}).get("status", "N/A")}** | **{repaired_quality.get("completeness", {}).get("status", "N/A")}** |
| **Uniqueness** | **{corrupted_quality.get("uniqueness", {}).get("status", "N/A")}** | **{repaired_quality.get("uniqueness", {}).get("status", "N/A")}** |
| **Freshness** | **{corrupted_quality.get("freshness", {}).get("status", "N/A")}** | **{repaired_quality.get("freshness", {}).get("status", "N/A")}** |

## Key Findings

1. **Impact of Corruption:**
   - Check if retrieval hit rate or QA F1 dropped.
   - Describe how the data corruption (missing fields, duplicate IDs, or temporal drift) was detected by the data quality layer.

2. **Lineage-based Repair Success:**
   - Explain how the repair process restored the metrics and quality checks to baseline levels.
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

