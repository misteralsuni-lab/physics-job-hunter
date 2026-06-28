"""
GulfTalent.com scraper.

Source: https://www.gulftalent.com/  — corporate Gulf employment job board
covering the UAE, Saudi Arabia, Qatar, Bahrain, Oman, Kuwait and Lebanon.

Reconnaissance (2026-06-27)
---------------------------
The site's primary listings endpoint is a **public JSON API**:

    GET https://www.gulftalent.com/api/jobs/search?keywords=...&page=...

The endpoint requires no authentication, returns ``application/json``, and
shapes each result with a rich payload: ``id``, ``link``, ``title``,
``reference``, ``posted_date``, ``location`` (with ``location_parts``),
``job_category`` (slug + cat_name_short), ``company_name`` (``"confidential"``
when anonymous), ``industry_name_short``, ``employment_type``, salary range
when public, ``is_remote``, ``is_exclusive``, etc.  Default page size is 5.

Scope reality
-------------
The site's taxonomy is corporate Gulf employment — there is no standalone
``education`` / ``teaching`` category.  However, **searching with combined
subject + curriculum phrases (e.g. ``physics teacher igcse``) over the
GCC country mask (``10111111000000`` — UAE / Saudi / Qatar / Bahrain /
Oman / Kuwait) does return real teaching gigs**.  Probing on 2026-06-28
showed ``search_keyword=physics Teacher  igcse `` + GCC mask returned
17 roles with titles like "Primary Teacher / Homeroom Teacher" — the
exact IGCSE secondary set is sparse but bona-fide.

API param shape (confirmed 2026-06-28): ``search_keyword`` (was named
``keywords`` in v1), ``country`` bitmask, ``page``.  Each job record
carries ``link`` already in the form ``/uae/jobs/<slug>-<id>`` so the
detail-page URL is one URL prepend away.

Class choice
------------
Because the API is plain JSON over HTTPS, we inherit ``BaseScraper``
(``httpx`` + a quick ``json.loads``).  ``StealthBrowserScraper`` is not
needed and would only add cost.

Fallback / safety
-----------------
* HTTP error → log warning, return ``[]``.
* Empty `positions` array → return ``[]`` cleanly.
* Page-size: we pull up to ``MAX_PAGES`` (default ``10``, ~50 records)
  per query, dominated by the keyword-driven search; cheap.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


_SEARCH_PATH = "/api/jobs/search"
_DEFAULT_PAGE_SIZE = 5
_MAX_PAGES = 10

# Gulf Cooperation Council country mask — confirmed via probe of
# https://www.gulftalent.com/jobs/search?country=10111111000000 on 2026-06-28.
# The 6 contiguous bits match the 6 GCC countries (UAE / Saudi / Qatar /
# Bahrain / Oman / Kuwait).  Overridable via the ``GT_COUNTRY_MASK`` env
# var (set to empty string for unfiltered global search).  Pin a single
# mask at scraper-construction time rather than per call so probe behaviour
# is reproducible.
import os as _os
_GCC_MASK = _os.environ.get("GT_COUNTRY_MASK") or "10111111000000"


class GulfTalentScraper(BaseScraper):
    SOURCE_NAME = "gulftalent"
    BASE_URL = "https://www.gulftalent.com"

    # Targeted keyword set — keeps the query narrow and HTTP-cheap.  Each
    # entry is the *search_keyword* parameter to ``/api/jobs/search``;
    # combined subject + curriculum phrases work best against the loose
    # full-text matcher (e.g. ``physics teacher igcse``).  Add broader
    # terms only if the operator believes Gulf corporate L&D / trainer
    # roles are worth surfacing.
    KEYWORDS: tuple[str, ...] = (
        "physics teacher IGCSE",
        "physics teacher A-Level",
        "maths teacher IGCSE",
        "secondary physics",
        "IGCSE physics",
        "A-Level physics",
    )

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        # Use the operator-supplied terms if non-empty, otherwise fall
        # back to our narrow physics/maths keyword set.
        queries = list(search_terms) if search_terms else list(self.KEYWORDS)
        if not queries:
            return []

        for term in queries:
            try:
                positions = self._fetch_all_positions(term)
            except Exception as exc:
                log.warning(
                    "[gulftalent] query %r failed: %s", term, exc,
                )
                continue

            log.info("  gulftalent term=%r  → %d positions", term, len(positions))

            for p in positions:
                pid = p.get("id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                job = self._shape_job(p)
                if job is not None:
                    all_jobs.append(job)

        return all_jobs

    # ------------------------------------------------------------------
    #  HTTP layer
    # ------------------------------------------------------------------

    def _fetch_all_positions(self, keyword: str) -> list[dict[str, Any]]:
        """Paginate the JSON search endpoint for one keyword.

        The endpoint accepts ``search_keyword``, ``country`` (bitmask),
        ``page`` and indicates ``total_results`` in the envelope.  We
        pull up to ``MAX_PAGES`` pages — a hard cap prevents the request
        count from blowing up on popular terms.
        """
        aggregated: list[dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            params = {
                "search_keyword": keyword,
                "country": _GCC_MASK,
                "page": page,
            }
            response = self.client.get(_SEARCH_PATH, params=params)
            response.raise_for_status()
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                log.warning(
                    "[gulftalent] non-JSON payload for %s page %d: %s",
                    keyword, page, exc,
                )
                break

            positions = (
                payload.get("positions", []) if isinstance(payload, dict) else []
            )
            if not positions:
                break
            aggregated.extend(positions)

            total = payload.get("total_results") if isinstance(payload, dict) else None
            # Stop early once we've captured everything the site knows about.
            if total is not None and len(aggregated) >= total:
                break

        return aggregated

    # ------------------------------------------------------------------
    #  Schema mapping  →  pipeline contract
    # ------------------------------------------------------------------

    @staticmethod
    def _shape_job(record: dict[str, Any]) -> dict[str, Any] | None:
        """Map a GulfTalent ``positions[].`` record to the pipeline schema.

        The pipeline filter keys on ``title`` and ``subject``; the latter
        is set to ``["Physics"]`` only when the title literally contains
        that word, so the heuristic filter stays the source of truth.
        ``curriculum`` and ``subject`` default to ``[]`` per the
        strict project-wide convention.
        """
        title = (record.get("title") or "").strip()
        if not title or len(title) < 4:
            return None

        link = record.get("link") or ""
        if link and not link.startswith("http"):
            link = f"https://www.gulftalent.com{link}"

        location_parts = record.get("location_parts") or {}
        country = (
            location_parts.get("country_name")
            or record.get("location")
            or ""
        )
        city = location_parts.get("city_name") or ""
        location = (
            ", ".join([p for p in (city, country) if p]) or record.get("location", "")
        )

        job_category = record.get("job_category") or {}
        industry = (
            record.get("industry_name_short")
            or job_category.get("cat_name_short")
            or ""
        )

        company = (record.get("company_name") or "").strip() or "Confidential"

        min_salary = record.get("minSalary")
        max_salary = record.get("maxSalary")
        currency = record.get("salaryCurrency") or ""
        salary_range = ""
        if min_salary or max_salary:
            def _fmt(v: Any) -> str:
                return (
                    f"{int(v):,}"
                    if isinstance(v, (int, float)) else ""
                )
            salary_range = "–".join(
                filter(None, [_fmt(min_salary), _fmt(max_salary)])
            )
            if currency:
                salary_range = (salary_range + " " + currency).strip()

        posted = record.get("posted_date")  # ISO timestamp e.g. 2026-04-18T...
        employment = record.get("employment_type") or ""
        is_remote = record.get("is_remote") is True

        # Subject tag: only when the title literally mentions physics,
        # otherwise leave [] so the heuristic filter (not the scraper)
        # decides whether the row survives.  Curriculum is always []
        # — GulfTalent does not advertise an exam board.
        lower_title = title.lower()
        subject = ["Physics"] if "physics" in lower_title else []

        return {
            "title": title,
            "url": link,
            "school": company,
            "location": location,
            "country": country,
            "salary_range": salary_range,
            "closing_date": None,
            "subject": subject,
            "curriculum": [],
            "curriculum_board": None,
            "job_type": employment + (" (remote)" if is_remote else ""),
            "industry": industry,
            "provider": GulfTalentScraper.SOURCE_NAME,
            "posted_date": posted,
        }


__all__ = ["GulfTalentScraper"]
