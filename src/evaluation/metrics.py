from __future__ import annotations

import logging
from dataclasses import dataclass
from statistics import mean
import os
import sys
import types
from typing import Any

from datasets import Dataset
from pydantic import BaseModel, Field

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json
from retrieval.embeddings import MiniLMEmbeddings
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import answer_question

logger = logging.getLogger(__name__)


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    correct: bool
    reasoning: str


@dataclass(frozen=True)
class EvaluationBundle:
    summary: dict[str, Any]
    answers: list[dict[str, Any]]


def _token_f1(reference: str, prediction: str) -> float:
    ref_tokens = normalize_whitespace(reference).lower().split()
    pred_tokens = normalize_whitespace(prediction).lower().split()
    if not ref_tokens or not pred_tokens:
        return 0.0
    ref_set = set(ref_tokens)
    pred_set = set(pred_tokens)
    overlap = len(ref_set & pred_set)
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_set)
    recall = overlap / len(ref_set)
    return 2 * precision * recall / (precision + recall)


def _judge_answer(settings: Settings, question: str, reference: str, prediction: str) -> JudgeVerdict:
    prompt = f"""
Evaluate the model answer against the reference answer.

Question: {question}
Reference answer: {reference}
Model answer: {prediction}

Return:
- score from 1 to 5
- correct = true only when the answer is materially correct
- short reasoning
""".strip()
    try:
        llm = build_llm(settings=settings, temperature=0.0).with_structured_output(JudgeVerdict)
        return llm.invoke(prompt)
    except Exception:
        score = 5 if _token_f1(reference, prediction) >= 0.95 else 3 if _token_f1(reference, prediction) >= 0.5 else 1
        return JudgeVerdict(
            score=score,
            correct=score >= 3,
            reasoning="Fallback heuristic judge used because the LLM evaluator was unavailable.",
        )


def _run_ragas(settings: Settings, answers: list[dict[str, Any]]) -> dict[str, Any]:
    if os.getenv("RUN_RAGAS", "").lower() not in {"1", "true", "yes"}:
        return {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}
    try:
        if "langchain_community.chat_models.vertexai" not in sys.modules:
            shim = types.ModuleType("langchain_community.chat_models.vertexai")
            shim.ChatVertexAI = type("ChatVertexAI", (), {})
            sys.modules["langchain_community.chat_models.vertexai"] = shim
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

        dataset = Dataset.from_dict(
            {
                "question": [item["question"] for item in answers],
                "answer": [item["answer"] for item in answers],
                "ground_truth": [item["ground_truth"] for item in answers],
                "contexts": [item["retrieved_contexts"] for item in answers],
            }
        )
        result = evaluate(
            dataset,
            metrics=[answer_relevancy, context_precision, context_recall, faithfulness],
            llm=build_llm(settings=settings, temperature=0.0),
            embeddings=MiniLMEmbeddings(settings.embedding_model),
        )
        return dict(result)
    except Exception as exc:  # pragma: no cover
        return {"error": f"Ragas evaluation failed: {exc}"}


def evaluate_pipeline(
    settings: Settings,
    index: LocalEmbeddingIndex,
    test_set_path,
    metrics_output_path,
    answers_output_path,
) -> EvaluationBundle:
    test_set = read_json(test_set_path)
    answers: list[dict[str, Any]] = []

    for item in test_set:
        result = answer_question(item["question"], settings=settings, index=index)
        judge = _judge_answer(settings, item["question"], item["ground_truth"], result.answer)
        retrieval_hit = any(doc_id in item["ground_truth_doc_ids"] for doc_id in result.retrieved_doc_ids)
        answers.append(
            {
                "id": item["id"],
                "question_type": item["question_type"],
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "ground_truth_doc_ids": item["ground_truth_doc_ids"],
                "answer": result.answer,
                "retrieved_doc_ids": result.retrieved_doc_ids,
                "retrieved_contexts": result.retrieved_contexts,
                "retrieval_hit": retrieval_hit,
                "token_f1": _token_f1(item["ground_truth"], result.answer),
                "judge": judge.model_dump(),
            }
        )

    summary = {
        "samples": len(answers),
        "retrieval_hit_rate": mean(1.0 if item["retrieval_hit"] else 0.0 for item in answers),
        "mean_token_f1": mean(item["token_f1"] for item in answers),
        "judge_accuracy": mean(1.0 if item["judge"]["correct"] else 0.0 for item in answers),
        "mean_judge_score": mean(item["judge"]["score"] for item in answers),
    }
    summary["ragas"] = _run_ragas(settings, answers)

    bundle = EvaluationBundle(summary=summary, answers=answers)
    write_json(metrics_output_path, summary)
    write_json(answers_output_path, answers)
    return bundle


