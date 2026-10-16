import logging
import re
import time
from abc import ABC, abstractmethod
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


FETCH_ATTEMPTS = 5
FETCH_BACKOFF = 2.0
FETCH_BACKOFF_CAP = 15.0


class BaseScraper(ABC):
    SOURCE_NAME: str = ""
    BASE_URL: str = ""
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self):
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers=self.HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def absolute_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return urljoin(self.BASE_URL, path)

    def fetch(self, path: str) -> BeautifulSoup:
        resp = self.client.get(path)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def fetch_with_retry(self, path: str, attempts: int = FETCH_ATTEMPTS):
        """``fetch`` with retries on transient network failures.

        Raises the last error if every attempt fails.  Catches only
        transport-level problems (timeouts, connection resets) — an HTTP
        error status still propagates immediately, since a 404 will not
        become a 200 on the fifth try.

        DNS failures (``socket.gaierror`` → ``httpx.ConnectError``, a
        ``TransportError``) are retried too: a measured ~30s resolver
        outage in WSL zeroed the TES scraper for a whole run because it
        used bare ``fetch``.  Backoff is exponential (2/4/8/15s) so the
        five attempts span ~30-50s including per-attempt timeouts.
        """
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self.fetch(path)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                if attempt < attempts:
                    wait = min(
                        FETCH_BACKOFF * (2 ** (attempt - 1)),
                        FETCH_BACKOFF_CAP,
                    )
                    log.warning(
                        "[%s] %s — transient fetch failure (%s), retrying in %.1fs",
                        self.SOURCE_NAME, path, e, wait,
                    )
                    time.sleep(wait)
        assert last is not None
        raise last

    def extract_text(self, element) -> str:
        if element is None:
            return ""
        return element.get_text(strip=True)

    def extract_attr(self, element, attr: str) -> str:
        if element is None:
            return ""
        return (element.get(attr) or "").strip()

    @abstractmethod
    def scrape(self, search_terms: list[str] | None = None) -> list[dict]:
        ...

    def run(self, search_terms: list[str] | None = None) -> list[dict]:
        if search_terms is None:
            search_terms = [
                "Physics",
                "IGCSE Physics", "A-Level Physics",
            ]
        return self.scrape(search_terms)
