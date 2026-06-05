import logging
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class SearchAssociatesScraper(BaseScraper):
    SOURCE_NAME = "search_associates"

    def scrape(self, search_terms: list[str]) -> list[dict[str, Any]]:
        log.warning(
            "Search Associates requires login credentials. "
            "Set SEARCH_ASSOCIATES_EMAIL and SEARCH_ASSOCIATES_PASSWORD in .env to enable."
        )
        return []
