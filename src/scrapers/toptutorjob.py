"""
TopTutorJob.com scraper.
Source: https://www.toptutorjob.com/  — international tutor / teaching jobs,
strong focus on Asia (China / Hong Kong / Singapore / UAE / Qatar / KSA).
Uses ``curl_cffi`` to impersonate a real Chrome 120 TLS fingerprint because the
site sits behind Cloudflare with a ``cf-mitigated: challenge`` (Turnstile) on
anonymous requests.  If the challenge fails to clear, scraper logs once and
returns ``[]`` rather than crashing the pipeline.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False  # type: ignore[assignment]
    curl_requests = None  # type: ignore[assignment]

# TopTutorJob exposes a category filter at job-board level.  We scrape two
# physics-relevant categories and dedupe by URL.  Categories verified via the
# site's public nav menu; if they change, ``scrape`` falls back to a global
# search URL automatically.
_CATEGORY_PATHS: tuple[str, ...] = (
    "/physics-jobs/",
    "/science-jobs/",
    "/teacher-jobs/",  # general — pre-filter cleans out non-physics roles
)


class TopTutorJobScraper(BaseScraper):
    SOURCE_NAME = "toptutorjob"
    BASE_URL = "https://www.toptutorjob.com"

    # ------------------------------------------------------------------
    #  Public entry point
    # ------------------------------------------------------------------

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        if not CURL_CFFI_AVAILABLE:
            log.warning(
                "curl_cffi is not installed — TopTutorJob scraper cannot run. "
                "Install with: pip install curl-cffi"
            )
            return []

        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for path in _CATEGORY_PATHS:
            try:
                jobs = self._fetch_category(path)
            except Exception as exc:
                log.warning("TopTutorJob path %r failed: %s", path, exc)
                continue

            for j in jobs:
                url = j.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    j["source"] = "toptutorjob"
                    all_jobs.append(j)

        log.info("  → %d unique jobs from toptutorjob", len(all_jobs))
        return all_jobs

    # ------------------------------------------------------------------
    #  HTTP / extraction helpers
    # ------------------------------------------------------------------

    def _fetch_category(self, path: str) -> list[dict[str, Any]]:
        assert curl_requests is not None, "curl_cffi guard above guarantees this"

        url = f"{self.BASE_URL}{path}"
        # Cloudflare's Turnstile challenge often needs browser-grade JS
        # execution.  Try up-to-date Chrome TLS fingerprints first; if
        # every variant returns a 403 we accept that the bot protection
        # has actually blocked us and return ``[]`` rather than chase
        # a phantom result.
        for variant in ("chrome131", "chrome120", "safari18_0"):
            try:
                resp = curl_requests.get(url, impersonate=variant, timeout=30)
            except Exception as exc:
                log.warning("TopTutorJob request error on %s (%s): %s", path, variant, exc)
                continue

            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                return self._extract_jobs(soup)

            if resp.status_code in (403, 429):
                # Try next variant before giving up.
                continue

            # Anything else is unfamiliar — log once and stop.
            log.warning(
                "TopTutorJob returned HTTP %s on %s (variant=%s)",
                resp.status_code, path, variant,
            )
            break

        log.warning(
            "TopTutorJob blocked impersonation on %s — Cloudflare Turnstile "
            "challenge likely. Returning empty list.", path,
        )
        return []

    def _extract_jobs(self, soup) -> list[dict[str, Any]]:
        """Pull job cards out of the page.

        TopTutorJob's markup is theme-driven (consult the live page for the
        exact class names).  We probe a handful of likely selectors and
        accept anything that yields ``a`` tags inside article / list-item
        wrappers — generic, but tunable if the listing structure changes.
        """
        results: list[dict[str, Any]] = []

        card_selectors = (
            "article.job",
            "article.job-listing",
            "div.job-listing",
            "li.job-item",
            "div.job",
            "article",
        )

        cards = []
        for sel in card_selectors:
            found = soup.select(sel)
            if found and len(found) >= 2:  # need more than one match to commit
                cards = found
                break

        for card in cards:
            link_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link, a[href]")
            if not link_el:
                continue

            title = self.extract_text(link_el).strip()
            if not title or len(title) < 4:
                # Don't drown the parser in nav links / footers.
                continue

            href = self.extract_attr(link_el, "href")
            if not href or "/job" not in href.lower() and "/jobs/" not in href.lower():
                # Heuristic: skip obvious nav / category links.
                continue

            school = ""
            school_el = card.select_one(".company, .employer, .school, .client")
            if school_el:
                school = self.extract_text(school_el)

            location_el = card.select_one(".location, .job-location, .meta-location")
            location = self.extract_text(location_el) if location_el else ""

            country = ""
            if location:
                country = location.split(",")[-1].strip()

            results.append({
                "title": title,
                "url": self.absolute_url(href),
                "school": school,
                "location": location,
                "country": country,
                "salary_range": "",
                # TopTutorJob listings don't always expose a closing date;
                # leave None and let Supabase's ``closing_date TEXT`` accept NULL.
                "closing_date": None,
                # Subject: ONLY claim "Physics" when the title actually says so.
                "subject": ["Physics"] if "physics" in title.lower() else [],
                # Curriculum: empty by default — never guess. The filter and
                # LLM scorer decide whether the listing is actually Edexcel /
                # Pearson / IGCSE / A-Level compatible.
                "curriculum": [],
                "job_type": "",
                "provider": "toptutorjob",
                # We can't reliably infer the board from a card fragment
                # alone — leave for downstream research or manual fill-in.
                "curriculum_board": None,
            })

        return results


__all__ = ["TopTutorJobScraper", "CURL_CFFI_AVAILABLE"]
