from __future__ import annotations

from dataclasses import dataclass
import re

from core.config import Settings
from core.utils import first_sentence
from retrieval.index import LocalEmbeddingIndex, SearchResult


@dataclass(frozen=True)
class AnswerResult:
    question: str
    answer: str
    retrieved_doc_ids: list[str]
    retrieved_contexts: list[str]
    retrieved_titles: list[str]


def _extract_answer(question: str, top_result: SearchResult) -> str:
    lowered = question.lower()
    metadata = top_result.metadata
    
    # 1. Authors
    if any(kw in lowered for kw in ["tác giả", "tác giả là ai", "who authored", "list the authors"]):
        return metadata.get("authors_joined", "")
        
    # 2. Publication Date
    if any(kw in lowered for kw in ["xuất bản khi nào", "xuất bản vào lúc nào", "when was", "publication date", "published on"]):
        return metadata.get("published", "")
        
    # 3. Categories / Field
    if any(kw in lowered for kw in ["thuộc lĩnh vực nào", "lĩnh vực nào", "what categories", "category", "subject"]):
        return metadata.get("categories_joined", "") or metadata.get("primary_category", "")
        
    # 4. Journal / Conference (comment)
    if any(kw in lowered for kw in ["tạp chí nào", "đăng trên tạp chí nào", "journal", "published in", "where was it published"]):
        return metadata.get("comment", "")
        
    # Default to first sentence of summary
    return first_sentence(metadata.get("summary", ""))


def answer_question(question: str, settings: Settings, index: LocalEmbeddingIndex, top_k: int | None = None) -> AnswerResult:
    title_match = re.search(r"'([^']+)'", question)
    exact = index.lookup(title_match.group(1)) if title_match else None
    retrieved = index.search(question, top_k=top_k)
    if exact:
        exact_result = SearchResult(
            paper_id=exact["paper_id"],
            title=exact["title"],
            score=1.0,
            content=exact["content"],
            metadata=exact["metadata"],
        )
        deduped = [exact_result] + [item for item in retrieved if item.paper_id != exact_result.paper_id]
        retrieved = deduped[: (top_k or settings.top_k)]
    if not retrieved:
        answer = "I don't know from the indexed corpus."
    else:
        answer = _extract_answer(question, retrieved[0])
    return AnswerResult(
        question=question,
        answer=answer,
        retrieved_doc_ids=[item.paper_id for item in retrieved],
        retrieved_contexts=[item.content for item in retrieved],
        retrieved_titles=[item.title for item in retrieved],
    )
