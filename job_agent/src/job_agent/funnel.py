"""The Funnel: narrow raw fetched jobs down to the ones worth a full,
model-driven Job Score.

Two code-only stages, in order:
1. A cheap title pre-filter against profile.yaml's target_titles — cuts
   the list down using only data we already have (title/location), no
   extra network calls. This exists mainly to control cost: Workday's
   full job description costs one extra request PER job (see
   jobs.fetch_workday_description), so filtering by title FIRST avoids
   doing that for jobs that are obviously irrelevant.
2. Fit Quotient: a resume/JD keyword-overlap percentage, computed only
   for jobs that survived stage 1. The top ~N by Fit Quotient move on to
   Job Score, which the model computes itself from rubric.md — not here.

Location filtering is deliberately NOT done here. rubric.md's own
"Location rules" require judgment (e.g. telling whether a remote job is
actually restricted to a non-US country) that simple code can't reliably
make — that stays with the model, at Job Score time.
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


def load_resume_keywords(resumes_dir: Path = DEFAULT_RESUMES_DIR) -> set[str]:
    """The union of significant words across every resume .md copy.

    Picking the single BEST-matching resume per job is step 8's job, not
    this one — for now, Fit Quotient uses whatever any resume mentions.
    """
    keywords: set[str] = set()
    for path in resumes_dir.glob("*.md"):
        text = path.read_text()
        lines = text.split("\n", 1)
        if lines[0].startswith("<!-- Copy of"):
            text = lines[1] if len(lines) > 1 else ""
        keywords |= _words(text)
    return keywords


def fit_quotient(resume_keywords: set[str], job: Job) -> float | None:
    """% of the resume's significant words that also appear in this job's
    description. None if there's no description to compare against."""
    if not job.description or not resume_keywords:
        return None
    job_words = _words(job.description)
    overlap = resume_keywords & job_words
    return round(100 * len(overlap) / len(resume_keywords), 1)


def run_funnel(
    company: Company,
    jobs: list[Job],
    profile: dict,
    resume_keywords: set[str],
    client: httpx.Client,
    top_n: int = 20,
) -> list[tuple[Job, float]]:
    """Title pre-filter -> backfill descriptions -> Fit Quotient -> top N.

    Returns (job, fit_quotient) pairs, highest score first. A job with no
    description (Fit Quotient None) sorts last, never padding the results.
    """
    survivors = prefilter_by_title(jobs, profile.get("target_titles") or [])
    survivors = [ensure_description(job, company, client) for job in survivors]

    scored = [(job, fit_quotient(resume_keywords, job)) for job in survivors]
    scored.sort(key=lambda pair: (pair[1] is None, -(pair[1] or 0)))
    return scored[:top_n]
