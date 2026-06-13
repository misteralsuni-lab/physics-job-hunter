from urllib.parse import quote
from src.scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    SOURCE_NAME = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    def scrape(self, search_terms: list[str]) -> list[dict]:
        """
        LinkedIn requires a logged-in session and renders jobs via JavaScript.
        This scraper is limited without a browser automation tool.
        Returns an empty list as a placeholder.
        """
        return []
