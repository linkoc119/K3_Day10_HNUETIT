from __future__ import annotations

from datetime import date, datetime
import html
import re

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

MIN_TITLE_CHARS = 10
MIN_SUMMARY_CHARS = 120
MAX_AGE_DAYS = 3650

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "title_chars",
    "author_count",
    "age_days",
    "text_for_embedding",
]

_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_BEFORE_PUNCT_PATTERN = re.compile(r"\s+([,;:.!?])")
_EDGE_PUNCT_PATTERN = re.compile(r"^[\s\-–—:;,.]+|[\s\-–—:;,]+$")
# `<jats:title>` cua Crossref bien thanh nhan section dinh o dau abstract.
_SECTION_LABEL_PATTERN = re.compile(
    r"^(abstract|summary|background|introduction|objectives?|purpose|aims?|context|highlights)"
    r"\b[\s:.\-–—]*",
    re.IGNORECASE,
)


def _clean_text(value: object) -> str:
    """Chuan hoa chung: bo markup con sot, unescape entity, gom whitespace."""
    if value is None:
        return ""
    text = _TAG_PATTERN.sub(" ", str(value))
    text = normalize_whitespace(html.unescape(text))
    return _SPACE_BEFORE_PUNCT_PATTERN.sub(r"\1", text)


def _clean_title(value: str) -> str:
    return _EDGE_PUNCT_PATTERN.sub("", _clean_text(value))


def _clean_summary(value: str) -> str:
    """Bo nhan section o dau abstract vi `first_sentence(summary)` la ground truth."""
    text = _clean_text(value)
    for _ in range(3):
        stripped = _SECTION_LABEL_PATTERN.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return text.strip()


def _clean_name_list(values: list[str]) -> list[str]:
    """Chuan hoa list ten (authors/categories): lam sach, bo rong, khu trung lap khong phan biet hoa thuong."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _EDGE_PUNCT_PATTERN.sub("", _clean_text(value))
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def _parse_published(value: str) -> date | None:
    text = normalize_whitespace(str(value or ""))[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _as_date(run_date: datetime | date) -> date:
    return run_date.date() if isinstance(run_date, datetime) else run_date


def _build_text_for_embedding(row: dict) -> str:
    """Title/authors/categories dat truoc summary vi MiniLM cat o ~256 token."""
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Categories: {row['categories_joined']}",
            f"Published: {row['published']}",
            f"Summary: {row['summary']}",
        ]
    )


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed.

    Loai bo record khong hop le, chuan hoa tung truong, tinh freshness (`age_days`)
    va dung `text_for_embedding`. Schema output khop voi cai ma
    `retrieval/index.py` va `retrieval/qa.py` doc.
    """
    run_day = _as_date(run_date)

    rows: list[dict] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()

    for record in records or []:
        paper_id = _clean_text(record.paper_id).lower()
        title = _clean_title(record.title)
        summary = _clean_summary(record.summary)
        authors = _clean_name_list(record.authors)
        categories = _clean_name_list(record.categories)
        published = _parse_published(record.published)

        if not paper_id or len(title) < MIN_TITLE_CHARS or len(summary) < MIN_SUMMARY_CHARS:
            continue
        if not authors or not categories:
            continue
        if published is None or published > run_day:
            continue

        age_days = (run_day - published).days
        if age_days > MAX_AGE_DAYS:
            continue

        title_key = title.lower()
        if paper_id in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(paper_id)
        seen_titles.add(title_key)

        updated = _parse_published(record.updated)
        primary_category = _clean_text(record.primary_category) or categories[0]

        row = {
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "categories": categories,
            "primary_category": primary_category,
            "published": published.isoformat(),
            "updated": (updated or published).isoformat(),
            "abs_url": _clean_text(record.abs_url) or f"https://doi.org/{paper_id}",
            "pdf_url": _clean_text(record.pdf_url),
            "comment": _clean_text(record.comment),
            "authors_joined": compact_join(authors),
            "categories_joined": compact_join(categories),
            "summary_chars": len(summary),
            "title_chars": len(title),
            "author_count": len(authors),
            "age_days": age_days,
        }
        row["text_for_embedding"] = _build_text_for_embedding(row)
        rows.append(row)

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    if df.empty:
        raise ValueError(
            "Cleaning loai bo toan bo record. Kiem tra lai data/raw/crossref_records.json."
        )

    df = df.sort_values(["published", "paper_id"], ascending=[False, True])
    return df.reset_index(drop=True)
