from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import requests

from core.config import Settings

logger = logging.getLogger(__name__)

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


class CrossrefCrawler:
    def __init__(
        self,
        query: str,
        rows: int = 100,
        mailto: str | None = None,
    ):
        self.query = query
        self.rows = rows
        self.mailto = mailto
        self.url = "https://api.crossref.org/works"

    def fetch(self, filter_str: str | None = None) -> dict:
        """Call GET https://api.crossref.org/works with retry + backoff."""
        headers = {
            "User-Agent": f"CrossrefCrawler/1.0 (mailto:{self.mailto})" if self.mailto else "CrossrefCrawler/1.0",
            "Accept": "application/json",
        }
        params: dict[str, str | int] = {
            "query": self.query,
            "rows": self.rows,
        }
        if filter_str:
            params["filter"] = filter_str
        if self.mailto:
            params["mailto"] = self.mailto

        max_retries = 5
        backoff_factor = 2

        logger.info(f"Start crawling from API URL: {self.url} with params: {params}")

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(self.url, headers=headers, params=params, timeout=30)
                status_code = response.status_code

                if status_code == 200:
                    return response.json()

                if status_code in [429, 500, 502, 503, 504]:
                    if attempt == max_retries:
                        logger.error(f"HTTP {status_code} on final attempt {attempt}. Raising exception.")
                        response.raise_for_status()
                    
                    sleep_time = backoff_factor ** attempt
                    logger.warning(f"Retry #{attempt} after HTTP {status_code}. Sleeping {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"HTTP {status_code} is not retryable. Raising exception.")
                    response.raise_for_status()

            except requests.RequestException as e:
                if attempt == max_retries:
                    logger.error(f"Request exception on final attempt {attempt}: {e}")
                    raise
                sleep_time = backoff_factor ** attempt
                logger.warning(f"Retry #{attempt} after exception: {e}. Sleeping {sleep_time} seconds...")
                time.sleep(sleep_time)

        raise RuntimeError("Failed to fetch data from Crossref API after maximum retries.")


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload into list of PaperRecord."""
    items = payload.get("message", {}).get("items", [])
    records: list[PaperRecord] = []

    for item in items:
        # 1. DOI -> paper_id
        doi = item.get("DOI", "")
        if not doi:
            continue

        # 2. Title
        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""

        # 3. Abstract -> summary
        summary = item.get("abstract", "")

        # Only keep records if both title and abstract (summary) exist and are not empty
        if not title or not summary:
            continue

        # 4. Authors
        authors_raw = item.get("author", [])
        authors: list[str] = []
        for author in authors_raw:
            given = author.get("given", "").strip()
            family = author.get("family", "").strip()
            if given and family:
                name = f"{given} {family}"
            elif family:
                name = family
            elif given:
                name = given
            else:
                name = author.get("name", "").strip()
            if name:
                authors.append(name)

        # 5. Categories (Subject)
        categories = item.get("subject", [])
        primary_category = categories[0] if categories else ""

        # 6. Published date
        published = None
        for field in ["published-online", "published-print", "published", "created"]:
            if field in item and "date-parts" in item[field]:
                parts = item[field]["date-parts"]
                if parts and parts[0] and parts[0][0] is not None:
                    date_parts = parts[0]
                    if len(date_parts) >= 3 and date_parts[1] is not None and date_parts[2] is not None:
                        published = f"{date_parts[0]:04d}-{date_parts[1]:02d}-{date_parts[2]:02d}"
                    elif len(date_parts) >= 2 and date_parts[1] is not None:
                        published = f"{date_parts[0]:04d}-{date_parts[1]:02d}"
                    elif len(date_parts) >= 1:
                        published = f"{date_parts[0]:04d}"
                    break
        if not published:
            published = "NaT"

        # 7. Updated date
        updated = published

        # 8. Abs URL
        abs_url = item.get("URL", "")

        # 9. PDF URL
        pdf_url = ""
        links = item.get("link", [])
        for link in links:
            if link.get("content-type") == "application/pdf":
                pdf_url = link.get("URL", "")
                break
        if not pdf_url and links:
            pdf_url = links[0].get("URL", "")

        # 10. Comment -> journal (container-title)
        container = item.get("container-title", [])
        comment = container[0] if container else ""

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Call source API, save raw response, parse into records."""
    # Instantiate crawler
    crawler = CrossrefCrawler(
        query=settings.source_query,
        rows=settings.max_results,
    )

    # Fetch raw HTTP response
    payload = crawler.fetch(filter_str=settings.source_filter)

    # Ensure output directories exist
    settings.paths.raw_api_response.parent.mkdir(parents=True, exist_ok=True)
    
    # Save Raw Artifact 1: Raw HTTP response
    with open(settings.paths.raw_api_response, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved raw response to {settings.paths.raw_api_response}")

    # Parse payload
    records = parse_crossref_payload(payload)
    logger.info(f"Total parsed records: {len(payload.get('message', {}).get('items', []))}")
    logger.info(f"Filtered records (with title and abstract): {len(records)}")

    # Save Raw Artifact 2: Parsed records
    records_dict = [asdict(r) for r in records]
    with open(settings.paths.raw_records_json, "w", encoding="utf-8") as f:
        json.dump(records_dict, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved parsed records to {settings.paths.raw_records_json}")

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Read JSON snapshot and map to PaperRecord."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    records = []
    for item in data:
        records.append(
            PaperRecord(
                paper_id=item["paper_id"],
                title=item["title"],
                summary=item["summary"],
                authors=item["authors"],
                categories=item["categories"],
                primary_category=item["primary_category"],
                published=item["published"],
                updated=item["updated"],
                abs_url=item["abs_url"],
                pdf_url=item["pdf_url"],
                comment=item["comment"],
            )
        )
    return records


if __name__ == "__main__":
    # Standard python logging configuration
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    from core.config import load_settings
    settings = load_settings()
    fetch_source_records(settings)
