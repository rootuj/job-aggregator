"""The entry point launchd actually calls: run the pipeline once and log
a one-line summary. Run it manually any time with `uv run job-agent-daily`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from job_agent.pipeline import run_pipeline


def main() -> None:
    summary = run_pipeline()
    timestamp = datetime.now(timezone.utc).isoformat()
    print(
        f"[{timestamp}] {summary['companies_checked']} companies checked, "
        f"{summary['candidates_found']} candidates found, "
        f"{len(summary['errors'])} errors, "
        f"{len(summary['pruned_stale_scores'])} stale scores pruned"
    )
    for error in summary["errors"]:
        print(f"  ERROR: {error}")
    for title in summary["pruned_stale_scores"]:
        print(f"  PRUNED: {title}")


if __name__ == "__main__":
    main()
