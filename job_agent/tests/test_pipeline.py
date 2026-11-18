import json

import job_agent.pipeline as pipeline_module
from job_agent.jobs import Job
from job_agent.watchlist import Company


def _setup_common(monkeypatch, target_titles=None, resumes=None):
    monkeypatch.setattr(pipeline_module, "load_profile", lambda: {"target_titles": target_titles or []})
    monkeypatch.setattr(pipeline_module, "load_resumes", lambda: resumes or {})
    monkeypatch.setattr(pipeline_module, "load_state", lambda name: {})
    monkeypatch.setattr(pipeline_module, "save_state", lambda name, state: None)


def test_run_pipeline_writes_candidates_with_change_and_fit_info(tmp_path, monkeypatch):
    company = Company(name="X", careers_url="x", ats="greenhouse", slug="x", board_url="u")
    job = Job(external_id="1", company="X", ats="greenhouse", title="Engineer", location=None,
              url="u1", description="python")

    _setup_common(monkeypatch, resumes={"a.md": {"python"}})
    monkeypatch.setattr(pipeline_module, "load_watchlist", lambda: [company])
    monkeypatch.setattr(pipeline_module, "fetch_jobs", lambda company, client=None: [job])

    pending_path = tmp_path / "pending.json"
    summary = pipeline_module.run_pipeline(top_n_per_company=5, pending_path=pending_path)

    assert summary == {
        "companies_checked": 1,
        "candidates_found": 1,
        "errors": [],
        "pending_scoring_path": str(pending_path),
    }
    data = json.loads(pending_path.read_text())
    assert data[0]["title"] == "Engineer"
    assert data[0]["change"] == "new"
    assert data[0]["best_resume"] == "a.md"
    assert data[0]["fit_quotient"] == 100.0
    assert data[0]["repost_count"] == 0
    assert data[0]["age_days"] == 0


def test_run_pipeline_skips_companies_with_no_ats_detected(tmp_path, monkeypatch):
    company = Company(name="Mystery", careers_url="x", ats=None, slug=None, board_url=None)
    _setup_common(monkeypatch)
    monkeypatch.setattr(pipeline_module, "load_watchlist", lambda: [company])

    summary = pipeline_module.run_pipeline(pending_path=tmp_path / "pending.json")

    assert summary["companies_checked"] == 1
    assert summary["candidates_found"] == 0
    assert "Mystery" in summary["errors"][0]


def test_run_pipeline_keeps_going_after_one_companys_fetch_fails(tmp_path, monkeypatch):
    broken = Company(name="Broken", careers_url="x", ats="greenhouse", slug="b", board_url="u")
    working = Company(name="Working", careers_url="x", ats="greenhouse", slug="w", board_url="u2")
    job = Job(external_id="1", company="Working", ats="greenhouse", title="Engineer", location=None,
              url="u1", description="python")

    _setup_common(monkeypatch, resumes={"a.md": {"python"}})
    monkeypatch.setattr(pipeline_module, "load_watchlist", lambda: [broken, working])

    def fake_fetch(company, client=None):
        if company.name == "Broken":
            raise RuntimeError("boom")
        return [job]

    monkeypatch.setattr(pipeline_module, "fetch_jobs", fake_fetch)

    summary = pipeline_module.run_pipeline(pending_path=tmp_path / "pending.json")

    assert summary["companies_checked"] == 2
    assert summary["candidates_found"] == 1
    assert "Broken" in summary["errors"][0]
