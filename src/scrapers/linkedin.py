"""
LinkedIn scraper with stealth fingerprinting.

Uses ``curl-impersonate`` (via ``curl_cffi``) to avoid trivial bot detection.
If ``curl_cffi`` is not installed the scraper degrades to an empty-list
placeholder and logs a warning.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False  # type: ignore[assignment]
    curl_requests = None  # type: ignore[assignment]


class LinkedInScraper(BaseScraper):
    SOURCE_NAME = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        if not CURL_CFFI_AVAILABLE:
            log.warning(
                "curl_cffi is not installed — LinkedIn scraper cannot run. "
                "Install with: pip install curl-cffi"
            )
            return []

        if search_terms is None:
            search_terms = ["Physics teacher", "IGCSE Physics", "A-Level Physics"]

        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for term in search_terms:
            jobs = self._fetch_linkedin_jobs(term)
            for j in jobs:
                url = j.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    j["source"] = "linkedin"
                    all_jobs.append(j)

        return all_jobs

    def _fetch_linkedin_jobs(self, query: str, pages: int = 1) -> list[dict[str, Any]]:
        """Search LinkedIn public job listings via curl-impersonate."""
        assert curl_requests is not None

        jobs: list[dict[str, Any]] = []
        start = 0
        for _ in range(pages):
            # Public search endpoint (no auth required)
            url = (
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={self._enc(query)}&location=Worldwide&start={start}"
            )
            try:
                resp = curl_requests.get(url, impersonate="chrome120")  # type: ignore[arg-type]
                resp.raise_for_status()
            except Exception as exc:
                log.warning("LinkedIn request failed: %s", exc)
                break

            soup = self._soup_from_text(resp.text)  # type: ignore[arg-type]
            cards = soup.select("li") if soup else []

            for card in cards:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle a")
                meta_el = card.select_one("div.base-search-card__metadata")
                link_el = card.select_one("a.base-card__full-link")

                if not title_el or not link_el:
                    continue

                title = self.extract_text(title_el)
                company = self.extract_text(company_el) if company_el else ""
                location = self.extract_text(meta_el) if meta_el else ""
                raw_url = self.extract_attr(link_el, "href")

                # Normalise URL to the canonical public job page
                url = raw_url.split("?")[0] if raw_url else ""

                if not url:
                    continue

                # Curriculum inference
                curriculum = self._infer_curriculum(title)
                # Closing date — LinkedIn does not expose this on the search card;
                # we leave it None so upstream coercion handles it.
                closing_date = None

                jobs.append({
                    "title": title,
                    "url": url,
                    "school": company,
                    "location": location,
                    "country": location.split(",")[-1].strip() if "," in location else location,
                    "salary_range": "",
                    "closing_date": closing_date,
                    # Subject: ONLY mark "Physics" when the title actually says so.
                    # Other subjects must NOT be tagged as "Physics" — filtering
                    # happens downstream against the strict subject requirement
                    # and a lying tag would let "Geography teacher" through.
                    "subject": ["Physics"] if "physics" in title.lower() else [],
                    "curriculum": curriculum,
                    "job_type": "",
                    "provider": "linkedin",
                })

            start += 25
            if len(cards) < 5:
                break

        return jobs

    @staticmethod
    def _enc(text: str) -> str:
        from urllib.parse import quote
        return quote(text)

    @staticmethod
    def _soup_from_text(text: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "lxml")

    @staticmethod
    def _infer_curriculum(title: str) -> list[str]:
        """Detect curriculum from the job title.

        IMPORTANT: returns an *empty* list when nothing matches; it must NOT
        default to a guess that misleads the downstream filter and LLM scorer
        (a UK Edexcel teacher and an American-curriculum teacher both get
        tagged with the same false "IGCSE, A-Level" otherwise).
        """
        t = title.lower()
        curricula: list[str] = []
        if "igcse" in t:
            curricula.append("IGCSE")
        if "a-level" in t or "a level" in t:
            curricula.append("A-Level")
        if "ib" in t:
            curricula.append("IB")
        if "gcse" in t and "igcse" not in t:
            curricula.append("GCSE")
        return curricula
