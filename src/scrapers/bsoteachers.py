import logging

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class BSOTeachersScraper(BaseScraper):
    SOURCE_NAME = "bsoteachers"
    BASE_URL = "https://www.bsoteachers.com"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict]:
        all_jobs = []
        seen_urls: set[str] = set()

        for page_num in range(1, 4):
            path = f"/jobs.aspx?page={page_num}" if page_num > 1 else "/jobs.aspx"
            soup = self.fetch(path)
            jobs = self._extract_jobs(soup)

            if not jobs:
                log.warning(
                    "[bsoteachers] 0 job cards on page %s — possible Firefish DOM drift",
                    page_num,
                )

            for j in jobs:
                url = j.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                j["source"] = "bsoteachers"
                all_jobs.append(j)

        return all_jobs

    def _extract_jobs(self, soup) -> list[dict]:
        results = []
        cards = soup.select("div.job-result-item")

        for card in cards:
            title_el = card.select_one("div.job-title a.card__title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = self.extract_attr(title_el, "href")

            if not title or not url:
                continue

            location = self.extract_text(card.select_one("li.results-job-location"))

            results.append({
                "title": title,
                "url": self.absolute_url(url),
                "school": "",
                "location": location,
                "country": self._extract_country(location),
                "salary_range": "",
                "closing_date": "",
                "subject": self._subject_tags(title),
                "curriculum": [],
                "job_type": "",
                "category": "",
                "easy_apply": False,
            })

        return results

    @staticmethod
    def _extract_country(location: str) -> str:
        if not location:
            return ""
        # "UAE - Abu Dhabi" / "Middle East, UAE - Abu Dhabi" style strings:
        # the last segment is a city, not a country.
        if any(part.strip().startswith("UAE") for part in location.split(",")):
            return "UAE"
        # "Europe, Poland" / "Middle East, Doha, Qatar" / "North Africa, Egypt":
        # the last comma segment is the country.
        return location.rsplit(",", 1)[-1].strip()

    @staticmethod
    def _subject_tags(title: str) -> list[str]:
        # Conservative literal-word tagging — same convention as libyan_jobs:
        # never pre-stamp a subject unless the literal word is in the title.
        subject_list: list[str] = []
        title_lower = title.lower()
        if "physics" in title_lower:
            subject_list.append("Physics")
        elif "science" in title_lower.split():
            subject_list.append("Science")
        elif "biology" in title_lower.split():
            subject_list.append("Biology")
        elif "math" in title_lower.split() or "mathematics" in title_lower.split() \
                or "maths" in title_lower.split():
            subject_list.append("Mathematics")
        return subject_list