def calculate_token_f1(reference: str, prediction: str) -> float:
    import re
    ref = reference.lower()
    pred = prediction.lower()
    ref = re.sub(r'[^\w\s]', ' ', ref)
    pred = re.sub(r'[^\w\s]', ' ', pred)
    ref_tokens = ref.split()
    pred_tokens = pred.split()
    
    if not ref_tokens or not pred_tokens:
        return 0.0
        
    ref_set = set(ref_tokens)
    pred_set = set(pred_tokens)
    overlap = len(ref_set & pred_set)
    if overlap == 0:
        return 0.0
        
    precision = overlap / len(pred_set)
    recall = overlap / len(ref_set)
    return 2 * precision * recall / (precision + recall)


class LLMJudge:
    @staticmethod
    def evaluate(settings: Settings, question: str, reference: str, prediction: str) -> str:
        prompt = f"""
Evaluate the model prediction against the reference answer for the given question.

Question: {question}
Reference Answer: {reference}
Model Prediction: {prediction}

Return only one of the following words: "Correct", "Partially Correct", or "Incorrect". Do not include any other text or reasoning.
""".strip()
        try:
            llm = build_llm(settings=settings, temperature=0.0)
            response = llm.invoke(prompt)
            verdict = getattr(response, "content", str(response)).strip()
            for option in ["Correct", "Partially Correct", "Incorrect"]:
                if option.lower() in verdict.lower():
                    return option
            return "Incorrect"
        except Exception:
            f1 = calculate_token_f1(reference, prediction)
            if f1 >= 0.9:
                return "Correct"
            elif f1 >= 0.3:
                return "Partially Correct"
            else:
                return "Incorrect"

    @staticmethod
    def score_from_verdict(verdict: str) -> int:
        if verdict == "Correct":
            return 5
        if verdict == "Partially Correct":
            return 3
        return 1

    @staticmethod
    def is_correct(verdict: str) -> bool:
        return verdict == "Correct"


