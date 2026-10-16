import json
import re
from urllib.parse import quote

from src.scrapers.base import BaseScraper


# TES ``displayLocation`` is a free-form "Town, Region" / "City, Country"
# string.  The previous implementation took the last comma segment verbatim,
# which produced garbage for UK postings ("Bury, Greater Manchester" →
# country "Greater Manchester", "Weybridge, Surrey" → "Surrey", and one row
# where the trailing segment was a postcode, "BN27 3QH").  That single field
# feeds three consumers, so the damage was broad:
#   * ``job_signature()`` — a stable, wrong country makes cross-board dedup
#     miss real duplicates and collide unrelated ones.
#   * The LLM's Location/country rubric (0-25 of the 0-100 score).
#   * The country-match bonus in ``llm_scorer.py:_apply_modifiers``, which
#     compares against ``profile.json`` ``target_countries``.  Because that
#     list uses the short form "UAE" while TES emits "United Arab Emirates",
#     the bonus never fired for a single UAE posting.
#
# Resolution order: canonical alias → target country → UK shape → last
# segment.  Aliases mirror ``seekteachers.COUNTRY_ALIASES`` so the two boards
# converge on the same canonical strings.
COUNTRY_ALIASES = {
    "united arab emirates": "UAE",
    "uae": "UAE",
    "u.a.e.": "UAE",
    "ksa": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
}

# Counties / regions that TES puts in the trailing position for UK postings.
# Matched case-insensitively against the final comma segment.
_UK_REGIONS = frozenset({
    "berkshire", "buckinghamshire", "cambridgeshire", "cheshire", "cleveland",
    "cornwall", "county antrim", "county armagh", "county down", "county fermanagh",
    "county londonderry", "county tyrone", "cumbria", "derbyshire", "devon",
    "dorset", "dumfries and galloway", "durham", "east lothian", "east sussex",
    "essex", "fife", "gloucestershire", "greater manchester", "hampshire",
    "herefordshire", "hertfordshire", "highlands and islands", "humberside",
    "isle of wight", "kent", "lancashire", "leicestershire", "lincolnshire",
    "london", "merseyside", "midlands", "norfolk", "north yorkshire",
    "northamptonshire", "northumberland", "nottinghamshire", "oxfordshire",
    "perth and kinross", "powys", "ruthamptonshire", "s devon", "scotland",
    "shropshire", "somerset", "south gloucestershire", "south yorkshire",
    "staffordshire", "stirlingshire", "suffolk", "surrey", "tyne and wear",
    "wales", "warwickshire", "west midlands", "west sussex", "west yorkshire",
    "wiltshire", "worcestershire",
})

# Outward postcode pattern: A9 9AA / AA9 9AA / A99 9AA / AA99 9AA.
_UK_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.IGNORECASE)


