"""The job_agent MCP server.

Exposes the engine's capabilities as tools an MCP-aware client (like
Claude) can call directly, instead of you running Python by hand.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from job_agent.pipeline import DEFAULT_PENDING_SCORING_PATH, run_pipeline
from job_agent.scoring import record_score
from job_agent.watchlist import Company, add_company, load_watchlist

mcp = MCPServer("job-agent")


@mcp.tool()
def watchlist_add(name: str, careers_url: str) -> dict:
    """Add a company to the watchlist, detecting its ATS (Greenhouse/Lever/Ashby)."""
    company: Company = add_company(name, careers_url)
    return asdict(company)


@mcp.tool()
def watchlist_list() -> list[dict]:
    """List every company currently on the watchlist."""
    return [asdict(c) for c in load_watchlist()]


@mcp.tool()
def run_daily_pipeline() -> dict:
    """Fetch jobs for every watchlisted company, diff against yesterday, and
    funnel down to top candidates (by Fit Quotient). Writes candidates
    awaiting Job Score to disk and returns a summary."""
    return run_pipeline()


@mcp.tool()
def get_pending_scoring() -> list[dict]:
    """List candidates awaiting Job Score — read rubric.md and profile.yaml,
    then score each one and call score_job to record the result."""
    if not DEFAULT_PENDING_SCORING_PATH.exists():
        return []
    return json.loads(DEFAULT_PENDING_SCORING_PATH.read_text())


@mcp.tool()
def score_job(
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
) -> dict:
    """Record one job's Job Score, computed by following rubric.md exactly.

    job_score is None when rubric.md says "not enough information" (all 5
    criteria unknown). criteria_known is e.g. "4 of 5". recommendation is
    "Strong", "Maybe", "Skip", or "not enough information".
    """
    scored = record_score(
        company=company, external_id=external_id, title=title, url=url,
        job_score=job_score, criteria_known=criteria_known, work_mode=work_mode,
        overrides=overrides, notes=notes, recommendation=recommendation,
    )
    return asdict(scored)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
