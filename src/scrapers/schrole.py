"""
Schrole scraper — INTENTIONALLY DORMANT (recon 2026-10-01).

Schrole is one of the largest international-school job boards, so this looks
like the single biggest coverage win available. It is not anonymously
scrapable.

Recon result
------------
* The real listing URLs are ``/jobs-for-teachers/<region>/`` with regions
  ``africa | americas | asia | europe | middle-east | oceania`` — *not* the
  ``/en/job-search`` or ``/en/jobs`` paths previously assumed (both 404).
* ``/jobs-for-teachers/asia/jobs/`` and ``/jobs-for-teachers/middle-east/jobs/``
  both return HTTP 200 but contain only **school** cards (``.card--has-link``,
  ``.card__featured-school``) linking to ``/schools/<slug>/``. Zero job
  listings are present in the served HTML.
* The site's public API host is ``app.schrole.com``. Every path referenced
  from the public pages is either ``/api/files/<uuid>`` (image assets) or
  ``/Identity/Account/Login`` / ``/Identity/Account/Register``. There is no
  anonymous jobs endpoint — job postings sit behind an account.

Consequence
-----------
Implementing this requires Schrole credentials, in the same dormant pattern
as ``SearchAssociatesScraper`` (``sa_username``/``sa_password``) and
``TeacherHorizonsScraper`` (``th_email``/``th_password``). Until those exist
there is no anonymous path, so the scraper reports the fact once and returns
nothing rather than pretending to work.
"""
import logging
from typing import Any

from src.scrapers.base import BaseScraper

log = logging.getLogger(__name__)


class SchroleScraper(BaseScraper):
    SOURCE_NAME = "schrole"
    BASE_URL = "https://www.schrole.com"

    # Correct public listing roots, kept for whoever wires up credentials.
    REGION_PATHS = (
        "/jobs-for-teachers/middle-east/",
        "/jobs-for-teachers/asia/",
    )

    def scrape(self, search_terms: list[str] | None = None) -> list[dict[str, Any]]:
        log.warning(
            "Schrole scraper is credential-gated, not merely unimplemented: job "
            "postings are only served to authenticated accounts "
            "(app.schrole.com/Identity/Account/Login). Listing roots for a future "
            "credentialed implementation: %s. Returning no jobs.",
            ", ".join(self.REGION_PATHS),
        )
        return []