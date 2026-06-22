"""Storage layer for the private-tutoring branch.

Mirrors ``SupabaseClient`` (Supabase with httpx-fallback) but is intentionally
narrower: no DedupStore mirror, since ``tutoring_leads`` is interactive
(Manual paste + Telegram inbound + score + status flips) and a Supabase
outage should be loud, not silently masked.

See ``docs/dual-pathway.md`` §3, §6, §9.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from supabase import create_client, Client

from src.config import settings

log = logging.getLogger("job-hunter")


_VALID_STATUSES: frozenset[str] = frozenset({
    "new",
    "low_budget_hold",
    "out_of_scope_hold",
    "proposal_sent",
    "reply_received",
    "paid_first_session",
    "lost",
})


class TutoringLeadStorage:
    """CRUD against the ``tutoring_leads`` table.

    Methods raise :class:`httpx.HTTPError` when Supabase is unreachable;
    callers are expected to surface the failure to the user (a Telegram
    paste or a manual form submission failing silently would be a hard bug).
    """

    def __init__(self) -> None:
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    # ---- Health -----------------------------------------------------------

    def health_check(self) -> bool:
        try:
            self.client.table("tutoring_leads").select("id").limit(1).execute()
            log.info("tutoring_leads Supabase connection healthy")
            return True
        except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
            log.warning("tutoring_leads Supabase unreachable: %s", e)
            return False

    # ---- Intake -----------------------------------------------------------

    def insert_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        """Insert a freshly-ingested lead. Caller passes at minimum:

        ``source`` (``telegram`` / ``manual`` / ``other``) and ``raw_message``.
        All other fields are nullable; the parser fills them in later.
        """
        row = {
            "source": lead.get("source", "manual"),
            "raw_message": lead["raw_message"],
            "status": "new",
        }
        result = self.client.table("tutoring_leads").insert(row).execute()
        if not result.data:
            raise RuntimeError("Supabase insert returned no row")
        return result.data[0]

    # ---- Parse-queue ------------------------------------------------------

    def get_pending_parses(self, limit: int = 25) -> list[dict[str, Any]]:
        """Leads awaiting LLM parse.

        Status ``new`` and ``tutoring_brief_json`` null triggers a parse.
        """
        result = (
            self.client.table("tutoring_leads")
            .select("*")
            .eq("status", "new")
            .is_("tutoring_brief_json", "null")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def save_parse(self, lead_id: str, brief: dict[str, Any]) -> None:
        """Persist the parsed brief, the extracted fields, and the score.

        ``brief`` is the serialised :class:`TutoringBrief` plus the heuristic
        fields extracted alongside it (curriculum, budget, urgency, etc.).
        Caller is responsible for computing the score and the final status.
        """
        self.client.table("tutoring_leads").update(brief).eq("id", lead_id).execute()

    # ---- Reads ------------------------------------------------------------

    def list_leads(
        self,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = self.client.table("tutoring_leads").select("*")
        if statuses:
            query = query.in_("status", statuses)
        result = query.order("created_at", desc=True).limit(limit).execute()
        return result.data or []

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("tutoring_leads")
            .select("*")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]

    # ---- Mutations --------------------------------------------------------

    def update_status(self, lead_id: str, status: str) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"Unknown tutoring_lead status: {status!r}")
        self.client.table("tutoring_leads").update({"status": status}).eq("id", lead_id).execute()

    def save_proposal(self, lead_id: str, proposal_text: str, proposed_rate_usd: float) -> None:
        self.client.table("tutoring_leads").update({
            "proposal_text": proposal_text,
            "proposed_rate_usd": proposed_rate_usd,
            "status": "proposal_sent",
        }).eq("id", lead_id).execute()

    # ---- Aggregates (for dashboard tiles) ---------------------------------

    def counts_current_month(self) -> dict[str, int]:
        """Top-tile counts: New, Proposal sent, Reply received, Paid, Lost."""
        result = self.client.table("tutoring_leads").select("status, created_at").execute()
        rows = result.data or []
        now = datetime.utcnow()
        month_prefix = now.strftime("%Y-%m")
        buckets = {
            "new": 0,
            "proposal_sent": 0,
            "reply_received": 0,
            "paid_first_session": 0,
            "lost": 0,
        }
        for row in rows:
            if not row.get("created_at", "").startswith(month_prefix):
                continue
            s = row.get("status")
            if s in buckets:
                buckets[s] += 1
        return buckets
