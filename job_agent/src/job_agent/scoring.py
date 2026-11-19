"""Store Job Score results the model computes from rubric.md.

Job Score itself is never computed in code (see CLAUDE.md) — this module
only persists what the model reports, keyed by (company, external_id),
ready for the dashboard to read.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SCORED_RESULTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "scored_results.json"


@dataclass
class ScoredJob:
    company: str
    external_id: str
    title: str
    url: str
    job_score: int | None  # None means "not enough information" (see rubric.md)
    criteria_known: str  # e.g. "4 of 5"
    work_mode: str
    overrides: list[str]
    notes: list[str]
    recommendation: str  # "Strong", "Maybe", "Skip", or "not enough information"
    scored_at: str


def _key(company: str, external_id: str) -> str:
    return f"{company}::{external_id}"


def load_scored_results(path: Path = DEFAULT_SCORED_RESULTS_PATH) -> dict[str, ScoredJob]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {key: ScoredJob(**fields) for key, fields in raw.items()}


def save_scored_results(results: dict[str, ScoredJob], path: Path = DEFAULT_SCORED_RESULTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: asdict(r) for key, r in results.items()}, indent=2))


def record_score(
    company: str,
    external_id: str,
    title: str,
    url: str,
    job_score: int | None,
    criteria_known: str,
    work_mode: str,
    overrides: list[str],
    notes: list[str],
    recommendation: str,
    path: Path = DEFAULT_SCORED_RESULTS_PATH,
) -> ScoredJob:
    """Record one job's Job Score result (the model already computed it)."""
    results = load_scored_results(path)
    scored = ScoredJob(
        company=company,
        external_id=external_id,
        title=title,
        url=url,
        job_score=job_score,
        criteria_known=criteria_known,
        work_mode=work_mode,
        overrides=overrides,
        notes=notes,
        recommendation=recommendation,
        scored_at=datetime.now(timezone.utc).isoformat(),
    )
    results[_key(company, external_id)] = scored
    save_scored_results(results, path)
    return scored


def prune_stale_scores(
    current_candidates: list[dict], path: Path = DEFAULT_SCORED_RESULTS_PATH
) -> list[str]:
    """Remove scored jobs that are no longer in the current candidate pool
    — whether because the job actually closed, or it simply didn't rank
    into today's top N. Found live: a scored job can otherwise sit on the
    dashboard forever, since nothing else ever removes it, even after a
    Funnel fix makes clear it never should have been a candidate at all.

    Call this after writing a fresh pending_scoring.json (pipeline.py
    does, on every run) so "today's matches" actually means today's.
    Returns the titles of whatever got pruned.
    """
    results = load_scored_results(path)
    current_keys = {_key(c["company"], c["external_id"]) for c in current_candidates}

    stale_keys = [key for key in results if key not in current_keys]
    pruned_titles = [results[key].title for key in stale_keys]
    for key in stale_keys:
        del results[key]

    if stale_keys:
        save_scored_results(results, path)
    return pruned_titles
