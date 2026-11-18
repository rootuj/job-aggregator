import json

import pytest
import yaml
from fastapi.testclient import TestClient

import dashboard.main as main_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(main_module, "SCORED_RESULTS_PATH", tmp_path / "scored_results.json")
    monkeypatch.setattr(main_module, "PENDING_SCORING_PATH", tmp_path / "pending_scoring.json")
    return TestClient(main_module.app)


def test_index_with_no_data_shows_empty_state(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "No scored jobs yet" in response.text


def test_index_shows_pending_count(client):
    main_module.PENDING_SCORING_PATH.write_text(json.dumps([{"title": "A"}, {"title": "B"}]))

    response = client.get("/")

    assert "2 jobs fetched but not scored yet" in response.text


def test_index_sorts_strong_before_maybe_before_skip(client):
    scored = {
        "a": {"company": "X", "external_id": "1", "title": "Skip Job", "url": "u", "job_score": 10,
              "criteria_known": "5 of 5", "work_mode": "unknown", "overrides": [], "notes": [],
              "recommendation": "Skip", "scored_at": "t"},
        "b": {"company": "X", "external_id": "2", "title": "Strong Job", "url": "u", "job_score": 90,
              "criteria_known": "5 of 5", "work_mode": "unknown", "overrides": [], "notes": [],
              "recommendation": "Strong", "scored_at": "t"},
    }
    main_module.SCORED_RESULTS_PATH.write_text(json.dumps(scored))

    response = client.get("/")

    assert response.text.index("Strong Job") < response.text.index("Skip Job")


def test_settings_page_shows_existing_profile_values(client):
    main_module.PROFILE_PATH.write_text(yaml.safe_dump({"name": "Test User", "target_titles": ["Engineer"]}))

    response = client.get("/settings")

    assert "Test User" in response.text
    assert "Engineer" in response.text


def test_settings_page_with_no_profile_shows_empty_form(client):
    response = client.get("/settings")
    assert response.status_code == 200


def test_saving_settings_writes_profile_yaml(client):
    response = client.post("/settings", data={
        "name": "Rootu Joshi",
        "target_titles": "Principal Product Manager\nHead of Product",
        "seniority_levels": "Senior\nPrincipal",
        "industries_or_lanes": "Fintech",
        "locations_ranked": "Remote (US)",
        "locations_exclude": "Hybrid or on-site outside the US",
        "comp_floor_usd": "200000",
        "must_haves": "Clear path to promotion",
        "dealbreakers": "Unpaid trial work",
    }, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/settings"

    saved = yaml.safe_load(main_module.PROFILE_PATH.read_text())
    assert saved["name"] == "Rootu Joshi"
    assert saved["target_titles"] == ["Principal Product Manager", "Head of Product"]
    assert saved["locations"]["ranked"] == ["Remote (US)"]
    assert saved["locations"]["exclude"] == ["Hybrid or on-site outside the US"]
    assert saved["comp_floor_usd"] == 200000
    assert saved["needs_visa_sponsorship"] is False
    assert saved["resumes_folder"] == "my-job-search/resumes/"


def test_saving_settings_with_empty_comp_floor_saves_none(client):
    response = client.post("/settings", data={"comp_floor_usd": ""}, follow_redirects=False)
    assert response.status_code == 303
    saved = yaml.safe_load(main_module.PROFILE_PATH.read_text())
    assert saved["comp_floor_usd"] is None


def test_saving_settings_checks_the_visa_sponsorship_box(client):
    response = client.post("/settings", data={"needs_visa_sponsorship": "on"}, follow_redirects=False)
    assert response.status_code == 303
    saved = yaml.safe_load(main_module.PROFILE_PATH.read_text())
    assert saved["needs_visa_sponsorship"] is True
