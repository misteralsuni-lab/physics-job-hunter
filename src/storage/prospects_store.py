import json
import logging
from pathlib import Path
from typing import Any

import httpx

from src.config import settings

log = logging.getLogger("job-hunter")

DB_PATH = Path("data/prospects.db")

# Column order used for both Supabase upsert and SQLite mirror.
_PROSPECT_COLUMNS = [
    "campaign_id", "school_name", "location", "normalized_key",
    "latitude", "longitude", "distance_km", "ring",
    "pearson_offerings", "lane",
    "visa", "career", "competition", "location_score", "curriculum_score",
    "campaign_score", "tier", "category_f", "evidence_urls",
    "confidence", "contact_strategy", "outreach_email_path", "research_brief",
]


def _normalize_key(school_name: str, location: str) -> str:
    return f"{(school_name or '').strip().lower()}|{(location or '').strip().lower()}"


def _as_json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


class _ProspectsSQLite:
    """SQLite fallback mirroring the Supabase ``campaign_prospects`` table.

    Used when Supabase is unreachable (mirrors the ``DedupStore`` pattern from
    the job pipeline). Arrays are stored as JSON-encoded text.
    """

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = __import__("sqlite3").connect(str(self.db_path))
        self._init_tables()

    def _init_tables(self):
        cols = ", ".join(f"{c} TEXT" for c in _PROSPECT_COLUMNS)
        # Mirror Supabase's on_conflict=(campaign_id, normalized_key) so that
        # re-runs upsert rather than append duplicate rows.
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS prospects ("
            f"{cols}, PRIMARY KEY (campaign_id, normalized_key))"
        )
        self._conn.commit()

    def upsert(self, prospects: list[dict[str, Any]]) -> int:
        placeholders = ", ".join(["?"] * len(_PROSPECT_COLUMNS))
        for p in prospects:
            row = self._row(p)
            self._conn.execute(
                f"INSERT OR REPLACE INTO prospects ({', '.join(_PROSPECT_COLUMNS)}) "
                f"VALUES ({placeholders})",
                row,
            )
        self._conn.commit()
        return len(prospects)

    def _row(self, p: dict[str, Any]) -> list:
        out = []
        for c in _PROSPECT_COLUMNS:
            v = p.get(c)
            if c in ("pearson_offerings", "evidence_urls") and v is not None:
                v = json.dumps(_as_json_list(v))
            elif c == "research_brief" and v is not None:
                v = json.dumps(v)
            elif c == "category_f":
                v = "1" if v else "0"
            out.append("" if v is None else str(v))
        return out

    def get_all(self, campaign_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            f"SELECT {', '.join(_PROSPECT_COLUMNS)} FROM prospects WHERE campaign_id = ?",
            (campaign_id,),
        )
        rows = cur.fetchall()
        return [self._decode(r) for r in rows]

    def _decode(self, row) -> dict[str, Any]:
        p = {}
        for col, val in zip(_PROSPECT_COLUMNS, row):
            if col in ("pearson_offerings", "evidence_urls") and val:
                p[col] = json.loads(val)
            elif col == "research_brief" and val:
                p[col] = json.loads(val)
            elif col == "category_f":
                p[col] = val == "1"
            else:
                p[col] = val
        return p


class ProspectsStore:
    """Persistence for campaign prospects: Supabase primary, SQLite fallback."""

    def __init__(self) -> None:
        self._supabase: Any | None = None
        self._sqlite = _ProspectsSQLite()
        if settings.supabase_url and settings.supabase_service_role_key:
            try:
                from supabase import create_client
                self._supabase = create_client(
                    settings.supabase_url, settings.supabase_service_role_key
                )
            except Exception as exc:
                log.warning("ProspectsStore: Supabase client init failed: %s", exc)
                self._supabase = None

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def upsert_prospects(self, prospects: list[dict[str, Any]]) -> int:
        if not prospects:
            return 0
        if self._supabase is not None:
            try:
                rows = [self._supabase_row(p) for p in prospects]
                self._supabase.table("campaign_prospects").upsert(
                    rows, on_conflict="campaign_id,normalized_key"
                ).execute()
                log.info("ProspectsStore: upserted %d prospect(s) to Supabase", len(rows))
                return len(rows)
            except httpx.HTTPError as exc:
                log.warning("ProspectsStore: Supabase upsert failed (%s) — SQLite fallback", exc)
            except Exception as exc:
                log.warning("ProspectsStore: Supabase upsert error (%s) — SQLite fallback", exc)
        return self._sqlite.upsert(prospects)

    @staticmethod
    def _supabase_row(p: dict[str, Any]) -> dict[str, Any]:
        row = {c: p.get(c) for c in _PROSPECT_COLUMNS}
        row["pearson_offerings"] = _as_json_list(row.get("pearson_offerings"))
        row["evidence_urls"] = _as_json_list(row.get("evidence_urls"))
        row["category_f"] = bool(row.get("category_f"))
        return row

    def get_all(self, campaign_id: str) -> list[dict[str, Any]]:
        if self._supabase is not None:
            try:
                res = self._supabase.table("campaign_prospects").select("*").eq(
                    "campaign_id", campaign_id
                ).execute()
                if res.data:
                    return list(res.data)
            except httpx.HTTPError:
                log.warning("ProspectsStore: Supabase get_all failed — SQLite fallback")
            except Exception as exc:
                log.warning("ProspectsStore: Supabase get_all error (%s) — SQLite fallback", exc)
        return self._sqlite.get_all(campaign_id)

    def get_top(self, campaign_id: str, n: int = 10) -> list[dict[str, Any]]:
        all_p = self.get_all(campaign_id)
        # Category F first, then by campaign_score descending.
        ordered = sorted(
            all_p,
            key=lambda p: (not bool(p.get("category_f")), -(int(p.get("campaign_score") or 0))),
        )
        return ordered[:n]

    def mark_email_written(self, campaign_id: str, normalized_key: str, path: str) -> None:
        for store in (self._supabase, self._sqlite):
            if store is None:
                continue
            try:
                store.table("campaign_prospects").update(
                    {"outreach_email_path": path}
                ).eq("campaign_id", campaign_id).eq("normalized_key", normalized_key).execute()
            except Exception:
                pass

    def close(self) -> None:
        try:
            self._sqlite._conn.close()
        except Exception:
            pass
