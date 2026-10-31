"""
LinkedIn scraper with stealth fingerprinting.

Uses ``curl-impersonate`` (via ``curl_cffi``) to avoid trivial bot detection.
If ``curl_cffi`` is not installed the scraper degrades to an empty-list
placeholder and logs a warning.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)

_PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "profile.json"
_POLITE_DELAY = 1.0


def _target_countries() -> list[str]:
    """Countries from the operator profile, used for location-scoped searches."""
    try:
        data = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
        return [str(c).strip() for c in data.get("target_countries", []) if str(c).strip()]
    except (OSError, ValueError):
        return []


# LinkedIn emits full country names; the scorer's country bonus (and the
# profile's target_countries) use short canonical forms.  Without this,
# "United Arab Emirates" never matched "UAE", so a target-country LinkedIn
# role lost the 25-point location credit in the rule-based fallback and its
# signature differed from the same vacancy on TES.
_COUNTRY_ALIASES = {
    "united arab emirates": "UAE",
    "uae": "UAE",
    "u.a.e.": "UAE",
    "ksa": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "bahrain": "Bahrain",
    "kuwait": "Kuwait",
    "oman": "Oman",
    "hong kong": "Hong Kong",
    "hong kong sar": "Hong Kong",
    "vietnam": "Vietnam",
    "viet nam": "Vietnam",
    "japan": "Japan",
    "south korea": "South Korea",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "taiwan": "Taiwan",
    "indonesia": "Indonesia",
    "czechia": "Czechia",
    "czech republic": "Czechia",
    "austria": "Austria",
    "hungary": "Hungary",
    "slovakia": "Slovakia",
    "slovak republic": "Slovakia",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "usa": "United States",
    "u.s.a.": "United States",
    "united states of america": "United States",
    "türkiye": "Türkiye",
    "turkey": "Türkiye",
}

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False  # type: ignore[assignment]
    curl_requests = None  # type: ignore[assignment]


class LinkedInScraper(BaseScraper):
    SOURCE_NAME = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        if not CURL_CFFI_AVAILABLE:
            log.warning(
                "curl_cffi is not installed — LinkedIn scraper cannot run. "
                "Install with: pip install curl-cffi"
            )
            return []

        if search_terms is None:
            search_terms = ["Physics teacher", "IGCSE Physics", "A-Level Physics"]

        all_jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # Worldwide queries catch globally advertised international-school
        # roles, but LinkedIn's relevance ranking heavily favours the
        # operator's own region (India/US/Europe).  A location-scoped query
        # per target country surfaces the UAE/Qatar/Saudi/China roles that
        # the worldwide search buries — those are the ones that score into
        # the notification threshold.
        queries: list[tuple[str, str]] = [(term, "Worldwide") for term in search_terms]
        for country in _target_countries():
            queries.append(("Physics teacher", country))

        for index, (term, location) in enumerate(queries):
            jobs = self._fetch_linkedin_jobs(term, location=location)
            for j in jobs:
                url = j.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    j["source"] = "linkedin"
                    all_jobs.append(j)
            if index < len(queries) - 1:
                time.sleep(_POLITE_DELAY)

        return all_jobs

    def _fetch_linkedin_jobs(
        self, query: str, pages: int = 1, location: str = "Worldwide"
    ) -> list[dict[str, Any]]:
        """Search LinkedIn public job listings via curl-impersonate."""
        assert curl_requests is not None

        jobs: list[dict[str, Any]] = []
        start = 0
        for _ in range(pages):
            # Public search endpoint (no auth required)
            url = (
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={self._enc(query)}&location={self._enc(location)}&start={start}"
            )
            resp = None
            for attempt in range(1, 4):
                try:
                    candidate = curl_requests.get(  # type: ignore[arg-type]
                        url, impersonate="chrome120", timeout=30
                    )
                    candidate.raise_for_status()
                    resp = candidate
                    break
                except Exception as exc:
                    if attempt < 3:
                        wait = 2 * attempt
                        log.warning(
                            "LinkedIn request failed (attempt %d/3): %s — retrying in %ds",
                            attempt, exc, wait,
                        )
                        time.sleep(wait)
                    else:
                        log.warning("LinkedIn request failed after 3 attempts: %s", exc)

            if resp is None:
                break

            soup = self._soup_from_text(resp.text)  # type: ignore[arg-type]
            cards = soup.select("li") if soup else []

            for card in cards:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle a")
                meta_el = card.select_one("div.base-search-card__metadata")
                link_el = card.select_one("a.base-card__full-link")

                if not title_el or not link_el:
                    continue

                title = self.extract_text(title_el)
                company = self.extract_text(company_el) if company_el else ""

                # ``div.base-search-card__metadata`` also contains the posted
                # time and occasionally an "Actively Hiring" badge.  Reading
                # it wholesale produced countries such as
                # "Switzerland2 days ago" and "TXBe an early applicant",
                # which broke the country bonus, signature dedup and the
                # Telegram location line.  Prefer the dedicated location span.
                location_el = card.select_one("span.job-search-card__location")
                if location_el:
                    location = self.extract_text(location_el)
                elif meta_el:
                    location = self.extract_text(meta_el)
                    location = re.sub(
                        r"\s*(Actively Hiring|Be an early applicant|"
                        r"\d+\s+(day|week|month|year)s?\s+ago).*$",
                        "",
                        location,
                    ).strip()
                else:
                    location = ""

                raw_url = self.extract_attr(link_el, "href")

                # Normalise URL to the canonical public job page
                url = raw_url.split("?")[0] if raw_url else ""

                if not url:
                    continue

                # Curriculum inference
                curriculum = self._infer_curriculum(title)
                # Closing date — LinkedIn does not expose this on the search card;
                # we leave it None so upstream coercion handles it.
                closing_date = None

                country = location.split(",")[-1].strip() if "," in location else location
                country = _COUNTRY_ALIASES.get(country.lower(), country)

                jobs.append({
                    "title": title,
                    "url": url,
                    "school": company,
                    "location": location,
                    "country": country,
                    "salary_range": "",
                    "closing_date": closing_date,
                    # Subject: ONLY mark "Physics" when the title actually says so.
                    # Other subjects must NOT be tagged as "Physics" — filtering
                    # happens downstream against the strict subject requirement
                    # and a lying tag would let "Geography teacher" through.
                    "subject": ["Physics"] if "physics" in title.lower() else [],
                    "curriculum": curriculum,
                    "job_type": "",
                    "provider": "linkedin",
                })

            start += 25
            if len(cards) < 5:
                break

        return jobs

    @staticmethod
    def _enc(text: str) -> str:
        from urllib.parse import quote
        return quote(text)

    @staticmethod
    def _soup_from_text(text: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "lxml")

    @staticmethod
    def _infer_curriculum(title: str) -> list[str]:
        """Detect curriculum from the job title.

        IMPORTANT: returns an *empty* list when nothing matches; it must NOT
        default to a guess that misleads the downstream filter and LLM scorer
        (a UK Edexcel teacher and an American-curriculum teacher both get
        tagged with the same false "IGCSE, A-Level" otherwise).
        """
        t = title.lower()
        curricula: list[str] = []
        if "igcse" in t:
            curricula.append("IGCSE")
        if "a-level" in t or "a level" in t:
            curricula.append("A-Level")
        if "ib" in t:
            curricula.append("IB")
        if "gcse" in t and "igcse" not in t:
            curricula.append("GCSE")
        return curricula
