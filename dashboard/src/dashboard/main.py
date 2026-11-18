"""The Dashboard: a thin local web app that only reads/writes the engine's
output files (scored_results.json, profile.yaml) — no pipeline logic
lives here. Run with `uv run dashboard` from the dashboard/ folder.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.config import PENDING_SCORING_PATH, PROFILE_PATH, SCORED_RESULTS_PATH

_HERE = Path(__file__).resolve().parent

app = FastAPI(title="Job Aggregator Dashboard")
templates = Jinja2Templates(directory=str(_HERE / "templates"))
app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

_RECOMMENDATION_RANK = {"Strong": 0, "Maybe": 1, "Skip": 2, "not enough information": 3}


def _load_scored_jobs() -> list[dict]:
    if not SCORED_RESULTS_PATH.exists():
        return []
    raw = json.loads(SCORED_RESULTS_PATH.read_text())
    jobs = list(raw.values())
    jobs.sort(key=lambda j: (_RECOMMENDATION_RANK.get(j["recommendation"], 4), -(j["job_score"] or -1)))
    return jobs


def _pending_count() -> int:
    if not PENDING_SCORING_PATH.exists():
        return 0
    return len(json.loads(PENDING_SCORING_PATH.read_text()))


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"jobs": _load_scored_jobs(), "pending_count": _pending_count()}
    )


def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    return yaml.safe_load(PROFILE_PATH.read_text()) or {}


def _lines_to_list(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


@app.get("/settings")
def settings_page(request: Request):
    profile = _load_profile()
    return templates.TemplateResponse(request, "settings.html", {"profile": profile, "saved": False})


@app.post("/settings")
def save_settings(
    request: Request,
    name: str = Form(""),
    target_titles: str = Form(""),
    seniority_levels: str = Form(""),
    industries_or_lanes: str = Form(""),
    locations_ranked: str = Form(""),
    locations_exclude: str = Form(""),
    needs_visa_sponsorship: bool = Form(False),
    comp_floor_usd: str = Form(""),
    must_haves: str = Form(""),
    dealbreakers: str = Form(""),
):
    profile = _load_profile()
    profile["name"] = name.strip()
    profile["target_titles"] = _lines_to_list(target_titles)
    profile["seniority_levels"] = _lines_to_list(seniority_levels)
    profile["industries_or_lanes"] = _lines_to_list(industries_or_lanes)
    profile["locations"] = {
        "ranked": _lines_to_list(locations_ranked),
        "exclude": _lines_to_list(locations_exclude),
    }
    profile["needs_visa_sponsorship"] = needs_visa_sponsorship
    profile["comp_floor_usd"] = int(comp_floor_usd) if comp_floor_usd.strip() else None
    profile["must_haves"] = _lines_to_list(must_haves)
    profile["dealbreakers"] = _lines_to_list(dealbreakers)
    profile.setdefault("resumes_folder", "my-job-search/resumes/")

    PROFILE_PATH.write_text(yaml.safe_dump(profile, sort_keys=False))
    return RedirectResponse(url="/settings", status_code=303)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8420)


if __name__ == "__main__":
    main()
