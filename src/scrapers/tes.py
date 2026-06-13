import json
import re
from urllib.parse import quote

from src.scrapers.base import BaseScraper


class TESScraper(BaseScraper):
    SOURCE_NAME = "tes"
    BASE_URL = "https://www.tes.com"

    def scrape(self, search_terms: list[str]) -> list[dict]:
        all_jobs = []
        seen_urls = set()

        for term in search_terms:
            for page in range(1, 6):
                path = f"/jobs/search?keywords={quote(term)}&location=International&page={page}"
                soup = self.fetch(path)
                jobs = self._extract_from_json(soup)

                for j in jobs:
                    url = j.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    j["source"] = "tes"
                    all_jobs.append(j)

                if len(jobs) < 20:
                    break

        return all_jobs

    def _extract_from_json(self, soup) -> list[dict]:
        """Extract job listings from Next.js JSON payload."""
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return self._extract_from_html(soup)

        try:
            data = json.loads(script.string)
            # Navigate to the jobs array in TRPC state
            queries = (
                data.get("props", {})
                .get("pageProps", {})
                .get("trpcState", {})
                .get("json", {})
                .get("queries", [])
            )
            for q in queries:
                state = q.get("state", {})
                jobs_data = state.get("data", {}).get("jobs", [])
                if jobs_data:
                    return [self._parse_job(j) for j in jobs_data]
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            pass

        return self._extract_from_html(soup)

    def _extract_from_html(self, soup) -> list[dict]:
        """Fallback: extract from rendered HTML."""
        cards = soup.select(
            '[data-testid="job-card"], '
            "[class*='job-card'], "
            "[class*='vacancy'], "
            "article"
        )
        results = []
        for card in cards:
            title_el = card.select_one(
                "h2, h3, [data-testid='job-title'], a"
            )
            link_el = card.select_one("a[href]")
            url = self.extract_attr(link_el, "href") or ""

            if not url:
                continue

            results.append({
                "title": self.extract_text(title_el),
                "url": self.absolute_url(url),
                "school": "",
                "location": "",
                "salary_range": "",
                "closing_date": "",
                "country": "",
                "subject": ["Physics"],
                "curriculum": [],
            })
        return results

    def _parse_job(self, raw: dict) -> dict:
        title = raw.get("title", "")
        location = raw.get("displayLocation", "") or raw.get("address", "") or ""

        employer = raw.get("employer") or {}
        school = employer.get("name", "") if isinstance(employer, dict) else str(employer)

        salary_obj = raw.get("salary") or {}
        salary = salary_obj.get("range", "") if isinstance(salary_obj, dict) else str(salary_obj)
        if not salary:
            salary = raw.get("displaySalary", "")

        closing = raw.get("closingDate") or raw.get("applicationDeadline") or ""

        url = raw.get("canonicalUrl", "") or f"/jobs/vacancy/{raw.get('id', '')}"
        if url.startswith("/"):
            url = f"https://www.tes.com{url}"

        subject_list = ["Physics"]
        if "science" in title.lower():
            subject_list.append("Science")

        return {
            "title": title,
            "url": url,
            "school": school,
            "location": location,
            "country": location.split(",")[-1].strip() if "," in location else location,
            "salary_range": str(salary) if salary else "",
            "closing_date": str(closing),
            "subject": subject_list,
            "curriculum": self._infer_curriculum(title, school),
        }

    @staticmethod
    def _infer_curriculum(title: str, school: str) -> list[str]:
        text = f"{title} {school}".lower()
        curricula = []
        if "igcse" in text:
            curricula.append("IGCSE")
        if "a-level" in text or "a level" in text:
            curricula.append("A-Level")
        if re.search(r'\bib\b', text) or "international baccalaureate" in text:
            curricula.append("IB")
        if re.search(r'\bgcse\b', text) and "igcse" not in text:
            curricula.append("GCSE")
        return curricula or ["IGCSE", "A-Level"]
