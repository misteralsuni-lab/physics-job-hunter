from src.scrapers.base import BaseScraper


class LibyanJobsScraper(BaseScraper):
    SOURCE_NAME = "libyanjobs"
    BASE_URL = "https://libyanjobs.ly"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict]:
        all_jobs = []
        seen_urls: set[str] = set()

        for page_num in range(1, 4):
            path = f"/jobs/page/{page_num}/" if page_num > 1 else "/jobs/"
            soup = self.fetch_with_retry(path)
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

            # Subject tagging: never pre-stamp.  Both intermediate rules
            # used to list ``["Physics", "Science"]`` whenever the title
            # mentioned *any* keyword from a wide "teacher / academic"
            # bucket — that quietly classified every teacher-shaped job
            # as a Physics role, defeating the heuristic filter.  Now we
            # only tag when the **literal word** "physics" or "biology"
            # appears in the title.
            subject_list: list[str] = []
            title_lower = title.lower()
            if "physics" in title_lower:
                subject_list.append("Physics")
            elif "science" in title_lower.split():
                # Conservative: "Science Teacher" only counts when the
                # word stands alone (whole-token match), avoiding
                # "Physical Education" or "Earth Sciences" false positives.
                subject_list.append("Science")
            elif "biology" in title_lower.split():
                subject_list.append("Biology")
            elif "math" in title_lower.split():
                subject_list.append("Mathematics")

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
