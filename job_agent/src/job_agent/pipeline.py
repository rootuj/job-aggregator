"""Ties the engine together into one run: for every watchlisted company,
fetch jobs, diff against yesterday, and funnel down to top candidates.

Writes job_agent/data/pending_scoring.json — candidates with Fit Quotient
but no Job Score yet. Job Score itself is NOT computed here; it's the
model's job, following rubric.md (see mcp_server.py's score_job tool).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import httpx

from job_agent.funnel import load_profile, load_resumes, run_funnel
from job_agent.jobs import fetch_jobs
from job_agent.scoring import DEFAULT_SCORED_RESULTS_PATH, prune_stale_scores
from job_agent.tracking import diff_jobs, load_state, save_state
from job_agent.watchlist import load_watchlist

DEFAULT_PENDING_SCORING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "pending_scoring.json"


def run_pipeline(
    top_n_per_company: int = 20,
    pending_path: Path = DEFAULT_PENDING_SCORING_PATH,
    scored_path: Path = DEFAULT_SCORED_RESULTS_PATH,
) -> dict:
    """Run the full pipeline across every watchlisted company.

    Returns a summary dict; writes the candidate list awaiting Job Score
    to `pending_path`.
    """
    profile = load_profile()
    resumes = load_resumes()
    companies = load_watchlist()

    candidates = []
    errors = []
    with httpx.Client() as client:
        for company in companies:
            if not company.ats:
                errors.append(f"{company.name}: no ATS detected, skipped")
                continue
            try:
                jobs = fetch_jobs(company, client=client)
            except (httpx.HTTPError, RuntimeError) as exc:
                errors.append(f"{company.name}: fetch failed — {exc}")
                continue

            previous_state = load_state(company.name)
            new_state, changes = diff_jobs(company.name, jobs, previous_state)
            save_state(company.name, new_state)
            changes_by_id = {c.job.external_id: c for c in changes}

            top = run_funnel(company, jobs, profile, resumes, client, top_n=top_n_per_company)
            for job, best_resume, fit_quotient in top:
                change = changes_by_id.get(job.external_id)
                candidates.append(
                    {
                        **asdict(job),
                        "best_resume": best_resume,
                        "fit_quotient": fit_quotient,
                        "change": change.change if change else "unchanged",
                        "repost_count": change.repost_count if change else 0,
                        "age_days": change.age_days if change else 0,
                    }
                )

    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(candidates, indent=2))

    pruned = prune_stale_scores(candidates, path=scored_path)

    return {
        "companies_checked": len(companies),
        "candidates_found": len(candidates),
        "errors": errors,
        "pending_scoring_path": str(pending_path),
        "pruned_stale_scores": pruned,
    }
