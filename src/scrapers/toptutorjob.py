"""
TopTutorJob.com scraper.
Source: https://www.toptutorjob.com/  — international tutor / teaching jobs,
strong focus on Asia (China / Hong Kong / Singapore / UAE / Qatar / KSA).

Built on ``StealthBrowserScraper`` (Camoufox / hardened Firefox) because the
site sits behind Cloudflare Turnstile — curl_cffi TLS impersonation returns
HTTP 403 on anonymous requests.  Camoufox executes the Turnstile JS in a
real browser engine, which resolves the challenge in normal cases.

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
import os
from typing import Any

from src.config import settings
from src.scrapers.browser_base import StealthBrowserScraper

log = logging.getLogger(__name__)


# TopTutorJob exposes a category filter at job-board level.  These three
# categories cover direct physics / science / education feed.
_CATEGORY_PATHS: tuple[str, ...] = (
    "/physics-jobs/",
    "/science-jobs/",
    "/teacher-jobs/",
)

# Most plausible selectors for the eventual job-listing container.
# Used purely as a "page rendered correctly" health-check after the Turnstile
# wait — we don't rely on them for HTML extraction (we re-parse the returned
# source independently with BeautifulSoup below).
_JOB_CONTAINER_SELECTORS: tuple[str, ...] = (
    "article.job",
    "article.job-listing",
    "div.job-listing",
    "li.job-item",
    "div.job",
    ".job-card",
    "article",
)


class TopTutorJobScraper(StealthBrowserScraper):
    SOURCE_NAME = "toptutorjob"
    BASE_URL = "https://www.toptutorjob.com"

    # ---- Camoufox tuning ------------------------------------------------
    page_load_timeout_ms: int = 45000
    # TopTutorJob uses a fairly aggressive Cloudflare setup.  Give Turnstile
    # time to execute its challenge script + redirect to the listing page
    # before we ask Playwright to assert a selector.
    wait_after_load_ms: int = 5500

    # ------------------------------------------------------------------
    #  Public entry point
    # ------------------------------------------------------------------

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        # Hard kill-switch — short-circuit BEFORE any Camoufox import-chain is
        # touched.  Default for ``CAMOUFOX_ENABLED`` is "0" (dormant) so the
        # engine stays cold until the operator has provisioned the binary.
        if not settings.camoufox_enabled:
            log.info(
                "[toptutorjob] running in dormant mode (camoufox_enabled=False)."
            )
            return []

        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for path in _CATEGORY_PATHS:
            url = f"{self.BASE_URL}{path}"
            html = self.get_page_source(
                url,
                wait_for_selector=self._pick_container_selector(),
            )
            if not html:
                log.warning(
                    "[toptutorjob] no HTML returned for %s — skipping", path,
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

    def _pick_container_selector(self) -> str | None:
        """Return the first selector we believe is on a real listing page.
        If the live site reorganises its DOM only the preferred selector
        changes — extraction itself uses a fallback chain."""
        return _JOB_CONTAINER_SELECTORS[0]

    def _extract_jobs(self, html: str) -> list[dict[str, Any]]:
        """Parse *html* and pull job cards out of the page.

        Extraction logic:
          * probe a handful of likely containers (covers the current site
            themes and most likely refactors);
          * for each card grab title via common heading/text patterns;
          * infer school, location, and URL;
          * leave curriculum empty so downstream ``_is_relevant()`` decides.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        cards = []
        for sel in _JOB_CONTAINER_SELECTORS:
            found = soup.select(sel)
            if found and len(found) >= 2:
                cards = found
                break

        # If a generic container matched but didn't yield >=2 cards we
        # accept single-card matches only when the selector is highly
        # specific (otherwise we'd extract nav links).
        if not cards:
            return []

        results: list[dict[str, Any]] = []
        for card in cards:
            link_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link, a[href]")
            if not link_el:
                continue

            title = self.extract_text(link_el).strip()
            if not title or len(title) < 4:
                continue

            href = self.extract_attr(link_el, "href")
            if not href:
                continue
            # Drop nav/category/manufactured noise: keep only links that
            # look like a job post.
            href_lower = href.lower()
            if not (
                "/job" in href_lower
                or "/tutor" in href_lower
                or "/vacancy" in href_lower
            ):
                continue

            school = ""
            school_el = card.select_one(
                ".company, .employer, .school, .client, .organization"
            )
            if school_el:
                school = self.extract_text(school_el)

            location_el = card.select_one(
                ".location, .job-location, .meta-location, .place"
            )
            location = self.extract_text(location_el) if location_el else ""

            country = ""
            if location:
                country = location.split(",")[-1].strip()

            # Closing date: TopTutorJob typically displays a "Posted ..."
            # rather than a hard closing date.  Capture it for completeness
            # but treat as posted_at downstream rather than deadline.
            closing_date = None
            closing_el = card.select_one(
                ".closing-date, .deadline, .closing, .apply-by"
            )
            if closing_el:
                raw = self.extract_text(closing_el).strip()
                if raw and raw.lower() not in ("", "n/a", "none"):
                    closing_date = raw

            # Subject: only claim "Physics" when the title actually says so.
            # Curriculum: empty by default — never guess; the pre-filter
            # and LLM scorer decide.
            results.append({
                "title": title,
                "url": self.absolute_url(href),
                "school": school,
                "location": location,
                "country": country,
                "salary_range": "",
                "closing_date": closing_date,
                "subject": ["Physics"] if "physics" in title.lower() else [],
                "curriculum": [],
                "job_type": "",
                "provider": "toptutorjob",
                # We can't reliably infer the board from a card fragment
                # alone — leave to downstream research / manual fill-in.
                "curriculum_board": None,
            })

        return results


__all__ = ["TopTutorJobScraper"]