def run_qa_evaluation(
    settings: Settings,
    index: "LocalEmbeddingIndex",
    test_set: list[dict[str, Any]],
    indexed_paper_ids: set[str] | None = None,
    use_llm_judge: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the frozen evaluation set against an index.

    Always computes retrieval_hit_rate, mean_token_f1, mean_latency_ms,
    judge_accuracy, mean_judge_score. The judge is either an LLM call or a
    deterministic token-F1 heuristic fallback.

    Returns (answers, metrics).
    """
    from retrieval.qa import answer_question
    import time as _time

    if indexed_paper_ids is None:
        indexed_paper_ids = {doc["paper_id"].lower() for doc in index.documents}

    answers: list[dict[str, Any]] = []
    hits = 0
    total_token_f1 = 0.0
    total_latency_ms = 0.0
    judge_correct_count = 0
    judge_partial_count = 0
    judge_incorrect_count = 0
    judge_total_count = 0
    judge_score_sum = 0
    judge_failed = 0

    for sample in test_set:
        q_id = sample.get("id", "unknown")
        question = sample.get("question", "")
        ground_truth = sample.get("ground_truth", "")
        gt_doc_ids = sample.get("ground_truth_doc_ids", [])

        gt_present = any(gt_id.lower() in indexed_paper_ids for gt_id in gt_doc_ids)
        if not gt_present:
            logger.warning("MISS: Ground truth doc IDs %s for question %s are not in the index.", gt_doc_ids, q_id)

        start_time = _time.perf_counter()
        try:
            result = answer_question(question, settings, index)
            latency_ms = int((_time.perf_counter() - start_time) * 1000)
            prediction = result.answer
            retrieved_ids = result.retrieved_doc_ids
        except Exception as exc:
            logger.error("Error evaluating %s: %s", q_id, exc)
            latency_ms = int((_time.perf_counter() - start_time) * 1000)
            prediction = ""
            retrieved_ids = []
            judge_failed += 1

        hit = False
        if gt_present:
            hit = len(set(gt_doc_ids) & set(retrieved_ids)) > 0
        if hit:
            hits += 1

        f1 = calculate_token_f1(ground_truth, prediction)
        total_token_f1 += f1
        total_latency_ms += latency_ms

        if use_llm_judge:
            judge_verdict = LLMJudge.evaluate(settings, question, ground_truth, prediction)
        else:
            if f1 >= 0.9:
                judge_verdict = "Correct"
            elif f1 >= 0.3:
                judge_verdict = "Partially Correct"
            else:
                judge_verdict = "Incorrect"
        judge_numeric_score = LLMJudge.score_from_verdict(judge_verdict)

        if prediction:
            judge_total_count += 1
            judge_score_sum += judge_numeric_score
            if judge_verdict == "Correct":
                judge_correct_count += 1
            elif judge_verdict == "Partially Correct":
                judge_partial_count += 1
            else:
                judge_incorrect_count += 1

        answer_item = {
            "question_id": q_id,
            "question": question,
            "prediction": prediction,
            "ground_truth": ground_truth,
            "retrieved_doc_ids": retrieved_ids,
            "hit": hit,
            "token_f1": round(f1, 4),
            "latency_ms": latency_ms,
            "judge": judge_verdict,
            "judge_score": judge_numeric_score,
        }
        if not gt_present:
            answer_item["index_status"] = "MISS"
        answers.append(answer_item)

    num_questions = len(answers)
    retrieval_hit_rate = hits / num_questions if num_questions > 0 else 0.0
    mean_token_f1 = total_token_f1 / num_questions if num_questions > 0 else 0.0
    mean_latency_ms = total_latency_ms / num_questions if num_questions > 0 else 0.0
    judge_accuracy = (
        judge_correct_count / judge_total_count if judge_total_count > 0 else 0.0
    )
    mean_judge_score = (
        judge_score_sum / judge_total_count if judge_total_count > 0 else 0.0
    )

    metrics = {
        "num_questions": num_questions,
        "retrieval_hit_rate": round(retrieval_hit_rate, 4),
        "mean_token_f1": round(mean_token_f1, 4),
        "mean_latency_ms": int(mean_latency_ms),
        "judge_accuracy": round(judge_accuracy, 4),
        "mean_judge_score": round(mean_judge_score, 4),
        "judge_total": judge_total_count,
        "judge_correct": judge_correct_count,
        "judge_partial": judge_partial_count,
        "judge_incorrect": judge_incorrect_count,
        "judge_failed": judge_failed,
        "judge_backend": "llm" if use_llm_judge else "heuristic",
        "correct_rate": round(judge_correct_count / judge_total_count, 4) if judge_total_count > 0 else 0.0,
        "partial_rate": round(judge_partial_count / judge_total_count, 4) if judge_total_count > 0 else 0.0,
        "incorrect_rate": round(judge_incorrect_count / judge_total_count, 4) if judge_total_count > 0 else 0.0,
    }
    return answers, metrics

