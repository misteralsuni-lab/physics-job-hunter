"""
Search Associates authenticated scraper.

Source: https://www.searchassociates.com/

Search Associates is a gated international-school job board.  The protected
sections require an authenticated session — a single login flow gates the
job-search dashboard.  This scraper:

  * inherits from ``StealthBrowserScraper`` (hence requires Camoufox);
  * opens a fresh browser context per run, persists cookies across runs at
    ``.cache/sa_cookies.json`` so the multi-step login only happens once;
  * uses credentials from the environment (``SA_USERNAME`` / ``SA_PASSWORD``,
    loaded by ``src.config.settings``);
  * falls back to ``[]`` rather than raising if the environment is unset,
    the binary is absent, or the auth flow fails (pipeline never crashes).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from src.config import settings
from src.scrapers.browser_base import StealthBrowserScraper

log = logging.getLogger(__name__)


_LOGIN_URL = "https://www.searchassociates.com/login"
_DASHBOARD_URL = "https://www.searchassociates.com/dashboard"
_JOB_SEARCH_URL = (
    "https://www.searchassociates.com/jobs/results"
    "?Keywords=physics&Areas=0&Regions=0&SchoolTypes=0&Submit=Search"
)

_SELECTOR_USERNAME = "input[name='email'], input#email, input[type='email']"
_SELECTOR_PASSWORD = "input[name='password'], input#password, input[type='password']"
_SELECTOR_SUBMIT = (
    "button[type='submit'], input[type='submit'], button.login-submit"
)
_DASHBOARD_GUARD = ".dashboard-portlet, .user-menu, h1:has-text('Dashboard')"


class SearchAssociatesScraper(StealthBrowserScraper):
    SOURCE_NAME = "search_associates"
    BASE_URL = "https://www.searchassociates.com"

    cookies_path: Path | None = Path(".cache/sa_cookies.json")

    page_load_timeout_ms: int = 60000
    wait_after_load_ms: int = 4000

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        # Hard kill-switch first — no Camoufox import-chain must be touched
        # while dormant.  Default for ``CAMOUFOX_ENABLED`` is "0" so the
        # engine stays cold until the operator has provisioned the binary.
        if os.getenv("CAMOUFOX_ENABLED", "0") == "0":
            log.info(
                "[search_associates] running in dormant mode "
                "(CAMOUFOX_ENABLED=0)."
            )
            return []

        if not self._credentials_configured():
            log.warning(
                "[search_associates] SA_USERNAME / SA_PASSWORD not set in .env "
                "— skipping authenticated scrape, returning []."
            )
            return []

        try:
            return self._scrape_under_browser()
        except Exception as exc:
            log.warning(
                "[search_associates] scrape failed: %s — returning []", exc
            )
            return []

    def _scrape_under_browser(self) -> list[dict[str, Any]]:
        from src.scrapers.browser_base import CAMOUFOX_AVAILABLE
        if not CAMOUFOX_AVAILABLE:
            log.warning(
                "[search_associates] camoufox module missing — install with: "
                "pip install 'camoufox[geoip]' && python -m camoufox fetch"
            )
            return []

        from camoufox.sync_api import Camoufox
        with Camoufox(
            headless=self.headless, humanise=self.humanise,
            geoip=os.environ.get("CAMOUFOX_GEOIP", True),
            screen=self._pick_screen(),
            enable_cache=False,
        ) as browser:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    if not self._attempt_authenticated_session(context, page):
                        log.warning(
                            "[search_associates] authentication failed — "
                            "returning []."
                        )
                        return []
                    listings = self._fetch_job_listings(page)
                    log.info("  → %d jobs from search_associates", len(listings))
                    return listings
                finally:
                    page.close()
            finally:
                context.close()

    def _attempt_authenticated_session(self, context: Any, page: Any) -> bool:
        if self.load_cookies(context):
            if self._is_session_valid(page):
                log.info(
                    "[search_associates] resumed session from %s",
                    self._cookies_path,
                )
                return True
            log.info(
                "[search_associates] stale cookies on %s — re-authenticating.",
                self._cookies_path,
            )

        if not self._login_with_credentials(page):
            return False

        self.save_cookies(context)
        return True

    def _is_session_valid(self, page: Any) -> bool:
        try:
            page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(self.wait_after_load_ms)
            if page.query_selector(_SELECTOR_USERNAME):
                return False
            return bool(page.query_selector(_DASHBOARD_GUARD))
        except Exception as exc:
            log.debug("[search_associates] dashboard probe failed: %s", exc)
            return False

    def _login_with_credentials(self, page: Any) -> bool:
        try:
            page.goto(_LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_selector(_SELECTOR_USERNAME, timeout=self.page_load_timeout_ms)
            page.wait_for_selector(_SELECTOR_PASSWORD, timeout=self.page_load_timeout_ms)
            page.fill(_SELECTOR_USERNAME, settings.sa_username)
            page.fill(_SELECTOR_PASSWORD, settings.sa_password)
            page.click(_SELECTOR_SUBMIT)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(self.wait_after_load_ms * 2)
            if page.query_selector(_SELECTOR_USERNAME):
                log.warning(
                    "[search_associates] login form still visible after submit "
                    "— credentials may be invalid."
                )
                return False
            return bool(page.query_selector(_DASHBOARD_GUARD))
        except Exception as exc:
            log.warning("[search_associates] login flow raised: %s", exc)
            return False

    def _fetch_job_listings(self, page: Any) -> list[dict[str, Any]]:
        try:
            page.goto(_JOB_SEARCH_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(self.wait_after_load_ms)
        except Exception as exc:
            log.warning(
                "[search_associates] job-search navigation failed: %s", exc
            )
            return []
        return self._extract_jobs(page.content())

    def _extract_jobs(self, html: str) -> list[dict[str, Any]]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        card_selectors = (
            "tr.job-row",
            "tr.result-row",
            "article.job-listing",
            "div.job-listing",
            "li.job",
        )
        title_selectors = (
            "a.job-title",
            "h3 a",
            "h2 a",
            ".title a",
        )

        cards: list = []
        for sel in card_selectors:
            found = soup.select(sel)
            if found and len(found) >= 2:
                cards = found
                break
        if not cards:
            return []

        results: list[dict[str, Any]] = []
        for card in cards:
            link_el = None
            for tsel in title_selectors:
                link_el = card.select_one(tsel)
                if link_el:
                    break
            if not link_el:
                continue

            title = self.extract_text(link_el).strip()
            if not title or len(title) < 4:
                continue

            href = self.extract_attr(link_el, "href")
            if not href:
                continue

            school = ""
            school_el = card.select_one(
                ".school, .school-name, .employer, .client, td.school"
            )
            if school_el:
                school = self.extract_text(school_el)

            location_el = card.select_one(
                ".location, .country, td.location, td.country"
            )
            location = self.extract_text(location_el) if location_el else ""
            country = ""
            if location:
                country = location.split(",")[-1].strip()

            closing_date = None
            closing_el = card.select_one(
                ".closing-date, .deadline, .date-closing, td.closing-date"
            )
            if closing_el:
                raw = self.extract_text(closing_el).strip()
                if raw and raw.lower() not in ("", "n/a"):
                    closing_date = raw

            lower_title = title.lower()
            results.append({
                "title": title,
                "url": self.absolute_url(href),
                "school": school,
                "location": location,
                "country": country,
                "salary_range": "",
                "closing_date": closing_date,
                "subject": ["Physics"] if "physics" in lower_title else [],
                "curriculum": [],
                "job_type": "",
                "provider": "search_associates",
                "curriculum_board": None,
            })

        return results

    @staticmethod
    def _credentials_configured() -> bool:
        return bool(settings.sa_username) and bool(settings.sa_password)


__all__ = ["SearchAssociatesScraper"]
