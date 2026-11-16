"""Job Finder: pull open jobs from a watchlisted company's ATS feed and
convert them into one standard format, whichever ATS they're on.

Field shapes were verified against real companies (Stripe/Greenhouse,
Palantir/Lever, Ramp/Ashby, NVIDIA/Workday) rather than assumed, since
each ATS names things differently.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from job_agent.watchlist import Company


@dataclass
class Job:
    external_id: str  # this job's unique id on its own ATS
    company: str
    ats: str
    title: str
    location: str | None
    url: str
    department: str | None = None
    posted_at: str | None = None  # left as a raw string; formats differ per ATS
    description: str | None = None  # plain text; None means not fetched yet (see jobs needing descriptions)


def _html_to_text(raw_html: str) -> str:
    """Strip tags and collapse whitespace. Unescaping first matters for
    Greenhouse, whose `content` field is HTML-entity-escaped (&lt;p&gt;)
    on top of being HTML — verified live, not assumed."""
    unescaped = html.unescape(raw_html)
    text = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_greenhouse(company: Company, client: httpx.Client) -> list[Job]:
    # content=true adds the full job description to this SAME list call —
    # no extra requests, unlike Workday (see _fetch_workday_description).
    url = company.board_url + ("&" if "?" in company.board_url else "?") + "content=true"
    data = client.get(url, timeout=10.0).json()
    jobs = []
    for raw in data.get("jobs", []):
        content = raw.get("content")
        jobs.append(
            Job(
                external_id=str(raw["id"]),
                company=company.name,
                ats="greenhouse",
                title=raw["title"],
                location=(raw.get("location") or {}).get("name"),
                url=raw["absolute_url"],
                posted_at=raw.get("first_published"),
                description=_html_to_text(content) if content else None,
            )
        )
    return jobs


def _fetch_lever(company: Company, client: httpx.Client) -> list[Job]:
    data = client.get(company.board_url, timeout=10.0).json()
    jobs = []
    for raw in data:
        categories = raw.get("categories") or {}
        # descriptionPlain duplicates openingPlain in Lever's own data (verified
        # live) — combine opening + body + additional instead, to avoid double-counting.
        description_parts = [
            raw.get("openingPlain") or "",
            raw.get("descriptionBodyPlain") or "",
            raw.get("additionalPlain") or "",
        ]
        description = "\n\n".join(p for p in description_parts if p) or None
        jobs.append(
            Job(
                external_id=raw["id"],
                company=company.name,
                ats="lever",
                title=raw["text"],
                location=categories.get("location"),
                department=categories.get("team"),
                url=raw["hostedUrl"],
                posted_at=str(raw.get("createdAt", "")) or None,
                description=description,
            )
        )
    return jobs


def _fetch_ashby(company: Company, client: httpx.Client) -> list[Job]:
    data = client.get(company.board_url, timeout=10.0).json()
    jobs = []
    for raw in data.get("jobs", []):
        jobs.append(
            Job(
                external_id=raw["id"],
                company=company.name,
                ats="ashby",
                title=raw["title"].strip(),
                location=raw.get("location"),
                department=raw.get("department"),
                url=raw.get("jobUrl", ""),
                posted_at=raw.get("publishedAt"),
                description=raw.get("descriptionPlain"),
            )
        )
    return jobs


def _fetch_workday(company: Company, client: httpx.Client) -> list[Job]:
    # company.slug is "{tenant}/{site}"; job URLs need the site name
    # prefixed on the host, e.g. https://tenant.wd5.myworkdayjobs.com/SITE/job/...
    _, site = company.slug.split("/", 1)
    host = urlparse(company.board_url).netloc
    base_url = f"https://{host}/{site}"

    jobs = []
    limit = 20  # Workday rejects anything higher than 20 with a 400 — found by testing, undocumented
    offset = 0
    total: int | None = None  # only reliable on the first page — later pages report 0, found by testing
    while True:
        body = {"limit": limit, "offset": offset, "appliedFacets": {}, "searchText": ""}
        response = client.post(company.board_url, json=body, timeout=10.0)

        if response.status_code == 429:
            # Observed live against a large company (NVIDIA, ~2000 jobs = ~100
            # paginated requests): Workday sits behind Cloudflare, and its rate
            # limiter blocks for well over 10 seconds once tripped — a 3s retry
            # wasn't enough in testing. One longer retry is given; a second
            # failure means something is actually wrong, so it's raised loudly
            # rather than retried forever.
            time.sleep(15.0)
            response = client.post(company.board_url, json=body, timeout=10.0)

        if response.status_code != 200:
            raise RuntimeError(
                f"Workday API returned {response.status_code} for {company.name} "
                f"(unofficial endpoint — it may have changed shape or rate-limited us): "
                f"{response.text[:200]}"
            )
        data = response.json()
        if total is None:
            total = data.get("total", 0)
        postings = data.get("jobPostings", [])
        if not postings:
            break
        for raw in postings:
            bullet_fields = raw.get("bulletFields") or []
            external_id = bullet_fields[0] if bullet_fields else raw["externalPath"]
            jobs.append(
                Job(
                    external_id=external_id,
                    company=company.name,
                    ats="workday",
                    title=raw["title"],
                    location=raw.get("locationsText"),
                    url=base_url + raw["externalPath"],
                    posted_at=raw.get("postedOn"),
                )
            )
        offset += limit
        if offset >= total:
            break
        time.sleep(0.5)  # space out requests so large companies don't trip the rate limit
    return jobs


def fetch_workday_description(job: Job, company: Company, client: httpx.Client) -> str | None:
    """Fetch one Workday job's full description.

    Unlike the other three ATS types, Workday's list endpoint never
    includes description text — getting it costs one extra request PER
    JOB. Call this only for jobs that already survived a cheaper filter
    (see funnel.py), not for every job in a large company's list.
    """
    _, site = company.slug.split("/", 1)
    host = urlparse(company.board_url).netloc
    base_url = f"https://{host}/{site}"
    external_path = job.url[len(base_url) :]
    detail_url = company.board_url.removesuffix("/jobs") + external_path

    response = client.get(detail_url, timeout=10.0)
    if response.status_code != 200:
        raise RuntimeError(
            f"Workday detail API returned {response.status_code} for {job.title!r} at {company.name}"
        )
    description_html = (response.json().get("jobPostingInfo") or {}).get("jobDescription")
    return _html_to_text(description_html) if description_html else None


_FETCHERS = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
    "workday": _fetch_workday,
}


def dedup_jobs(jobs: list[Job]) -> list[Job]:
    """Drop exact duplicate postings (same company + external_id), keeping the first."""
    seen: set[tuple[str, str]] = set()
    deduped = []
    for job in jobs:
        key = (job.company, job.external_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def fetch_jobs(company: Company, client: httpx.Client | None = None) -> list[Job]:
    """Fetch and normalize every open job for one watchlisted company."""
    fetcher = _FETCHERS.get(company.ats or "")
    if fetcher is None:
        raise ValueError(f"No fetcher for ATS {company.ats!r} (company: {company.name})")

    owns_client = client is None
    client = client or httpx.Client()
    try:
        return dedup_jobs(fetcher(company, client))
    finally:
        if owns_client:
            client.close()
