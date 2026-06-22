from src.scrapers.base import BaseScraper


class LibyanJobsScraper(BaseScraper):
    SOURCE_NAME = "libyanjobs"
    BASE_URL = "https://libyanjobs.ly"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict]:
        all_jobs = []
        seen_urls: set[str] = set()

        for page_num in range(1, 4):
            path = f"/jobs/page/{page_num}/" if page_num > 1 else "/jobs/"
            soup = self.fetch(path)
            jobs = self._extract_jobs(soup)

            for j in jobs:
                url = j.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                j["source"] = "libyanjobs"
                all_jobs.append(j)

        return all_jobs

    def _extract_jobs(self, soup) -> list[dict]:
        results = []
        articles = soup.select("article.loadmore-item.noo_job")

        for article in articles:
            title_el = article.select_one("h3 a, h2 a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = self.extract_attr(title_el, "href")

            if not title or not url:
                continue

            company = self.extract_text(article.select_one("span.job-company"))
            location = self.extract_text(article.select_one("span.job-location"))
            job_type = self.extract_text(article.select_one("span.job-type"))
            closing = self.extract_text(article.select_one("span.job-date__closing"))
            category = self.extract_text(article.select_one("span.job-category"))

            subject_list: list[str] = []
            title_lower = title.lower()
            if any(kw in title_lower for kw in ["teacher", "teaching", "instructor", "physics", "biology", "science", "math", "english", "academic", "faculty", "professor", "lecturer", "education"]):
                subject_list = ["Education"]
            if any(kw in title_lower for kw in ["physics", "science", "biology"]):
                subject_list = ["Physics", "Science"]

            results.append({
                "title": title,
                "url": self.absolute_url(url),
                "school": company,
                "location": location,
                "country": "Libya",
                "salary_range": "",
                "closing_date": closing,
                "subject": subject_list,
                "curriculum": [],
                "job_type": job_type,
                "category": category,
                "easy_apply": False,
            })

        return results
