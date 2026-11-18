from job_agent.scoring import load_scored_results, record_score, save_scored_results, ScoredJob


def test_record_score_persists_and_is_keyed_by_company_and_external_id(tmp_path):
    path = tmp_path / "scored.json"

    record_score(
        company="Stripe", external_id="1", title="PM", url="u",
        job_score=85, criteria_known="4 of 5", work_mode="Hybrid, Austin, TX",
        overrides=[], notes=[], recommendation="Strong", path=path,
    )

    results = load_scored_results(path)
    assert "Stripe::1" in results
    assert results["Stripe::1"].job_score == 85
    assert results["Stripe::1"].recommendation == "Strong"


def test_record_score_supports_no_score_case(tmp_path):
    path = tmp_path / "scored.json"

    scored = record_score(
        company="X", external_id="1", title="PM", url="u",
        job_score=None, criteria_known="0 of 5", work_mode="unknown",
        overrides=[], notes=["not enough information"], recommendation="not enough information", path=path,
    )

    assert scored.job_score is None
    assert load_scored_results(path)["X::1"].job_score is None


def test_record_score_overwrites_a_previous_score_for_the_same_job(tmp_path):
    path = tmp_path / "scored.json"
    record_score(company="X", external_id="1", title="PM", url="u", job_score=50,
                  criteria_known="3 of 5", work_mode="unknown", overrides=[], notes=[],
                  recommendation="Maybe", path=path)

    record_score(company="X", external_id="1", title="PM", url="u", job_score=90,
                  criteria_known="5 of 5", work_mode="Remote (US)", overrides=[], notes=[],
                  recommendation="Strong", path=path)

    results = load_scored_results(path)
    assert len(results) == 1
    assert results["X::1"].job_score == 90


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "scored.json"
    scored = ScoredJob(company="X", external_id="1", title="PM", url="u", job_score=75,
                        criteria_known="4 of 5", work_mode="Remote (US)", overrides=["dealbreaker"],
                        notes=["sponsorship not mentioned"], recommendation="Strong", scored_at="2026-01-01T00:00:00+00:00")

    save_scored_results({"X::1": scored}, path)

    assert load_scored_results(path) == {"X::1": scored}
