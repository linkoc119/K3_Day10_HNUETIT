from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

MIN_DOCUMENTS = 4
DEFAULT_QUESTIONS_PER_PAPER = 2
SECONDARY_TYPES = ("authors", "date", "categories")

# Template phai chua dung keyword ma `retrieval/qa.py::_extract_answer` route theo,
# va dat title trong dau nhay don de `answer_question` lookup exact duoc.
QUESTION_TEMPLATES = {
    "summary": "What is the main contribution of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories are assigned to the paper '{title}'?",
}


def _route_of(question: str) -> str:
    """Mo phong dung logic route cua `qa.py::_extract_answer` de tu kiem tra template."""
    lowered = question.lower()
    if "who authored" in lowered or "list the authors" in lowered:
        return "authors"
    if "when was" in lowered or "publication date" in lowered or "published on" in lowered:
        return "date"
    if "what categories" in lowered:
        return "categories"
    return "summary"


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "authors":
        return str(row["authors_joined"]).strip()
    if question_type == "date":
        return str(row["published"]).strip()
    if question_type == "categories":
        return str(row["categories_joined"]).strip()
    return first_sentence(str(row["summary"]))


def _types_for_row(position: int, questions_per_paper: int) -> list[str]:
    """Moi paper luon co cau hoi summary, cac loai con lai xoay vong de can bang."""
    if questions_per_paper >= 4:
        return ["summary", *SECONDARY_TYPES]
    types = ["summary"]
    for offset in range(max(0, questions_per_paper - 1)):
        types.append(SECONDARY_TYPES[(position + offset) % len(SECONDARY_TYPES)])
    return types


def build_test_set(
    df: pd.DataFrame,
    output_path,
    questions_per_paper: int = DEFAULT_QUESTIONS_PER_PAPER,
) -> list[dict[str, Any]]:
    """Tao evaluation set template-based tu cleaned dataframe.

    Moi sample gom `id`, `question_type`, `question`, `ground_truth`,
    `ground_truth_doc_ids` - dung schema ma `evaluation/metrics.py` doc.
    """
    if df is None or len(df) < MIN_DOCUMENTS:
        raise ValueError(
            f"Can it nhat {MIN_DOCUMENTS} document de tao evaluation set, hien co {0 if df is None else len(df)}."
        )

    test_set: list[dict[str, Any]] = []
    skipped: list[str] = []

    for position, (_, row) in enumerate(df.iterrows()):
        paper_id = str(row["paper_id"]).strip()
        title = str(row["title"]).strip()
        if not paper_id or not title:
            continue

        for question_type in _types_for_row(position, questions_per_paper):
            question = QUESTION_TEMPLATES[question_type].format(title=title)
            ground_truth = _ground_truth(row, question_type)

            # Title co the chua keyword lam lech route cua qa.py -> sample se khong bao gio dung.
            if _route_of(question) != question_type:
                skipped.append(f"{paper_id}:{question_type} (route -> {_route_of(question)})")
                continue
            if not ground_truth:
                skipped.append(f"{paper_id}:{question_type} (ground truth rong)")
                continue

            test_set.append(
                {
                    "id": f"q{len(test_set) + 1:03d}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper_id],
                }
            )

    if not test_set:
        raise ValueError("Khong tao duoc sample nao. Kiem tra lai cleaned dataframe.")
    if skipped:
        print(f"[testset] bo qua {len(skipped)} sample: {', '.join(skipped[:5])}")

    write_json(Path(output_path), test_set)
    return test_set
