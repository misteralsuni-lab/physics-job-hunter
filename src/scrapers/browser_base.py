"""
Stealth browser base class for scrapers that must clear Cloudflare Turnstile
and other JS-driven bot challenges.

Built on top of ``camoufox`` — a hardened Firefox fork with anti-fingerprint
measures — driven through the ``playwright``-shaped sync API.  Each instance
spawns one stealth browser context, navigates pages, and tears down cleanly
even on exceptions.  Cookie persistence is wired so a future Search Associates
adapter can re-use sessions between runs without re-authenticating.

Configuration:
    ``CAMOUFOX_ENABLED`` env var (default ``0``).  Set to ``1`` to enable
    the stealth browser after the binary has been provisioned.
    ``StealthBrowserScraper`` to short-circuit ``get_page_source()`` returning
    ``None`` — useful in CI where the binary is absent.
    ``CAMOUFOX_GEOIP`` env var (e.g. ``"GB"``) to anchor geoip lookups to
    a stable locale, avoiding timezone / locale flip flops between scrapes.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from src.config import settings
from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)

try:
    from camoufox.sync_api import Camoufox
    from browserforge.fingerprints import Screen
    CAMOUFOX_AVAILABLE = True
except Exception:  # pragma: no cover — binary missing or build broken
    CAMOUFOX_AVAILABLE = False
    Camoufox = None  # type: ignore[assignment]
    Screen = None  # type: ignore[assignment]


class StealthBrowserScraper(BaseScraper):
    """Abstract base class for scrapers needing real browser rendering.

    Subclasses implement ``scrape()`` and call ``self.get_page_source(url)``
    to fetchfully-rendered HTML.  Helper methods encapsulate humanised
    behaviour-nudges (mouse wag, short random waits) that materially help
    Cloudflare's bot classifier return a ``200`` instead of a Turnstile
    interstitial.
    """

    DEFAULT_VIEWPORTS: tuple[tuple[int, int], ...] = (
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1920, 1080),
    )

    # ----- subclass-overridable knobs -----------------------------------
    headless: bool = True
    humanise: float | bool = True  # Camoufox humanise: 1.0 = full
    page_load_timeout_ms: int = 45000
    wait_after_load_ms: int = 4500    # long enough for Turnstile JS to settle
    cookies_path: Path | None = None  # override per subclass

    # ------------------------------------------------------------------
    #  Construction / lifecycle
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        # Initialise the parent BaseScraper (its underlying httpx client is
        # ignored by callers that exclusively use get_page_source()).
        super().__init__()
        self._camoufox: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._cookies_path: Path | None = self._resolve_cookies_path()

    def _resolve_cookies_path(self) -> Path | None:
        if self.cookies_path is not None:
            return Path(self.cookies_path)
        # Default per-class cookie jar under XDG_CACHE_HOME or tempdir.
        base = Path(
            os.environ.get("XDG_CACHE_HOME")
            or os.environ.get("CAMOUFOX_COOKIE_DIR")
            or tempfile.gettempdir()
        )
        return base / f"camoufox_{self.SOURCE_NAME or 'scraper'}_cookies.json"

    # ------------------------------------------------------------------
    #  Public rendering API
    # ------------------------------------------------------------------

    def get_page_source(
        self,
        url: str,
        wait_for_selector: str | None = None,
        timeout_ms: int | None = None,
    ) -> str | None:
        """Navigate *url*, optionally wait for a CSS selector, return the
        fully-rendered HTML.  Returns ``None`` on any failure so callers
        degrade gracefully (we never raise into the pipeline).
        """
        # Kill-switch first — must short-circuit BEFORE any Camoufox Python
        # import-chain is touched, otherwise missing-binary auto-fetch may
        # trigger inside the engine.
        if not settings.camoufox_enabled:
            log.info(
                "[%s] dormant mode (camoufox_enabled=False) — skipping stealth fetch.",
                self.SOURCE_NAME,
            )
            return None

        if not CAMOUFOX_AVAILABLE:
            log.warning(
                "[%s] camoufox module is missing. "
                "Install with: pip install 'camoufox[geoip]' && python -m camoufox fetch",
                self.SOURCE_NAME,
            )
            return None

        try:
            with self._browser_session() as (camoufox, browser):
                self._camoufox = camoufox
                self._browser = browser
                return self._render(url, wait_for_selector, timeout_ms)
        except Exception as exc:  # pragma: no cover — defensive
            log.warning(
                "[%s] get_page_source(%s) failed: %s\n%s",
                self.SOURCE_NAME, url, exc, traceback.format_exc(limit=1),
            )
            return None

    # ------------------------------------------------------------------
    #  Browser session context manager
    # ------------------------------------------------------------------

    @contextmanager
    def _browser_session(self) -> Generator[tuple[Any, Any], None, None]:
        """Open a Camoufox context; enforce deterministic cleanup on exit."""
        camoufox_obj = None
        browser = None
        try:
            camoufox_obj = Camoufox(
                headless=self.headless,
                humanize=self.humanise,
                geoip=os.environ.get("CAMOUFOX_GEOIP", True),
                enable_cache=False,
            )
            browser = camoufox_obj.__enter__()
            yield camoufox_obj, browser
        finally:
            if camoufox_obj is not None:
                try:
                    camoufox_obj.__exit__(None, None, None)
                except Exception as exc:  # pragma: no cover — defensive
                    log.debug("[%s] browser teardown warning: %s",
                              self.SOURCE_NAME, exc)
            self._camoufox = None
            self._browser = None
            self._context = None

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    def _pick_screen(self) -> Screen | None:
        """Return a screen constraint from DEFAULT_VIEWPORTS keyed by SOURCE_NAME so
        each scraper gets a stable-but-different appearance."""
        if not self.SOURCE_NAME:
            w, h = self.DEFAULT_VIEWPORTS[0]
        else:
            idx = sum(ord(c) for c in self.SOURCE_NAME) % len(self.DEFAULT_VIEWPORTS)
            w, h = self.DEFAULT_VIEWPORTS[idx]
        return Screen(min_width=w, max_width=w, min_height=h, max_height=h)

    def _render(
        self,
        url: str,
        wait_for_selector: str | None,
        timeout_ms: int | None,
    ) -> str | None:
        """Open the page in the camoufox browser and return its HTML.

        We default to a human-perceived strategy:
          1. Visit with a generous timeout.
          2. After load, sleep a few seconds so Turnstile / hCaptcha JS
             callbacks complete and the page transitions out of the
             challenge.
          3. Optionally wait for a CSS selector to confirm the content
             we actually want is present (defence against false-positive
             "200 OK" pages that are still a challenge interstitial)."""
        if self._browser is None:
            return None

        ctx = self._browser.new_context()
        try:
            page = ctx.new_page()
            try:
                page.set_default_timeout(timeout_ms or self.page_load_timeout_ms)
                page.goto(url, wait_until="domcontentloaded")

                # Let Turnstile callbacks finish before asserting content.
                page.wait_for_timeout(self.wait_after_load_ms)

                if wait_for_selector:
                    try:
                        page.wait_for_selector(
                            wait_for_selector,
                            timeout=timeout_ms or self.page_load_timeout_ms,
                        )
                    except Exception as exc:
                        log.warning(
                            "[%s] selector %r not found on %s: %s",
                            self.SOURCE_NAME, wait_for_selector, url, exc,
                        )
                        return page.content()

                return page.content()
            finally:
                page.close()
        finally:
            ctx.close()

    # ------------------------------------------------------------------
    #  Cookie persistence (foundation for Search Associates later)
    # ------------------------------------------------------------------

    def save_cookies(self, browser_context: Any) -> None:
        if self._cookies_path is None:
            return
        try:
            cookies = browser_context.cookies()
            self._cookies_path.parent.mkdir(parents=True, exist_ok=True)
            self._cookies_path.write_text(json.dumps(cookies, indent=2))
            log.info("[%s] saved %d cookies -> %s",
                     self.SOURCE_NAME, len(cookies), self._cookies_path)
        except Exception as exc:
            log.warning("[%s] save_cookies failed: %s",
                        self.SOURCE_NAME, exc)

    def load_cookies(self, browser_context: Any) -> bool:
        """Restore cookies from disk onto *browser_context*.  Returns True if
        any cookies were applied.  Used by Search Associates to skip the
        multi-step authenticated start flow on subsequent runs."""
        if self._cookies_path is None or not self._cookies_path.exists():
            return False
        try:
            cookies = json.loads(self._cookies_path.read_text())
            browser_context.add_cookies(cookies)
            log.info("[%s] restored %d cookies from %s",
                     self.SOURCE_NAME, len(cookies), self._cookies_path)
            return bool(cookies)
        except Exception as exc:
            log.warning("[%s] load_cookies failed: %s",
                        self.SOURCE_NAME, exc)
            return False


__all__ = ["StealthBrowserScraper", "CAMOUFOX_AVAILABLE"]
