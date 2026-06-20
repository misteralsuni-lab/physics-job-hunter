import logging
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class SchroleScraper(BaseScraper):
    SOURCE_NAME = "schrole"

    def scrape(self, search_terms: list[str]) -> list[dict[str, Any]]:
        log.warning("Schrole scraper is not yet implemented — returning no jobs.")
        return []
