"""Paths to the engine's output files.

The dashboard only ever reads/writes these files directly — it never
imports job_agent's Python code, so the engine and dashboard stay
decoupled (see PLAN.md's Architecture: "hosting-ready but not
hosting-built"). Override via environment variables if this project
layout ever changes.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

PROFILE_PATH = Path(os.environ.get("JOB_AGGREGATOR_PROFILE_PATH", PROJECT_ROOT / "profile.yaml"))
SCORED_RESULTS_PATH = Path(
    os.environ.get("JOB_AGGREGATOR_SCORED_RESULTS_PATH", PROJECT_ROOT / "job_agent" / "data" / "scored_results.json")
)
PENDING_SCORING_PATH = Path(
    os.environ.get("JOB_AGGREGATOR_PENDING_SCORING_PATH", PROJECT_ROOT / "job_agent" / "data" / "pending_scoring.json")
)
