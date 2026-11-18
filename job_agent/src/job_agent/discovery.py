"""Automated company discovery from HN's and YC's official, documented
public APIs — feeds candidates into the watchlist via the existing ATS
detector, rather than you typing companies in by hand (step 3c).

VC portfolio pages are deliberately NOT built here. Each VC firm's site
has its own layout, and parsing arbitrary heterogeneous HTML reliably is
a judgment call, not a deterministic one — ask Claude to check a
specific VC's portfolio page directly when you want that, rather than
this module guessing at a generic scraper.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

import httpx

from job_agent.ats import detect_ats
from job_agent.watchlist import Company, load_watchlist, save_watchlist

HN_API = "https://hacker-news.firebaseio.com/v0"
YC_API = "https://api.ycombinator.com/v0.1/companies"


@dataclass
class CompanyCandidate:
    name: str
    source: str  # "hn" or "yc"
    hint_url: str | None = None  # a URL mentioned alongside it, if any — tried first for ATS detection


def fetch_whoishiring_thread_id(client: httpx.Client) -> int:
    """The most recent 'Ask HN: Who is hiring?' story id.

    The whoishiring account posts THREE threads a month (hiring, who
    wants to be hired, freelancer) — this picks the right one by title,
    not just "most recent submission".
    """
    submitted = client.get(f"{HN_API}/user/whoishiring.json", timeout=10.0).json()["submitted"]
    for item_id in submitted[:10]:
        item = client.get(f"{HN_API}/item/{item_id}.json", timeout=10.0).json()
        if (item.get("title") or "").startswith("Ask HN: Who is hiring?"):
            return item_id
    raise RuntimeError("Couldn't find a recent 'Who is hiring?' thread among whoishiring's last 10 posts")


def _extract_company_name(comment_html: str) -> str | None:
    """HN's convention is 'CompanyName | field | field | ...' — best
    effort, not guaranteed: posts that don't follow it produce junk,
    which the length/emptiness check below filters out."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(comment_html))
    first_field = text.split("|")[0].strip()
    if not first_field or len(first_field) > 60:
        return None
    return first_field


def discover_from_hn(client: httpx.Client | None = None) -> list[CompanyCandidate]:
    owns_client = client is None
    client = client or httpx.Client()
    try:
        thread_id = fetch_whoishiring_thread_id(client)
        thread = client.get(f"{HN_API}/item/{thread_id}.json", timeout=10.0).json()

        candidates = []
        for comment_id in thread.get("kids", []):
            comment = client.get(f"{HN_API}/item/{comment_id}.json", timeout=10.0).json()
            if comment.get("dead") or comment.get("deleted") or not comment.get("text"):
                continue
            name = _extract_company_name(comment["text"])
            if name:
                candidates.append(CompanyCandidate(name=name, source="hn"))
        return candidates
    finally:
        if owns_client:
            client.close()


def discover_from_yc(batches: list[str], client: httpx.Client | None = None) -> list[CompanyCandidate]:
    """batches is explicit (e.g. ["W27", "S26"]) rather than guessed —
    YC's batch-naming convention could change, and guessing "the current
    batch" risks silently fetching nothing."""
    owns_client = client is None
    client = client or httpx.Client()
    try:
        candidates = []
        for batch in batches:
            page = 1
            while True:
                response = client.get(YC_API, params={"batch": batch, "page": page}, timeout=10.0).json()
                for company in response.get("companies", []):
                    if company.get("status") != "Active":
                        continue
                    candidates.append(
                        CompanyCandidate(name=company["name"], source="yc", hint_url=company.get("website"))
                    )
                if page >= response.get("totalPages", 1):
                    break
                page += 1
        return candidates
    finally:
        if owns_client:
            client.close()


def add_discovered_companies(candidates: list[CompanyCandidate]) -> dict:
    """Detect each candidate's ATS and add only the ones actually found
    to the watchlist — a company we can't fetch jobs from is clutter,
    not a lead (matches "dashboard never pads results"). Duplicate names
    already on the watchlist are skipped, not re-added.
    """
    companies = load_watchlist()
    existing_names = {c.name for c in companies}

    added: list[str] = []
    skipped_no_ats: list[str] = []
    skipped_duplicate: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        if candidate.name in seen:
            continue
        seen.add(candidate.name)

        if candidate.name in existing_names:
            skipped_duplicate.append(candidate.name)
            continue

        careers_url = candidate.hint_url or candidate.name
        match = detect_ats(careers_url)
        if match is None:
            skipped_no_ats.append(candidate.name)
            continue

        companies.append(Company.from_match(candidate.name, careers_url, match))
        added.append(candidate.name)

    save_watchlist(companies)
    return {"added": added, "skipped_no_ats": skipped_no_ats, "skipped_duplicate": skipped_duplicate}
