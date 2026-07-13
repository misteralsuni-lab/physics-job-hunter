import logging
import time
from math import asin, cos, radians, sin, sqrt
from typing import Any

from src.agents.tools import web_search
from src.config import settings

log = logging.getLogger("job-hunter")

DRESDEN = (51.0504, 13.7373)

# City-level coordinate + country cache for Central Europe. Used as the
# primary geocoding source (no external API key required) with Nominatim as a
# fallback for cities not listed here.
CITY_COORDS: dict[str, tuple[float, float, str]] = {
    "dresden": (51.0504, 13.7373, "germany"),
    "leipzig": (51.3397, 12.3731, "germany"),
    "berlin": (52.5200, 13.4050, "germany"),
    "munich": (48.1351, 11.5820, "germany"),
    "muenchen": (48.1351, 11.5820, "germany"),
    "nuremberg": (49.4521, 11.0767, "germany"),
    "nürnberg": (49.4521, 11.0767, "germany"),
    "paderborn": (51.7092, 8.7579, "germany"),
    "halle": (51.4818, 11.9704, "germany"),
    "erfurt": (50.9824, 11.0299, "germany"),
    "chemnitz": (50.8278, 12.9214, "germany"),
    "cottbus": (51.7620, 14.3257, "germany"),
    "prague": (50.0755, 14.4378, "czechia"),
    "praha": (50.0755, 14.4378, "czechia"),
    "brno": (49.1951, 16.6068, "czechia"),
    "brünn": (49.1951, 16.6068, "czechia"),
    "plzen": (49.7384, 13.3736, "czechia"),
    "pliben": (49.7384, 13.3736, "czechia"),
    "liberec": (50.7707, 15.0584, "czechia"),
    "ostrava": (49.8209, 18.2625, "czechia"),
    "warsaw": (52.2297, 21.0122, "poland"),
    "wroclaw": (51.1079, 17.0385, "poland"),
    "wrocław": (51.1079, 17.0385, "poland"),
    "vienna": (48.2082, 16.3738, "austria"),
    "wien": (48.2082, 16.3738, "austria"),
    "bratislava": (48.1486, 17.1077, "slovakia"),
    "budapest": (47.4979, 19.0402, "hungary"),
}

_GEO_CACHE: dict[str, tuple[float, float, str]] = {}


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def geocode(query: str) -> tuple[float, float, str] | None:
    if not query:
        return None
    q = query.lower().strip()
    if q in _GEO_CACHE:
        return _GEO_CACHE[q]
    for city, coord in CITY_COORDS.items():
        if city in q:
            _GEO_CACHE[q] = coord
            return coord
    try:
        import httpx

        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "physics-job-hunter/1.0"},
            timeout=15,
        )
        data = resp.json()
        if data:
            addr = data[0].get("address", {})
            country_raw = (addr.get("country") or "").lower()
            country = (
                "germany" if "germany" in country_raw
                else "czechia" if "czech" in country_raw
                else "austria" if "austria" in country_raw
                else "poland" if "poland" in country_raw
                else "slovakia" if "slovakia" in country_raw
                else "hungary" if "hungary" in country_raw
                else "central_europe"
            )
            coord = (float(data[0]["lat"]), float(data[0]["lon"]), country)
            _GEO_CACHE[q] = coord
            return coord
    except Exception as exc:
        log.debug("geocode failed for %r: %s", query, exc)
    return None


