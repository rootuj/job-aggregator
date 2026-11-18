"""The job_agent MCP server.

Exposes the engine's capabilities as tools an MCP-aware client (like
Claude) can call directly, instead of you running Python by hand.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from job_agent import resume_copies
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


@mcp.tool()
def check_resumes() -> dict:
    """Check the resumes folder for bookkeeping that needs doing:
    PDF/Word resumes with no Markdown copy, stale copies (original edited
    since its copy was made), new resumes not yet summarized to the user,
    and orphaned copies whose original is gone. For each PDF/Word resume
    needing a copy, read it and call save_resume_copy with the Markdown
    you produce — don't do the copying yourself in code.
    """
    return asdict(resume_copies.scan_resumes())


@mcp.tool()
def save_resume_copy(original_filename: str, markdown_body: str) -> str:
    """Save a Markdown copy of a PDF/Word resume you just read. Refuses to
    overwrite a Markdown file that isn't already one of the job agent's
    own copies. Returns the path written."""
    return str(resume_copies.save_resume_copy(original_filename, markdown_body))


@mcp.tool()
def mark_resume_known(name: str) -> None:
    """Record that a resume has been read and summarized for the user,
    so it isn't flagged as new again next time."""
    resume_copies.mark_resume_known(name)


@mcp.tool()
def delete_orphaned_resume_copy(original_name: str) -> None:
    """Delete a leftover copy whose original resume no longer exists.
    Only call this after the user says yes — never on your own."""
    resume_copies.delete_orphaned_copy(original_name)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
