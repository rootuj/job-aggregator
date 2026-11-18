#!/bin/bash
# Sets up Job Aggregator: installs both projects' dependencies and
# schedules the daily 9am run. Run this once: `./install.sh`.
set -euo pipefail

cd "$(dirname "$0")"

echo "Installing Job Aggregator..."
echo

if ! command -v uv &> /dev/null; then
    echo "uv is required but isn't installed."
    echo "Install it from https://docs.astral.sh/uv/ and run this script again."
    exit 1
fi

echo "Setting up the engine (job_agent)..."
(cd job_agent && uv sync)
echo

echo "Setting up the dashboard..."
(cd dashboard && uv sync)
echo

echo "Scheduling the daily 9am run..."
(cd job_agent && uv run job-agent-install-scheduler)
echo

echo "Done. Here's what's set up:"
echo "  - The pipeline (fetch jobs, Fit Quotient) runs automatically every day at 9:00am."
echo "  - To see your matches: cd dashboard && uv run dashboard, then open http://localhost:8420"
echo "  - Edit your preferences any time from the dashboard's Settings tab."
echo "  - Job Score still needs Claude — ask Claude to score the pending jobs whenever you check in."
echo "  - To remove the daily schedule later: cd job_agent && uv run job-agent-uninstall-scheduler"
