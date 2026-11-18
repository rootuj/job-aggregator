"""The Funnel: narrow raw fetched jobs down to the ones worth a full,
model-driven Job Score.

Two code-only stages, in order:
1. A cheap title pre-filter against profile.yaml's target_titles — cuts
   the list down using only data we already have (title/location), no
   extra network calls. This exists mainly to control cost: Workday's
   full job description costs one extra request PER job (see
   jobs.fetch_workday_description), so filtering by title FIRST avoids
   doing that for jobs that are obviously irrelevant.
2. Ranking: the top ~N candidates move on to Job Score, which the model
   computes itself from rubric.md — not here. Found live (NVIDIA... no,
   Stripe): ranking by Fit Quotient alone is a bad proxy for "worth
   scoring" — it has zero awareness of title precision or location, so
   an irrelevant "Head of AMER Startups (AI Sales)" (fit 31.6, shares
   only the generic word "Head" with target_titles) outranked 35+ of 42
   genuine, several explicitly remote, Product Manager roles (fit 12-30)
   and NONE of those 35+ survived the cutoff. The combined rank below
   blends Fit Quotient with title-match STRENGTH (word-overlap count,
   not just "shares one word") and a location-rank bonus, so a job
   matching your title and your #1 location can't be buried by one that
   merely shares a generic word and happens to score slightly higher on
   keyword overlap.

Full location EXCLUSION is still deliberately NOT done here. rubric.md's
own "Location rules" require judgment (e.g. telling whether a remote job
is actually restricted to a non-US country) that simple code can't
reliably make — that stays with the model, at Job Score time. The bonus
below is a rough ranking aid, not that final judgment.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import yaml

from job_agent.jobs import Job, fetch_workday_description
from job_agent.watchlist import Company

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "profile.yaml"
DEFAULT_RESUMES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "my-job-search" / "resumes"

_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "but", "by", "for", "from", "has", "have",
    "if", "in", "into", "is", "it", "not", "of", "on", "or", "our", "over", "per",
    "so", "than", "that", "the", "their", "then", "this", "to", "under", "we",
    "will", "with", "your", "you",
}


def _words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


def title_matches(job_title: str, target_titles: list[str]) -> bool:
    """A job's title overlaps at least one meaningful word with any target title.

    Deliberately lenient: this is a cost-control pre-filter, not the real
    judgment call — missing a real match here is worse than fetching a
    few extra descriptions that turn out irrelevant.
    """
    job_words = _words(job_title)
    if not job_words:
        return True  # no title text to judge — don't silently drop it
    return any(job_words & _words(target) for target in target_titles)


def prefilter_by_title(jobs: list[Job], target_titles: list[str]) -> list[Job]:
    if not target_titles:
        return jobs  # an empty profile field means this filter doesn't apply
    return [job for job in jobs if title_matches(job.title, target_titles)]


def ensure_description(job: Job, company: Company, client: httpx.Client) -> Job:
    """Fill in `description` for a job that doesn't have one yet.

    Greenhouse/Lever/Ashby jobs already have it from the list fetch — this
    is a no-op for them. Only Workday jobs need the extra per-job request.
    """
    if job.description is not None:
        return job
    if job.ats != "workday":
        return job
    description = fetch_workday_description(job, company, client)
    return Job(**{**job.__dict__, "description": description})


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"No profile at {path} — run setup first (see setup_questions.md)")
    return yaml.safe_load(path.read_text()) or {}


def load_resumes(resumes_dir: Path = DEFAULT_RESUMES_DIR) -> dict[str, set[str]]:
    """Each resume .md copy's significant words, keyed by filename.

    Kept per-resume (not pooled) so Fit Quotient can report which SPECIFIC
    resume fits a job best — step 8's "best-resume pick" — rather than a
    single score blended across every resume you have.
    """
    resumes: dict[str, set[str]] = {}
    for path in resumes_dir.glob("*.md"):
        text = path.read_text()
        lines = text.split("\n", 1)
        if lines[0].startswith("<!-- Copy of"):
            text = lines[1] if len(lines) > 1 else ""
        resumes[path.name] = _words(text)
    return resumes


def fit_quotient(resume_keywords: set[str], job: Job) -> float | None:
    """% of one resume's significant words that also appear in this job's
    description. None if there's no description to compare against."""
    if not job.description or not resume_keywords:
        return None
    job_words = _words(job.description)
    overlap = resume_keywords & job_words
    return round(100 * len(overlap) / len(resume_keywords), 1)


