import logging
import os
import time
from typing import Any

from playwright.sync_api import sync_playwright

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class TeacherHorizonsScraper(BaseScraper):
    SOURCE_NAME = "teacher_horizons"
    BASE_URL = "https://www.teacherhorizons.com"

    def __init__(self):
        super().__init__()
        self._headless = not os.environ.get("TH_DEBUG")

    def scrape(self, search_terms: list[str]) -> list[dict[str, Any]]:
        """Scrape job listings from Teacher Horizons Angular SPA via Playwright."""

        subject_map = {
            "Physics": "Physics",
            "Science": "Science",
            "IGCSE Physics": "Physics",
            "A-Level Physics": "Physics",
            "IB Physics": "Physics",
        }

        seen_urls: set[str] = set()
        all_jobs: list[dict[str, Any]] = []

        os.environ.setdefault(
            "PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", "ubuntu24.04-x64"
        )
        os.environ.setdefault(
            "LD_LIBRARY_PATH",
            os.path.expanduser("~/.cache/ms-playwright/chromium-1217/chrome-linux64"),
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self._headless,
                timeout=20000,
            )
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            try:
                for term in search_terms:
                    subject = subject_map.get(term, "Physics")
                    url = f"{self.BASE_URL}/jobs?subjects={subject}"
                    log.info("Fetching %s (subject=%s)", url, subject)

                    page.goto(url, wait_until="networkidle", timeout=60000)
                    time.sleep(3)

                    job_links = page.query_selector_all("h3 a")
                    if not job_links:
                        log.info("  No jobs found for %s", term)
                        continue

                    log.info("  Found %d job links", len(job_links))

                    for link in job_links:
                        try:
                            title = link.inner_text().strip()
                            if not title:
                                continue

                            href = link.get_attribute("href") or ""
                            job_id = href.rsplit("/", 1)[-1] if "/" in href else ""
                            job_url = f"{self.BASE_URL}/job-gateway/{job_id}"

                            if not job_url or job_url in seen_urls:
                                continue
                            seen_urls.add(job_url)

                            card = link.evaluate_handle(
                                "el => el.closest('[class*=\"ng-star-inserted\"]')"
                            )
                            card_el = card.as_element()
                            if not card_el:
                                continue

                            full_text = card_el.inner_text() or ""

                            location = ""
                            country = ""
                            salary_range = ""
                            closing_date = ""
                            curriculum: list[str] = []

                            parts = full_text.split("\n")

                            for i, part in enumerate(parts):
                                part = part.strip()
                                if not part:
                                    continue
                                if (
                                    "," in part
                                    and not any(
                                        kw in part.lower()
                                        for kw in [
                                            "start",
                                            "apply",
                                            "hour",
                                            "day",
                                            "week",
                                            "month",
                                            "year",
                                            "ago",
                                        ]
                                    )
                                    and "learn" not in part.lower()
                                ):
                                    location = part
                                    segments = [s.strip() for s in part.split(",")]
                                    country = segments[-2] if len(segments) >= 2 else segments[-1]

                                if part.lower().startswith("apply before"):
                                    closing_date = part.split(":", 1)[-1].strip()

                            subject_list = ["Physics"]
                            if "science" in title.lower():
                                subject_list.append("Science")

                            curriculum = self._infer_curriculum(title, location)

                            all_jobs.append(
                                {
                                    "title": title,
                                    "url": job_url,
                                    "school": "",
                                    "location": location,
                                    "country": country,
                                    "salary_range": salary_range,
                                    "closing_date": closing_date,
                                    "subject": subject_list,
                                    "curriculum": curriculum,
                                    "source": self.SOURCE_NAME,
                                }
                            )

                        except Exception as e:
                            log.error("  Failed to parse job card: %s", e)
                            continue

            except Exception as e:
                log.error("Teacher Horizons scrape failed: %s", e)
            finally:
                browser.close()

        log.info("%s: %d jobs extracted", self.SOURCE_NAME, len(all_jobs))
        return all_jobs

    @staticmethod
    def _infer_curriculum(title: str, text: str) -> list[str]:
        combined = f"{title} {text}".lower()
        curricula = []
        if "igcse" in combined:
            curricula.append("IGCSE")
        if "a-level" in combined or "a level" in combined:
            curricula.append("A-Level")
        if "ib" in combined or "international baccalaureate" in combined:
            curricula.append("IB")
        if "gcse" in combined:
            curricula.append("GCSE")
        return curricula or ["IGCSE", "A-Level"]
