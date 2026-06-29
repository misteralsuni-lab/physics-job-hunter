"""
TopTutorJob.com scraper.
Source: https://www.toptutorjob.com/  — international tutor / teaching jobs,
strong focus on Asia (China).

Built on ``StealthBrowserScraper`` (Camoufox / hardened Firefox) because the
site sits behind Cloudflare Turnstile — curl_cffi TLS impersonation returns
HTTP 403 on anonymous requests.  Camoufox executes the Turnstile JS in a
real browser engine, which resolves the challenge after ~26s.

The site runs Drupal 11.  Job listings are rendered server-side in a flat
``<ul>`` with each job in an ``<li>``.  No client-side rendering or API
endpoint is available for job data.

Fallback policy
---------------
* If Camoufox is unavailable (``CAMOUFOX_ENABLED=0`` or binary missing), the
  scraper logs a warning and returns ``[]`` rather than crashing the pipeline.
* Any exception inside ``get_page_source()`` is caught and surfaced as
  ``None``; that propagates to ``[]`` here.
* Memory freed deterministically via ``_browser_session`` (context manager).
"""
from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.scrapers.browser_base import StealthBrowserScraper

log = logging.getLogger(__name__)


# TopTutorJob is a Drupal site with a single /jobs listing page and
# query-parameter search.  We issue one search per keyword rather than
# relying on category URLs (which no longer exist).
_SEARCH_TERMS: tuple[str, ...] = (
    "physics",
    "science",
    "teacher",
)


class TopTutorJobScraper(StealthBrowserScraper):
    SOURCE_NAME = "toptutorjob"
    BASE_URL = "https://www.toptutorjob.com"

    # ---- Camoufox tuning ------------------------------------------------
    page_load_timeout_ms: int = 60000
    # Cloudflare Turnstile takes ~26s to complete on this site.  We wait
    # for the main content container (div.view-content) which only appears
    # after the challenge resolves.
    wait_after_load_ms: int = 30000

    # ------------------------------------------------------------------
    #  Public entry point
    # ------------------------------------------------------------------

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        if not settings.camoufox_enabled:
            log.info(
                "[toptutorjob] running in dormant mode (camoufox_enabled=False)."
            )
            return []

        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        terms = search_terms or list(_SEARCH_TERMS)
        for term in terms:
            url = f"{self.BASE_URL}/jobs?title={term}"
            html = self.get_page_source(
                url,
                wait_for_selector="div.view-content",
                timeout_ms=60000,
            )
            if not html:
                log.warning(
                    "[toptutorjob] no HTML returned for term=%s — skipping", term,
                )
                continue

            jobs = self._extract_jobs(html)
            for j in jobs:
                eurl = j.get("url", "")
                if eurl and eurl not in seen_urls:
                    seen_urls.add(eurl)
                    j["source"] = "toptutorjob"
                    all_jobs.append(j)

        log.info("  → %d unique jobs from toptutorjob", len(all_jobs))
        return all_jobs

    # ------------------------------------------------------------------
    #  HTML extraction (BeautifulSoup)
    # ------------------------------------------------------------------

    def _extract_jobs(self, html: str) -> list[dict[str, Any]]:
        """Parse the Drupal 11 job listing page.

        DOM structure (2026-06-29):
          div.view-content > div.item-list > ul > li
            div.job-card
              div.job-card-top-left
                div.views-field-title > a[href*="/job/"]    ← title + URL
                div.job-card-salary > a                      ← salary range
                div.job-card-province                         ← city, province
              div.job-card-bottom
                div.bottom > div.bottom-school
                  a[href*="/school/"] > span.school-title    ← school name
                div.bottom-target-date                        ← start date
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # Each job is an <li> inside the view-content list.
        card_els = soup.select("div.view-content div.item-list ul > li")
        if not card_els:
            return []
        results: list[dict[str, Any]] = []
        for li in card_els:
            title_el = li.select_one(
                "div.job-card-top-left div.views-field-title a[href]"
            )
            if not title_el:
                continue

            title = self.extract_text(title_el).strip()
            if not title or len(title) < 4:
                continue

            href = self.extract_attr(title_el, "href")
            if not href:
                continue
            job_url = self.absolute_url(href)

            # Salary: inside job-card-salary, the anchor text is the range
            salary = ""
            salary_el = li.select_one("div.job-card-salary a, div.job-card-salary")
            if salary_el:
                salary = self.extract_text(salary_el).strip()

            # Location: "City,Province" inside job-card-province.
            # Site is exclusively China-based so country is always "China".
            location = ""
            loc_el = li.select_one("div.job-card-province")
            if loc_el:
                location = self.extract_text(loc_el).strip()
                location = location.replace(",", ", ").strip()

            country = "China"

            # School name: span.school-title inside bottom-school
            school = ""
            school_el = li.select_one("div.bottom-school span.school-title")
            if school_el:
                school = self.extract_text(school_el).strip()

            # Start date: bottom-target-date
            closing_date = None
            date_el = li.select_one("div.bottom-target-date")
            if date_el:
                raw = self.extract_text(date_el).strip()
                if raw:
                    closing_date = raw

            results.append({
                "title": title,
                "url": job_url,
                "school": school,
                "location": location,
                "country": country,
                "salary_range": salary,
                "closing_date": closing_date,
                "subject": ["Physics"] if "physics" in title.lower() else [],
                "curriculum": [],
                "job_type": "",
                "provider": "toptutorjob",
                "curriculum_board": None,
            })

        return results


__all__ = ["TopTutorJobScraper"]
