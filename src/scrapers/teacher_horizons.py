"""
Teacher Horizons authenticated scraper.

Source: https://www.teacherhorizons.com/

Teacher Horizons is a paid-recruulter international teaching-job platform.
Reconnaissance (2026-06-27) confirmed:

  * The public ``/jobs`` page is an Angular SPA shell — no static HTML
    payload to scrape.
  * A JSON:API-style endpoint exists at
    ``https://beta.teacherhorizons.com/th/api/jobs`` but **every** path
    (``/jobs``, ``/job-gateway/*``, ``/th/api/jobs/*``) returns
    ``401 Unauthorized`` without a session cookie.
  * The login flow is ``POST /auth/sign-in`` (multipart ``FormData``).

Architectural consequence: no ``BaseScraper`` (HTTP) fallback exists —
the only path to listings is the authenticated browser flow.  We follow
the same hardened pattern used by ``SearchAssociatesScraper``:

  * inherit ``StealthBrowserScraper`` (Camoufox under the hood);
  * kill-switch default ``0`` (``CAMOUFOX_ENABLED``) like the rest of
    the browser fleet — never auto-fetch the binary;
  * cookies persisted to ``.cache/th_cookies.json`` so the form post
    only happens on a clean run;
  * credentials read from ``TH_EMAIL`` / ``TH_PASSWORD`` in ``.env``;
  * jobs deliver from the API in JSON:API envelope; mapped to the
    user-supplied contract:
        ``{'title', 'company', 'location', 'url', 'source': 'TeacherHorizons'}``

Fallback policy
---------------
* If ``CAMOUFOX_ENABLED!=1`` → return ``[]`` immediately, log once.
* If ``camoufox`` module missing → install hint + ``[]``.
* If credentials missing → log once, return ``[]``.
* If auth flow raises or cookies are stale → log warning + ``[]``.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from src.config import settings
from src.scrapers.browser_base import StealthBrowserScraper

log = logging.getLogger(__name__)


_LOGIN_URL = "https://www.teacherhorizons.com/user/sign-in"
_AUTH_API = "https://www.teacherhorizons.com/auth/sign-in"
_DASHBOARD_URL = "https://www.teacherhorizons.com/candidates/dashboard"
_JOB_SEARCH_URL = (
    "https://beta.teacherhorizons.com/th/api/jobs"
    "?page[number]=1&page[size]=50"
    "&filter[latestEmploymentRecord.subject.id]=Physics"
)

_SELECTOR_EMAIL = "input[name='email'], input#email, input[type='email']"
_SELECTOR_PASSWORD = "input[name='password'], input#password, input[type='password']"
_SELECTOR_SUBMIT = (
    "button[type='submit'], input[type='submit'], button.sign-in-submit"
)
_DASHBOARD_GUARD = ".user-menu, .dashboard, h1:has-text('Dashboard')"


class TeacherHorizonsScraper(StealthBrowserScraper):
    SOURCE_NAME = "teacher_horizons"
    BASE_URL = "https://www.teacherhorizons.com"

    # NOTE: per the user-supplied contract, every record's
    # ``source`` field is the literal string ``"TeacherHorizons"`` (one
    # word, capitalised) — keep this distinct from the internal
    # SOURCE_NAME which the rest of the pipeline reads in snake_case.
    PUBLIC_SOURCE = "TeacherHorizons"

    cookies_path: Path | None = Path(".cache/th_cookies.json")

    page_load_timeout_ms: int = 60000
    wait_after_load_ms: int = 3500

    # ------------------------------------------------------------------
    #  Public entry point
    # ------------------------------------------------------------------

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        # Spec-mandated kill-switch (Phase 2 hardening).  Must run before
        # any Camoufox import chain is touched.  Default ``"0"`` so the
        # engine stays dormant unless the operator explicitly opts in.
        import os
        if os.environ.get("CAMOUFOX_ENABLED", "0") != "1":
            log.info("running in dormant mode (CAMOUFOX_ENABLED != 1)")
            return []

        if not self._credentials_configured():
            log.warning(
                "[teacher_horizons] TH_EMAIL / TH_PASSWORD not set in .env "
                "— skipping authenticated scrape, returning []."
            )
            return []

        try:
            return self._scrape_under_browser()
        except Exception as exc:
            log.warning(
                "[teacher_horizons] scrape failed: %s — returning []", exc
            )
            return []

    # ------------------------------------------------------------------
    #  Internal browser-driven flow
    # ------------------------------------------------------------------

    def _scrape_under_browser(self) -> list[dict[str, Any]]:
        from src.scrapers.browser_base import CAMOUFOX_AVAILABLE
        if not CAMOUFOX_AVAILABLE:
            log.warning(
                "[teacher_horizons] camoufox module missing — install with: "
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
                            "[teacher_horizons] authentication failed "
                            "— returning []."
                        )
                        return []
                    listings = self._fetch_job_listings(page)
                    log.info("  → %d jobs from teacher_horizons", len(listings))
                    return listings
                finally:
                    page.close()
            finally:
                context.close()

    def _attempt_authenticated_session(self, context: Any, page: Any) -> bool:
        # 1. Cookie resume.
        if self.load_cookies(context):
            if self._is_session_valid(page):
                log.info(
                    "[teacher_horizons] resumed session from %s",
                    self._cookies_path,
                )
                return True
            log.info(
                "[teacher_horizons] stale cookies on %s — re-authenticating.",
                self._cookies_path,
            )

        # 2. Cold-start credential login.
        if not self._login_with_credentials(page):
            return False

        # Persist cookies for the next run.
        self.save_cookies(context)
        return True

    def _is_session_valid(self, page: Any) -> bool:
        try:
            page.goto(_DASHBOARD_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(self.wait_after_load_ms)
            # If the SPA bounced us back to the sign-in form, cookies expired.
            if page.query_selector(_SELECTOR_EMAIL):
                return False
            return bool(page.query_selector(_DASHBOARD_GUARD))
        except Exception as exc:
            log.debug("[teacher_horizons] dashboard probe failed: %s", exc)
            return False

    def _login_with_credentials(self, page: Any) -> bool:
        try:
            page.goto(_LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_selector(_SELECTOR_EMAIL, timeout=self.page_load_timeout_ms)
            page.wait_for_selector(_SELECTOR_PASSWORD, timeout=self.page_load_timeout_ms)
            page.fill(_SELECTOR_EMAIL, settings.th_email)
            page.fill(_SELECTOR_PASSWORD, settings.th_password)
            page.click(_SELECTOR_SUBMIT)
            page.wait_for_load_state("domcontentloaded")
            # Angular SPAs need a beat to settle once auth is set.
            page.wait_for_timeout(self.wait_after_load_ms * 2)
            # If the sign-in form is still rendered, credentials were wrong.
            if page.query_selector(_SELECTOR_EMAIL):
                log.warning(
                    "[teacher_horizons] login form still visible after submit "
                    "— credentials may be invalid."
                )
                return False
            return bool(page.query_selector(_DASHBOARD_GUARD))
        except Exception as exc:
            log.warning("[teacher_horizons] login flow raised: %s", exc)
            return False

    def _fetch_job_listings(self, page: Any) -> list[dict[str, Any]]:
        """Hit ``/th/api/jobs`` from the authenticated browser, extract
        structured listings, and reshape into the user-supplied 5-key
        contract."""
        try:
            page.goto(_JOB_SEARCH_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(self.wait_after_load_ms)
        except Exception as exc:
            log.warning(
                "[teacher_horizons] job-search navigation failed: %s", exc
            )
            return []
        return self._extract_jobs(page.content())

    # ------------------------------------------------------------------
    #  HTML extraction (BeautifulSoup — JSON:API envelope)
    # ------------------------------------------------------------------

    def _extract_jobs(self, html: str) -> list[dict[str, Any]]:
        """Parse the JSON:API payload Teacher Horizons' browser emits.

        The page is mostly SPA shell, but on a fully-loaded authed
        navigation the API response is rendered as ``<pre>`` containing
        the JSON; some Angular versions embed it as ``window.__DATA__``
        or in a hidden application cache.  We try a JSON-shaped parse
        first, then a regex over the page source.
        """
        import json, re
        try:
            payload = json.loads(html)
            data = payload.get("data", payload)
        except Exception:
            # Fallback: regex-pull the first JSON object out of the page.
            match = re.search(r"\{.*\}", html, re.DOTALL)
            if not match:
                return []
            try:
                payload = json.loads(match.group(0))
                data = payload.get("data", payload)
            except Exception:
                return []

        # Normalise: API may return ``data`` as a list or wrap a list
        # under ``data.items``.
        if isinstance(data, dict) and "items" in data:
            items = data.get("items", [])
        elif isinstance(data, list):
            items = data
        else:
            items = []

        results: list[dict[str, Any]] = []
        for raw in items:
            attrs = raw.get("attributes", raw)  # JSON:API vs raw dict
            title = (attrs.get("title") or attrs.get("name") or "").strip()
            if not title or len(title) < 4:
                continue
            results.append({
                "title": title,
                "company": (
                    attrs.get("school")
                    or attrs.get("organization")
                    or attrs.get("employer")
                    or ""
                ),
                "location": (
                    attrs.get("location")
                    or attrs.get("city")
                    or attrs.get("country")
                    or ""
                ),
                "url": (
                    attrs.get("url")
                    or self._build_url(attrs.get("id", raw.get("id")))
                ),
                "source": self.PUBLIC_SOURCE,
            })
        return results

    def _build_url(self, job_id: Any) -> str:
        if not job_id:
            return f"{self.BASE_URL}/jobs"
        return f"{self.BASE_URL}/job-gateway/{job_id}"

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _credentials_configured() -> bool:
        return bool(settings.th_email) and bool(settings.th_password)


__all__ = ["TeacherHorizonsScraper"]