def best_fit_quotient(resumes: dict[str, set[str]], job: Job) -> tuple[str | None, float | None]:
    """Fit Quotient against every resume; returns whichever one fits best.

    (None, None) if there's no description or no resumes to compare.
    """
    best_resume: str | None = None
    best_score: float | None = None
    for name, keywords in resumes.items():
        score = fit_quotient(keywords, job)
        if score is not None and (best_score is None or score > best_score):
            best_resume, best_score = name, score
    return best_resume, best_score


def title_match_strength(job_title: str, target_titles: list[str]) -> int:
    """How many meaningful words a job's title shares with its best-matching
    target title — e.g. "Product Manager, Radar" shares 2 words ("product",
    "manager") with "Principal Product Manager", while "Head of AMER
    Startups" shares only 1 ("head") with "Head of Product". Unlike
    title_matches (a yes/no pre-filter), this is a ranking signal."""
    job_words = _words(job_title)
    if not job_words or not target_titles:
        return 0
    return max(len(job_words & _words(target)) for target in target_titles)


_LOCATION_RANK_POINTS = [20, 18, 15, 10]  # same scale as rubric.md's own Location fit scoring
_LOCATION_RANK_POINTS_DEFAULT = 6  # 5th-ranked-or-later match


def location_rank_bonus(location_text: str | None, ranked_locations: list[str]) -> int:
    """A rough ranking bonus from profile.yaml's locations.ranked — NOT the
    full judgment-based Location fit rubric.md computes (which handles
    "remote restricted to another country" etc.); this only exists so a
    job matching your #1 preferred location doesn't get buried in the
    Funnel's ranking before it ever reaches that real judgment call."""
    if not location_text or not ranked_locations:
        return 0
    location_words = _words(location_text)
    is_remote = "remote" in location_text.lower()
    for i, ranked in enumerate(ranked_locations):
        points = _LOCATION_RANK_POINTS[i] if i < len(_LOCATION_RANK_POINTS) else _LOCATION_RANK_POINTS_DEFAULT
        if "remote" in ranked.lower() and is_remote:
            return points
        if _words(ranked) & location_words:
            return points
    return 0


def _funnel_rank(job: Job, fit: float | None, profile: dict) -> float:
    """Combines Fit Quotient with title-match strength and a location
    bonus — see the module docstring for why Fit Quotient alone isn't
    enough. Weights are chosen so a strong title+location match can
    outrank a merely-higher-Fit-Quotient irrelevant job."""
    title_component = title_match_strength(job.title, profile.get("target_titles") or []) * 15
    location_component = location_rank_bonus(job.location, profile.get("locations", {}).get("ranked") or [])
    return (fit or 0) + title_component + location_component


def run_funnel(
    company: Company,
    jobs: list[Job],
    profile: dict,
    resumes: dict[str, set[str]],
    client: httpx.Client,
    top_n: int = 20,
) -> list[tuple[Job, str | None, float | None]]:
    """Title pre-filter -> backfill descriptions -> rank -> top N.

    Returns (job, best_resume, fit_quotient) triples, ranked by a
    combined score (see _funnel_rank), not Fit Quotient alone. A job
    with no description (Fit Quotient None) sorts last, never padding
    the results.
    """
    survivors = prefilter_by_title(jobs, profile.get("target_titles") or [])
    survivors = [ensure_description(job, company, client) for job in survivors]

    scored = [(job, *best_fit_quotient(resumes, job)) for job in survivors]
    scored.sort(key=lambda triple: (triple[2] is None, -_funnel_rank(triple[0], triple[2], profile)))
    return scored[:top_n]
