# Phase 1 Baseline Pipeline Report

## Dataset Summary

| Metric | Value |
| :--- | :--- |
| **Total Papers** | 24 |
| **Average Abstract Length (chars)** | 1728.0 |
| **Average Age (days)** | 77.8 |
| **Number of Categories** | 1 |

## Retrieval Performance

* **Hit Rate:** 90.0%
* **Mean Retrieved Docs:** 4.0

## QA Performance

* **Mean Token F1:** 0.91
* **Mean Latency:** 43.0 ms

## LLM Judge

* **Correct Rate:** 100.0%
* **Mean Judge Score:** 5.00 / 5.0

## Data Quality checks

| Check | Status | Details |
| :--- | :--- | :--- |
| **Completeness** | **PASS** | All records contain non-empty title, summary, and paper_id fields. |
| **Uniqueness** | **PASS** | doi column not present, paper_id represents DOI.; All paper_ids (and DOIs if present) are unique. |
| **Freshness** | **PASS** | All published dates are valid, age_days values are >= 0, and no stale records found. |

## Kết luận

Baseline retrieval đạt 90.0%.
Token F1 đạt 0.91.
Data quality PASS.

Đây sẽ là mốc benchmark để so sánh với các cải tiến Retrieval ở các checkpoint tiếp theo.
