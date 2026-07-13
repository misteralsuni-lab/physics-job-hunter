import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings

log = logging.getLogger("job-hunter")


def _slug(prospect: dict[str, Any]) -> str:
    text = f"{prospect.get('school_name', 'school')}_{prospect.get('location', '')}"
    safe = "".join(c.lower() for c in text if c.isalnum() or c in " -_").strip()
    safe = safe.replace(" ", "_")
    return safe[:80].rstrip("_") or "school"


class CampaignReporter:
    """Renders the master strategy report, prospect briefs and the top-10
    Telegram digest for a proactive campaign run.
    """

    def __init__(self, campaign: dict[str, Any]) -> None:
        self.campaign = campaign
        out = campaign.get("output", {})
        self.base_dir = Path(out.get("base_dir", "data/campaign_pe_central_europe"))
        self.prospects_dir = self.base_dir / out.get("prospects_dir", "prospects")
        self.emails_dir = self.base_dir / out.get("emails_dir", "emails")
        self.report_file = self.base_dir / out.get("strategy_report", "STRATEGY_REPORT.md")
        self.prospects_dir.mkdir(parents=True, exist_ok=True)
        self.emails_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    #  Prospect briefs (all ~40)
    # ------------------------------------------------------------------

    def write_prospect_briefs(self, prospects: list[dict[str, Any]]) -> None:
        for p in prospects:
            slug = _slug(p)
            path = self.prospects_dir / f"{slug}.md"
            path.write_text(self._prospect_brief_md(p), encoding="utf-8")
        log.info("CampaignReporter: wrote %d prospect brief(s) → %s",
                 len(prospects), self.prospects_dir)

    @staticmethod
    def _prospect_brief_md(p: dict[str, Any]) -> str:
        lines = [
            f"# {p.get('school_name', 'Unknown School')}",
            "",
            f"- **Location:** {p.get('location', '')}",
            f"- **Distance from Dresden:** {p.get('distance_km', '')} km (ring {p.get('ring', '')})",
            f"- **Lane / Curriculum:** {p.get('lane', '')}",
            f"- **Tier:** {p.get('tier', '')}",
            f"- **Campaign Score:** {p.get('campaign_score', 0)}/100",
            f"- **Confidence:** {p.get('confidence', '')}",
        ]
        if p.get("category_f"):
            lines.append("- **Category F:** live vacancy detected")
        lines += [
            "",
            "## Scores",
            f"- Curriculum: {p.get('curriculum_score', 0)}/30",
            f"- Visa: {p.get('visa', 0)}/20",
            f"- Location: {p.get('location_score', 0)}/15",
            f"- Career: {p.get('career', 0)}/20",
            f"- Competition: {p.get('competition', 0)}/15",
            "",
            "## Pearson Offerings",
        ]
        lines.append(", ".join(p.get("pearson_offerings", []) or ["(unknown)"]))
        lines += ["", "## Evidence"]
        for u in p.get("evidence_urls", []) or []:
            lines.append(f"- {u}")
        brief = p.get("research_brief")
        if brief:
            lines += ["", "## PART-8 Research Brief"]
            for key in ("school_profile", "recruitment_analysis", "candidate_match",
                        "contact_strategy", "institution_facts", "strategic_alignment",
                        "recommended_angle"):
                val = brief.get(key)
                if not val:
                    continue
                if isinstance(val, list):
                    val = "\n".join(f"- {v}" for v in val)
                lines += [f"### {key.replace('_', ' ').title()}", "", str(val), ""]
        lines += ["", f"_Generated {datetime.now().strftime('%Y-%m-%d')}_", ""]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    #  Master strategy report (10 parts) — §6
    # ------------------------------------------------------------------

    def render_strategy_report(
        self,
        all_prospects: list[dict[str, Any]],
        top10: list[dict[str, Any]],
    ) -> str:
        ranked = sorted(
            all_prospects,
            key=lambda p: (not bool(p.get("category_f")), -(int(p.get("campaign_score") or 0))),
        )
        parts: list[str] = []
        parts.append(f"# Pearson Edexcel Central Europe — Master Strategy Report\n")
        parts.append(f"_Generated {datetime.now().strftime('%Y-%m-%d')} · "
                     f"{len(all_prospects)} schools discovered_\n")

        # 1. Geographic ranking
        parts.append("## 1. Geographic Ranking")
        parts.append("Ordered by distance from Dresden (family base).\n")
        for p in sorted(all_prospects, key=lambda x: float(x.get("distance_km") or 9999)):
            parts.append(f"- {p.get('school_name')} — {p.get('location')} "
                         f"({p.get('distance_km')} km, ring {p.get('ring')})")
        parts.append("")

        # 2. Curriculum / campaign scoring ranking
        parts.append("## 2. School Ranking (Campaign Score)")
        parts.append("All discovered schools, scored 0–100 on the 5-axis rubric.\n")
        for i, p in enumerate(ranked, 1):
            parts.append(f"{i}. {p.get('school_name')} — {p.get('campaign_score')}/100 "
                         f"[{p.get('tier')}]")
        parts.append("")

        # 3. Recruitment probability
        parts.append("## 3. Recruitment Probability")
        parts.append("Proxy: campaign score decomposed. Higher `career` + lower `competition` "
                     "= stronger probability. Category-F schools are live opportunities.\n")
        for p in top10:
            prob = round((int(p.get("career", 0)) / 20.0) * 100 - (int(p.get("competition", 0)) / 15.0) * 30)
            parts.append(f"- {p.get('school_name')}: ~{max(0, min(100, prob))}% "
                         f"(career {p.get('career')}, competition {p.get('competition')})")
        parts.append("")

        # 4. Visa analysis
        parts.append("## 4. Visa Analysis")
        for p in top10:
            visa = int(p.get("visa", 0) or 0)
            parts.append(f"- {p.get('school_name')}: visa axis {visa}/20 "
                          f"({'sponsorship likely' if visa >= 20 else 'international history' if visa >= 10 else 'unknown — verify'})")
        parts.append("")

        # 5. Contact strategy
        parts.append("## 5. Contact Strategy")
        for p in top10:
            strat = (p.get("research_brief") or {}).get("contact_strategy") or p.get("contact_strategy") or "Research institution; approach HR/Head of Science via email with speculative CV."
            parts.append(f"- {p.get('school_name')}: {strat}")
        parts.append("")

        # 6. Visit strategy
        parts.append("## 6. Visit Strategy (Dresden-Centred)")
        parts.append("Candidate has a relative in Dresden and visits Dresden + the nearby city "
                     "next month. Prioritise inner-ring (Dresden/Leipzig) schools for in-person "
                     "meetings; propose demo lessons for the top tier during the trip.\n")
        for p in [x for x in top10 if float(x.get("distance_km") or 9999) <= 150]:
            parts.append(f"- {p.get('school_name')} ({p.get('distance_km')} km) — in-person feasible")
        parts.append("")

        # 7. CV positioning
        parts.append("## 7. CV Positioning")
        parts.append("Lead with Pearson Edexcel IGCSE (4PH1) + A-Level Physics/Maths authority, "
                     "PGCEi (Liverpool John Moores), and 4+ years international experience. Attach "
                     "`CV_Mahmoud_Alsini.html` to every outreach email. Bridge Cambridge/IB Physics-Maths "
                     "via ~90% content overlap where the target school is non-Edexcel.")
        parts.append("")

        # 8. Automation design
        parts.append("## 8. Automation Design")
        parts.append("DiscoveryAgent (radial web-search, this pipeline) enumerates and verifies "
                     "schools → ProspectsStore (Supabase + SQLite fallback) → ResearchAgent deep-research "
                     "top 10 → CoverLetterGenerator (speculative mode) → CampaignReporter (this report). "
                     "Re-run with FORCE=1 refreshes; dedup key is school_name + location.")
        parts.append("")

        # 9. 8-week action plan
        parts.append("## 9. Eight-Week Action Plan")
        for wk, act in [
            ("Week 1-2", "Send top-5 (Apply Immediately) speculative emails with CV; request meetings during Dresden visit."),
            ("Week 3-4", "Send next-5 (Network First) emails; follow up on replies; schedule demo lessons."),
            ("Week 5-6", "Attend Dresden visit; hold in-person meetings; expand to low-priority list as time allows."),
            ("Week 7-8", "Consolidate replies; if zero positive, trigger Cambridge fallback campaign."),
        ]:
            parts.append(f"- **{wk}:** {act}")
        parts.append("")

        # 10. Category F callouts
        parts.append("## 10. Category F — Live Vacancies")
        catf = [p for p in all_prospects if p.get("category_f")]
        if catf:
            for p in catf:
                parts.append(f"- 🔥 {p.get('school_name')} ({p.get('location')}) — vacancy detected. "
                             f"Evidence: {', '.join(p.get('evidence_urls', []) or [])}")
        else:
            parts.append("No live Edexcel Physics/Maths vacancies detected during discovery "
                         "(expected — this is a speculative campaign).")
        parts.append("")

        report = "\n".join(parts)
        self.report_file.write_text(report, encoding="utf-8")
        log.info("CampaignReporter: wrote strategy report → %s", self.report_file.resolve())
        return str(self.report_file.resolve())

    # ------------------------------------------------------------------
    #  Telegram digest (top 10 only)
    # ------------------------------------------------------------------

    def send_digest(self, top10: list[dict[str, Any]], email_paths: dict[str, str]) -> int:
        from src.notify.telegram import send_campaign_digest
        return send_campaign_digest(top10, email_paths)