class DiscoveryAgent:
    """Radial, agent-driven discovery of real target schools.

    Walks outward from Dresden in concentric rings, web-searches for
    Pearson Edexcel (or Cambridge) Physics/Maths schools in each region,
    verifies each candidate against an evidence URL, geo-locates it, scores
    and tiers it. Cheap by design: web_search only, no LLM deep-research.
    """

    def __init__(self, campaign: dict) -> None:
        self.campaign = campaign
        self.required = (campaign.get("required_curriculum") or "Edexcel").lower()
        self.discovery = campaign.get("discovery", {})
        center = self.discovery.get("center", {}) or {}
        self.center = (center.get("lat", 51.0504), center.get("lon", 13.7373))
        self.max_radius = self.discovery.get("max_radius_km", 300)
        self.ring_step = self.discovery.get("ring_step_km", 50)
        self.cap = self.discovery.get("cap", 40)
        self.region_queries = self.discovery.get("region_queries", {})
        self.prefix = "pearson_edexcel" if self.required == "edexcel" else "cambridge"
        self.thresholds = campaign.get("classification_thresholds", {})
        self._seen: set[str] = set()

    def discover(self, force: bool = False) -> list[dict[str, Any]]:
        prospects: list[dict[str, Any]] = []
        rings = sorted(int(r) for r in self.region_queries.keys())
        for radius in rings:
            if len(prospects) >= self.cap:
                break
            region = self.region_queries[str(radius)]
            log.info("Discovery ring %d km — region: %s", radius, region)
            candidates = self._search_ring(region)
            for cand in candidates:
                if len(prospects) >= self.cap:
                    break
                prospect = self._process_candidate(cand, radius)
                if prospect is None:
                    continue
                if prospect["distance_km"] > self.max_radius:
                    log.info("  - %s dropped: %.0f km beyond max radius",
                             prospect["school_name"], prospect["distance_km"])
                    continue
                key = prospect["normalized_key"]
                if key in self._seen and not force:
                    continue
                self._seen.add(key)
                prospects.append(prospect)
                log.info("  + %s (%s) score=%d ring=%d catF=%s",
                         prospect["school_name"], prospect["location"],
                         prospect["campaign_score"], prospect["ring"], prospect["category_f"])
            time.sleep(1)
        return prospects

    def _search_ring(self, region: str) -> list[dict[str, Any]]:
        if self.required == "cambridge":
            query = (
                f"Cambridge International IGCSE A-Level Physics Mathematics "
                f"school near {region}"
            )
        else:
            query = (
                f"Pearson Edexcel International GCSE A-Level Physics Mathematics "
                f"school near {region}"
            )
        res = web_search(query, max_results=8)
        if res.get("error") == "circuit_breaker_active":
            return []
        candidates: list[dict[str, Any]] = []
        for r in res.get("results", []):
            name = self._extract_school_name(r.get("title", ""), r.get("link", ""))
            if not name:
                continue
            candidates.append({
                "name": name,
                "url": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "region": region,
            })
        return candidates

    @staticmethod
    def _extract_school_name(title: str, link: str) -> str:
        title = (title or "").strip()
        if not title:
            return ""
        sep = max(title.find(" - "), title.find(" | "), title.find(" – "))
        if sep > 3:
            title = title[:sep]
        title = title.strip()
        if len(title) < 3 or len(title) > 80:
            return ""
        return title

    def _process_candidate(self, cand: dict[str, Any], radius: int) -> dict[str, Any] | None:
        name = cand["name"]
        vq = f"{name} {self.required} IGCSE A-Level Physics Mathematics curriculum"
        vres = web_search(vq, max_results=5)
        time.sleep(1)

        combined = cand["snippet"]
        evidence_url = cand["url"]
        for r in vres.get("results", []):
            combined += " " + r.get("snippet", "") + " " + r.get("title", "")
            if self._is_evidence(r.get("snippet", "") + " " + r.get("title", "")):
                if r.get("link"):
                    evidence_url = r.get("link")

        if not self._is_evidence(combined):
            return None

        offerings = self._detect_offerings(combined)
        cat_f, vacancy_url = self._check_category_f(name)
        evidence_urls = [evidence_url] + ([vacancy_url] if vacancy_url else [])

        loc_text = self._locate(cand, combined)
        coord = geocode(loc_text or name)
        if coord is None:
            coord = (self.center[0], self.center[1], "central_europe")
        lat, lon, country = coord
        dist = haversine(self.center, (lat, lon))
        ring = int(dist // self.ring_step)

        prospect: dict[str, Any] = {
            "campaign_id": self.campaign.get("id", ""),
            "school_name": name,
            "location": loc_text or cand["region"],
            "normalized_key": f"{name.lower()}|{(loc_text or cand['region']).lower()}",
            "latitude": lat,
            "longitude": lon,
            "distance_km": round(dist, 1),
            "ring": ring,
            "pearson_offerings": sorted(offerings),
            "lane": self.required,
            "category_f": cat_f,
            "evidence_urls": evidence_urls,
            "confidence": "low",
            "contact_strategy": "",
            "outreach_email_path": "",
            "research_brief": None,
        }
        self._score(prospect, offerings, combined, dist, country, cat_f)
        return prospect

    def _is_evidence(self, text: str) -> bool:
        t = (text or "").lower()
        if self.required == "edexcel":
            board_ok = ("edexcel" in t) or ("pearson" in t)
        else:
            board_ok = "cambridge" in t
        if not board_ok:
            return False
        has_physics = "physics" in t
        has_level = ("igcse" in t) or ("a-level" in t) or ("a level" in t) or ("gcse" in t)
        return has_physics and has_level

    def _detect_offerings(self, text: str) -> set[str]:
        t = (text or "").lower()
        offerings: set[str] = set()
        has_al = ("a-level" in t) or ("a level" in t)
        has_ig = ("igcse" in t) or ("gcse" in t)
        has_phys = "physics" in t
        has_math = ("maths" in t) or ("mathematics" in t) or ("math " in t)
        if has_al and has_phys:
            offerings.add("a_level_physics")
        if has_al and has_math:
            offerings.add("a_level_maths")
        if has_ig and has_phys:
            offerings.add("igcse_physics")
        if has_ig and has_math:
            offerings.add("igcse_maths")
        if has_phys or has_math:
            offerings.add("strong_stem")
        return offerings

    def _check_category_f(self, name: str) -> tuple[bool, str | None]:
        q = f"{name} careers vacancies physics teacher"
        res = web_search(q, max_results=5)
        time.sleep(1)
        if res.get("error") == "circuit_breaker_active":
            return False, None
        for r in res.get("results", []):
            t = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            if "physics" in t and ("vacanc" in t or "job" in t or "career" in t):
                return True, r.get("link", "")
        return False, None

    def _locate(self, cand: dict[str, Any], combined: str) -> str:
        for city in CITY_COORDS:
            if city in combined.lower():
                return city.title()
        for city in CITY_COORDS:
            if city in (cand.get("region", "") or "").lower():
                return city.title()
        return cand.get("region", "")

    def _score(self, prospect: dict[str, Any], offerings: set[str], text: str,
               dist: float, country: str, cat_f: bool) -> None:
        scoring = self.campaign.get("scoring", {})
        comp = scoring.get("curriculum_match", {}).get("components", {})
        cmap = {
            "a_level_physics": f"{self.prefix}_a_level_physics",
            "a_level_maths": f"{self.prefix}_a_level_maths",
            "igcse_physics": f"{self.prefix}_igcse_physics",
            "igcse_maths": f"{self.prefix}_igcse_maths",
            "strong_stem": "strong_stem",
        }
        curriculum_score = sum(comp.get(cmap[o], 0) for o in offerings)
        curriculum_score = min(30, curriculum_score)

        vcomp = scoring.get("visa", {})
        tl = text.lower()
        if "sponsorship" in tl or "visa support" in tl:
            visa = vcomp.get("explicit_sponsorship", 20)
        elif "international" in tl:
            visa = vcomp.get("international_hiring_history", 10)
        else:
            visa = vcomp.get("unknown", 5)

        loc_comp = scoring.get("location", {}).get("components", {})
        if dist <= 50:
            location_score = loc_comp.get("dresden_region", 20)
        elif country == "germany":
            location_score = loc_comp.get("germany", 15)
        elif country == "czechia":
            location_score = loc_comp.get("czechia", 10)
        else:
            location_score = loc_comp.get("central_europe", 5)

        career = 8
        if "international" in tl:
            career += 6
        if "bilingual" in tl or " ib " in tl or "international baccalaureate" in tl:
            career += 4
        career = min(20, career)

        if dist <= 50:
            competition = 5
        elif country == "germany":
            competition = 8
        elif country == "czechia":
            competition = 10
        else:
            competition = 12
        competition = min(15, competition)

        total = min(100, curriculum_score + visa + location_score + career + competition)

        if cat_f:
            tier = "F"
        elif total >= self.thresholds.get("apply_immediately", 66):
            tier = "apply_immediately"
        elif total >= self.thresholds.get("network_first", 45):
            tier = "network_first"
        else:
            tier = "low_priority"

        if evidence_url_present := prospect.get("evidence_urls"):
            if "a_level_physics" in offerings and "igcse_physics" in offerings:
                confidence = "high"
            else:
                confidence = "medium"
        else:
            confidence = "low"

        prospect.update({
            "curriculum_score": curriculum_score,
            "visa": visa,
            "location_score": location_score,
            "career": career,
            "competition": competition,
            "campaign_score": total,
            "tier": tier,
            "confidence": confidence,
        })
