"""
Dipont Education scraper.
Monitors https://www.dipont.com/careers/independent-schools-jobs/ for teaching posts.
Extracts: url, title, school (provider), closing_date, curriculum_board.
"""
from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class DipontScraper(BaseScraper):
    SOURCE_NAME = "dipont"
    BASE_URL = "https://www.dipont.com"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        soup = self.fetch("/careers/independent-schools-jobs/")
        jobs = self._extract_jobs(soup)

        for j in jobs:
            url = j.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            j["source"] = "dipont"
            all_jobs.append(j)

        return all_jobs

    def _extract_jobs(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        # Generic selectors — adjust after inspecting live HTML
        cards = soup.select("div.job-item, article.career, div.vacancy, .career-listing__item")

        for card in cards:
            title_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link")
            if not title_el:
                continue

            title = self.extract_text(title_el)
            url = self.extract_attr(title_el, "href")
            if not url:
                continue

            school = ""
            school_el = card.select_one(".school, .campus, .location")
            if school_el:
                school = self.extract_text(school_el)

            closing = None
            closing_el = card.select_one(".closing-date, .deadline, .apply-by")
            if closing_el:
                raw = self.extract_text(closing_el)
                if raw:
                    closing = raw

            if closing == "":
                closing = None

            # Subject / curriculum: NEVER pre-tag.  The hard-coded
            # curriculum_board="Edexcel" you may see in earlier revisions
            # has been removed — it lied about every Dipont listing in
            # exactly the same way the subject=Physics default used to.
            # Both fields must derive from the listing *text* or stay empty.
            results.append({
                "title": title,
                "url": self.absolute_url(url),
                "school": school or "Dipont Education",
                "location": "",
                "country": "",
                "salary_range": "",
                "closing_date": closing,
                "subject": (
                    ["Physics"] if "physics" in (title or "").lower() else []
                ),
                "curriculum": [],
                "job_type": "",
                "provider": "dipont",
                "curriculum_board": (
                    "Edexcel" if "edexcel" in (title or "").lower() else None
                ),
            })

        return results
