import re
from abc import ABC, abstractmethod
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


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

    def absolute_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return urljoin(self.BASE_URL, path)

    def fetch(self, path: str) -> BeautifulSoup:
        resp = self.client.get(path)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def extract_text(self, element) -> str:
        if element is None:
            return ""
        return element.get_text(strip=True)

    def extract_attr(self, element, attr: str) -> str:
        if element is None:
            return ""
        return (element.get(attr) or "").strip()

    @abstractmethod
    def scrape(self, search_terms: list[str]) -> list[dict]:
        ...

    def run(self, search_terms: list[str] | None = None) -> list[dict]:
        if search_terms is None:
            search_terms = [
                "Physics",
                "IGCSE Physics", "A-Level Physics",
            ]
        return self.scrape(search_terms)
