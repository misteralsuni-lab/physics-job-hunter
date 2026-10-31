import json
import logging
import re
import time
from urllib.parse import urlencode

from src.config import settings
from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)

# Per-country ceiling.  Measured 2026-09-30: with `keyword=physics`, country 17
# exhausts at page 5, UAE at page 14, and the largest country was still
# returning 20 fresh listings per page at page 30 — so the previous cap of 10
# truncated every country short of its tail.
MAX_PAGES_PER_COUNTRY = 20

# Global ceiling across all countries.  With 25 target countries this allows
# roughly 10 pages per country on average; countries that exhaust early
# release their budget to the larger boards.  Kept as a runtime backstop.
MAX_PAGES_TOTAL = 240

POLITE_DELAY = 0.5

# SeekTeachers country names -> profile.json target_countries names.
COUNTRY_ALIASES = {
    "United Arab Emirates": "UAE",
    "UAE": "UAE",
    "Saudi Arabia": "Saudi Arabia",
    "KSA": "Saudi Arabia",
    "Bahrain": "Bahrain",
    "Kuwait": "Kuwait",
    "Oman": "Oman",
    "Hong Kong": "Hong Kong",
    "Vietnam": "Vietnam",
    "Japan": "Japan",
    "South Korea": "South Korea",
    "Korea": "South Korea",
    "Taiwan": "Taiwan",
    "Indonesia": "Indonesia",
    "Czech Republic": "Czechia",
    "Czechia": "Czechia",
    "Austria": "Austria",
    "Hungary": "Hungary",
    "Slovakia": "Slovakia",
    "Turkey": "Türkiye",
    "Türkiye": "Türkiye",
}

_COUNT_RE = re.compile(r"\((\d+)\)\s*$")