class TESScraper(BaseScraper):
    SOURCE_NAME = "tes"
    BASE_URL = "https://www.tes.com"

    MAX_PAGES = 20

    def scrape(self, search_terms: list[str]) -> list[dict]:
        all_jobs = []
        seen_urls = set()

        for term in search_terms:
            prev_new = 0
            for page in range(1, self.MAX_PAGES + 1):
                path = f"/jobs/search?keywords={quote(term)}&location=International&page={page}"
                soup = self.fetch(path)
                jobs = self._extract_from_json(soup)

                new = 0
                for j in jobs:
                    url = j.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    j["source"] = "tes"
                    all_jobs.append(j)
                    new += 1

                # TES ignores the ``page`` parameter beyond the first page and
                # serves the identical 20-listing result set no matter how high
                # the page number goes.  The previous guard
                # (``len(jobs) < 20``) therefore never fired and the loop ran
                # all 5 pages regardless — 36 requests per run to re-fetch the
                # same listings.  Breaking on "this page yielded nothing new"
                # detects the repeat and stops after page 2, while still
                # handling a genuine second page of results if TES ever fixes
                # its pagination.
                if new == 0:
                    break
                # Diminishing returns: one thin page after a productive run
                # is the signature of the tail of a result set.
                if new <= 2 and prev_new > 0:
                    break
                prev_new = new

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
                # Subject: never pre-tag.  Only mark "Physics" when the
                # title literally contains the word; otherwise leave the
                # filter empty so the pipeline's hard-physics check rejects
                # the listing.  This was previously hardcoded
                # ``["Physics"]`` here which silently tagged every TES
                # listing as a physics role (incl. Biology, Geography,
                # etc.); the hard filter was then bypassed by the
                # scraper's lie.
                "subject": (
                    ["Physics"] if "physics" in (self.extract_text(title_el) or "").lower() else []
                ),
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

        # Subject: never pre-tag.  Only mark "Physics" when the
        # title literally contains the word "physics".  Hardcoding this
        # branch once created a silent false-positive chain — every TES
        # listing (Biology, Geography, TAs, etc.) was mis-stamped as
        # Physics to satisfy the heuristic filter, defeating the
        # project's hard-typesetting specialty-check guarantee.
        subject_list: list[str] = []
        if "physics" in title.lower():
            subject_list.append("Physics")
        # Surface "Science" only when the title says so verbatim — this
        # is conservative so we don't over-tag cross-discipline listings.
        if "science" in title.lower():
            subject_list.append("Science")

        return {
            "title": title,
            "url": url,
            "school": school,
            "location": location,
            "country": self._resolve_country(location),
            "salary_range": str(salary) if salary else "",
            "closing_date": str(closing),
            "subject": subject_list,
            "curriculum": self._infer_curriculum(title, school),
        }

    @classmethod
    def _resolve_country(cls, location: str) -> str:
        """Derive a canonical country from a TES ``displayLocation`` string.

        Returns "" when nothing usable can be derived, so downstream
        consumers see "unknown" rather than a confident wrong answer.
        """
        text = (location or "").strip()
        if not text:
            return ""

        last = text.split(",")[-1].strip()
        if not last:
            return ""

        # 1. Known alias — canonicalise ("United Arab Emirates" → "UAE").
        alias = COUNTRY_ALIASES.get(last.lower())
        if alias:
            return alias

        # 2. Whole-string alias (no comma in the field at all).
        alias = COUNTRY_ALIASES.get(text.lower())
        if alias:
            return alias

        # 3. Already a target country under any spelling.
        try:
            with open("data/profile.json") as f:
                targets = json.load(f).get("target_countries", [])
        except (OSError, json.JSONDecodeError):
            targets = []
        target_lookup = {t.lower(): t for t in targets}
        if last.lower() in target_lookup:
            return target_lookup[last.lower()]

        # 4. Any comma segment names a UK region, or the field carries a UK
        #    alias somewhere ("Bury, UK", "Sunbrae, West Sussex, UK").
        #    Scanned across all segments because TES is inconsistent about
        #    whether the country sits first or last.
        segments = [s.strip() for s in text.split(",") if s.strip()]
        for seg in segments:
            if COUNTRY_ALIASES.get(seg.lower()) == "United Kingdom" or seg.lower() in _UK_REGIONS:
                return "United Kingdom"

        # 5. A UK outward postcode in any segment.
        for seg in segments:
            if _UK_POSTCODE_RE.match(seg):
                return "United Kingdom"

        # 6. Fall back to the trailing segment unchanged.  It is the best
        #    available guess and preserves prior behaviour for locations
        #    that were already country-shaped.
        #
        #    Known residual gap: a UK posting whose location names only a
        #    town/district with no region, country or postcode ("Bromsgrove,
        #    Sunbrae", "Byfleet, Byfleet") still resolves to that town.  That
        #    is no worse than the previous behaviour, which also produced
        #    non-country strings, and it cannot be closed without shipping a
        #    UK gazetteer.  The signature it feeds is keyed on
        #    school|title|country, so an unresolved town still distinguishes
        #    schools correctly.
        return last

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
