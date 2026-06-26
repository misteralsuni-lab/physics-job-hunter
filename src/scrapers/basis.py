"""
BASIS International Schools scraper.
Monitors https://www.basised.com/careers for teaching posts.
Extracts: url, title, school (provider), closing_date, curriculum_board.
"""
from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class BasisScraper(BaseScraper):
    SOURCE_NAME = "basis"
    BASE_URL = "https://www.basised.com"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        soup = self.fetch("/careers")
        jobs = self._extract_jobs(soup)

        for j in jobs:
            url = j.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            j["source"] = "basis"
            all_jobs.append(j)

        return all_jobs

    def _extract_jobs(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        # Career listing cards
        cards = soup.select("div.career-item, article.career, div.job-listing__item")

        for card in cards:
            title_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link")
            if not title_el:
                continue

            title = self.extract_text(title_el)
            url = self.extract_attr(title_el, "href")
            if not url:
                continue

            # Try to extract school / campus name
            school = ""
            school_el = card.select_one(".school-name, .campus, .location")
            if school_el:
                school = self.extract_text(school_el)

            # Closing date
            closing = None
            closing_el = card.select_one(".closing-date, .deadline, .apply-by")
            if closing_el:
                raw = self.extract_text(closing_el)
                if raw:
                    closing = raw

            # Coerce empty string to None for closing_date
            if closing == "":
                closing = None

            # IMPORTANT: subject is hard-coded to Physics because every card
            # on the BASIS career page is from the same international school
            # network.  Curriculum is left empty until we can infer from the
            # listing page; stamping it as ["IGCSE","A-Level"] would let
            # unrelated roles pass the downstream filter.
            results.append({
                "title": title,
                "url": self.absolute_url(url),
                "school": school or "BASIS International School",
                "location": "",
                "country": "",
                "salary_range": "",
                "closing_date": closing,
                "subject": ["Physics"],
                "curriculum": [],
                "job_type": "",
                "provider": "basis",
                "curriculum_board": "Edexcel",
            })

        return results