class SeekTeachersScraper(BaseScraper):
    SOURCE_NAME = "seekteachers"
    BASE_URL = "https://www.seekteachers.com"

    def __init__(self):
        super().__init__()
        self._target_countries = self._load_target_countries()

    def _load_target_countries(self) -> set[str]:
        try:
            with open("data/profile.json", encoding="utf-8") as f:
                profile = json.load(f)
            return {c.lower() for c in profile.get("target_countries", [])}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("[seekteachers] could not load profile target_countries: %s", e)
            return set()

    def scrape(self, search_terms: list[str] | None = None) -> list[dict]:
        countries = self._discover_countries()
        if not countries:
            log.warning("[seekteachers] country discovery yielded nothing — possible DOM drift")
            return []

        if settings.seek_countries == "all":
            selected = countries
            log.info("[seekteachers] SEEK_COUNTRIES=all — sweeping %d countries", len(countries))
        else:
            selected = {
                cid: name for cid, name in countries.items()
                if self._canonical_name(name).lower() in self._target_countries
            }
            log.info(
                "[seekteachers] %d/%d countries match target_countries: %s",
                len(selected), len(countries),
                ", ".join(sorted(selected.values())),
            )

        all_jobs = []
        seen_urls: set[str] = set()
        total_pages = 0
        pages_done: dict[str, int] = {cid: 0 for cid in selected}
        stopped_at: dict[str, str] = {}

        # Round-robin across countries rather than draining them one at a
        # time.  Under a global page budget the old sequential loop let the
        # first country consume the entire allowance, starving the rest —
        # discovery order put the largest board first, so every later country
        # got whatever was left over.  Interleaving guarantees every country
        # progresses in step, and countries that exhaust early (17 at page 5,
        # UAE at 14) hand their remaining budget straight back to the others.
        cursors = {cid: 1 for cid in selected}
        active = set(selected)

        while active and total_pages < MAX_PAGES_TOTAL:
            for country_id in sorted(active):
                if total_pages >= MAX_PAGES_TOTAL:
                    break
                page_num = cursors[country_id]

                params = {"keyword": "physics", "country_id": country_id}
                if page_num > 1:
                    params["page"] = page_num
                path = f"/jobs.asp?{urlencode(params)}"
                # A transient timeout must not abort the whole board — one
                # bad page used to raise out of scrape() and return zero
                # jobs for every country. Retry the page, then skip it and
                # carry on if it still fails.
                try:
                    soup = self.fetch_with_retry(path)
                except Exception as exc:
                    log.warning(
                        "[seekteachers] giving up on %s (%s) — skipping this page",
                        path, exc,
                    )
                    active.discard(country_id)
                    stopped_at[country_id] = f"page {page_num} failed: {type(exc).__name__}"
                    break
                total_pages += 1
                pages_done[country_id] += 1

                jobs = self._extract_jobs(soup, country_id, selected[country_id])
                if not jobs:
                    if page_num == 1:
                        # Only page 1 being empty is suspicious. Past page 1 an
                        # empty result is simply how the board ends — the
                        # previous run reported every country's normal
                        # exhaustion as "possible DOM drift".
                        log.warning(
                            "[seekteachers] 0 job cards on page 1 for %s — possible DOM drift",
                            selected[country_id],
                        )
                        stopped_at[country_id] = "no job cards on page 1 (DOM drift?)"
                    else:
                        stopped_at[country_id] = f"listing exhausted at page {page_num}"
                    active.discard(country_id)
                    continue

                new_on_page = 0
                for j in jobs:
                    url = j.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    j["source"] = "seekteachers"
                    all_jobs.append(j)
                    new_on_page += 1

                if new_on_page == 0:
                    stopped_at[country_id] = "listing exhausted"
                    active.discard(country_id)
                    continue

                cursors[country_id] = page_num + 1
                if page_num >= MAX_PAGES_PER_COUNTRY:
                    stopped_at[country_id] = f"hit {MAX_PAGES_PER_COUNTRY}-page cap, listings still coming"
                    active.discard(country_id)

                time.sleep(POLITE_DELAY)

        for country_id, name in sorted(selected.items(), key=lambda kv: kv[1]):
            log.info(
                "[seekteachers] %s: %d page(s) — %s",
                name, pages_done[country_id],
                stopped_at.get(country_id, "not reached"),
            )
        log.info(
            "[seekteachers] %d unique listing(s) from %d page(s) across %d country/countries",
            len(all_jobs), total_pages, len(selected),
        )

        return all_jobs

    def _discover_countries(self) -> dict[str, str]:
        soup = self.fetch_with_retry("/jobs.asp?keyword=physics")
        result: dict[str, str] = {}
        for link in soup.select('a[href*="keyword=physics&country_id="]'):
            href = self.extract_attr(link, "href")
            m = re.search(r"country_id=(\d+)", href)
            if not m:
                continue
            text = link.get_text(strip=True)
            text = _COUNT_RE.sub("", text).strip()
            if text:
                result[m.group(1)] = text
        return result

    def _canonical_name(self, name: str) -> str:
        return COUNTRY_ALIASES.get(name, name)

    def _extract_jobs(self, soup, country_id: str, country_name: str) -> list[dict]:
        results = []
        # Job blocks are NOT wrapped in a per-job container: each block is a
        # ``div.titlebar-listing`` (flag + title + location) followed by loose
        # sibling divs (description, salary, start date, Read More row) up to
        # the next ``titlebar-listing``.  Walk siblings for the full chunk.
        for section in soup.select("div.titlebar-listing"):
            link = section.select_one('a[href*="job-detail.asp?job_id="]')
            if link is None:
                continue
            url = self.extract_attr(link, "href")
            title_el = link.select_one("span[style*='font-size']")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or not url:
                continue

            link_text = link.get_text(" ", strip=True)
            loc_m = re.search(r"Permanent Post in\s*(.+?)$", link_text)
            location = loc_m.group(1).strip() if loc_m else country_name

            chunk = [section]
            node = section.find_next_sibling()
            while node is not None and not (
                node.name == "div" and "titlebar-listing" in (node.get("class") or [])
            ):
                chunk.append(node)
                node = node.find_next_sibling()

            chunk_text = " ".join(el.get_text(" ", strip=True) for el in chunk)

            # The description div and start-date span are chunk nodes THEMSELVES
            # (loose siblings), not descendants — check the node, not select_one().
            description = ""
            for el in chunk:
                if el.name == "div" and el.get("class") == ["margin-top"]:
                    description = el.get_text(" ", strip=True)
                    break

            salary_range = ""
            m = re.search(r"Salary up to:\s*([\d,]+)\s*([A-Za-z() ]+?)\s*Per\s+(Month|Year)", chunk_text)
            if m:
                salary_range = f"{m.group(1)} {m.group(2).strip()} per {m.group(3)}"

            start_date = ""
            for el in chunk:
                if el.name == "span" and el.get("style") and "color:green" in el.get("style"):
                    start_date = el.get_text(strip=True)
                    break

            results.append({
                "title": title,
                "url": self.absolute_url(url),
                "school": "",
                "location": location,
                "country": self._canonical_name(country_name),
                "salary_range": salary_range,
                "closing_date": "",
                "subject": self._subject_tags(title),
                "curriculum": [],
                "job_type": "Permanent" if loc_m else "",
                "category": "",
                "description": description,
                "start_date": start_date,
                "easy_apply": False,
            })
        return results

    @staticmethod
    def _subject_tags(title: str) -> list[str]:
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