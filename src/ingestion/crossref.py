from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
import html
import os
import re
import time

import requests

from core.config import Settings
from core.utils import compact_join, normalize_whitespace, read_json, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 5
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 16.0

_TAG_PATTERN = re.compile(r"<[^>]+>")
_ABSTRACT_LABEL_PATTERN = re.compile(r"^abstract[:.\s-]*", re.IGNORECASE)
_SPACE_BEFORE_PUNCT_PATTERN = re.compile(r"\s+([,;:.!?])")
_PUBLISHED_KEYS = ("published", "issued", "published-online", "published-print", "created")
_UPDATED_KEYS = ("deposited", "indexed", "created")


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _user_agent() -> str:
    """Crossref khuyen khich gui User-Agent co mailto de vao polite pool."""
    base = "K3-Day10-DataObservability/0.1"
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    return f"{base} (mailto:{mailto})" if mailto else base


def _text(value: Any) -> str:
    """Title/abstract cua Crossref co the chua JATS markup va HTML entity."""
    if not value:
        return ""
    text = _TAG_PATTERN.sub(" ", str(value))
    text = normalize_whitespace(html.unescape(text))
    return _SPACE_BEFORE_PUNCT_PATTERN.sub(r"\1", text)


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return ""
    return _text(value)


def _clean_abstract(raw: str) -> str:
    """Abstract cua Crossref la JATS XML, bo tag/entity va bo nhan 'Abstract' o dau."""
    return _ABSTRACT_LABEL_PATTERN.sub("", _text(raw)).strip()


def _date_from_parts(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    parts = node.get("date-parts") or []
    if not parts or not isinstance(parts[0], list):
        return ""
    values = [int(part) for part in parts[0] if isinstance(part, int)]
    if not values:
        return ""
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        try:
            return date(year, 1, 1).isoformat()
        except ValueError:
            return ""


def _pick_date(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return ""


def _extract_authors(item: dict) -> list[str]:
    authors: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = _text(author.get("name")) or compact_join(
            [_text(author.get("given")), _text(author.get("family"))], " "
        )
        if name and name not in authors:
            authors.append(name)
    return authors


def _extract_categories(item: dict) -> list[str]:
    categories: list[str] = []
    for subject in item.get("subject") or []:
        text = _text(subject)
        if text and text not in categories:
            categories.append(text)
    if categories:
        return categories

    container = _first_text(item.get("container-title"))
    if container:
        return [container]

    item_type = _text(item.get("type"))
    return [item_type] if item_type else []


def _extract_pdf_url(item: dict) -> str:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        if link.get("content-type") == "application/pdf" and link.get("URL"):
            return str(link["URL"])
    return ""


def _build_comment(item: dict) -> str:
    return compact_join(
        [
            _text(item.get("type")),
            _first_text(item.get("container-title")),
            _text(item.get("publisher")),
        ]
    )


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord da chuan hoa va bo trung lap."""
    items = ((payload or {}).get("message") or {}).get("items") or []
    today = datetime.now(UTC).date().isoformat()

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = _text(item.get("DOI")).lower()
        title = _first_text(item.get("title"))
        summary = _clean_abstract(str(item.get("abstract", "")))
        published = _pick_date(item, _PUBLISHED_KEYS)
        if not paper_id or not title or not summary or not published:
            continue
        # Crossref co ban ghi "forthcoming" voi ngay tuong lai -> age_days se am.
        if published > today:
            continue
        if paper_id in seen_ids:
            continue
        seen_ids.add(paper_id)

        categories = _extract_categories(item)
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_extract_authors(item),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=_pick_date(item, _UPDATED_KEYS) or published,
                abs_url=normalize_whitespace(str(item.get("URL", ""))) or f"https://doi.org/{paper_id}",
                pdf_url=_extract_pdf_url(item),
                comment=_build_comment(item),
            )
        )
    return records


def _retry_after_seconds(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _request_with_retry(params: dict[str, Any]) -> dict:
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    last_error = "unknown error"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        delay = min(2.0 ** (attempt - 1), MAX_BACKOFF_SECONDS)
        try:
            response = requests.get(
                CROSSREF_API_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            last_error = f"request error: {exc}"
        else:
            if response.status_code == 200:
                return response.json()
            if response.status_code not in RETRY_STATUS_CODES:
                raise RuntimeError(
                    f"Crossref request failed with HTTP {response.status_code}: {response.text[:300]}"
                )
            last_error = f"HTTP {response.status_code}"
            delay = _retry_after_seconds(response) or delay

        if attempt < MAX_ATTEMPTS:
            print(f"[crossref] {last_error} - retry {attempt}/{MAX_ATTEMPTS - 1} sau {delay:.1f}s")
            time.sleep(delay)

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts ({last_error}).")


def _bounded_filter(source_filter: str) -> str:
    """Chan tren ngay xuat ban: `sort=issued desc` neu khong se keo ve ban ghi forthcoming."""
    if "until-pub-date" in source_filter:
        return source_filter
    today = datetime.now(UTC).date().isoformat()
    return compact_join([source_filter, f"until-pub-date:{today}"], ",")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref API, luu raw response va raw records vao data/raw/."""
    params: dict[str, Any] = {
        "query": settings.source_query,
        "filter": _bounded_filter(settings.source_filter),
        "rows": settings.max_results,
        # Sort theo relevance thay vi issued: sort theo ngay se tra ve paper moi nhat
        # nhung lac de, lam corpus khong con lien quan den source_query.
        "sort": "relevance",
        "order": "desc",
    }

    payload = _request_with_retry(params)
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError(
            "Crossref tra ve 0 record hop le. Kiem tra lai source_query/source_filter trong core/config.py."
        )

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc snapshot JSON trong data/raw/ va map nguoc lai thanh PaperRecord."""
    payload = read_json(path)
    rows = payload.get("records", []) if isinstance(payload, dict) else payload

    records: list[PaperRecord] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        paper_id = normalize_whitespace(str(row.get("paper_id", "")))
        title = normalize_whitespace(str(row.get("title", "")))
        if not paper_id or not title:
            continue
        categories = [str(category) for category in row.get("categories") or []]
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=str(row.get("summary", "")),
                authors=[str(author) for author in row.get("authors") or []],
                categories=categories,
                primary_category=str(row.get("primary_category", "")) or (categories[0] if categories else ""),
                published=str(row.get("published", "")),
                updated=str(row.get("updated", "")) or str(row.get("published", "")),
                abs_url=str(row.get("abs_url", "")),
                pdf_url=str(row.get("pdf_url", "")),
                comment=str(row.get("comment", "")),
            )
        )
    return records
