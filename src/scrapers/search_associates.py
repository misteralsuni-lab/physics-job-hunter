import logging
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class SearchAssociatesScraper(BaseScraper):
    SOURCE_NAME = "search_associates"

    def scrape(self, search_terms: list[str]) -> list[dict[str, Any]]:
        log.warning("Search Associates scraper is not yet implemented — returning no jobs.")
        return []
