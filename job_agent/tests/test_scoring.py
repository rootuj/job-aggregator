from job_agent.scoring import load_scored_results, prune_stale_scores, record_score, save_scored_results, ScoredJob


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


def test_prune_stale_scores_removes_jobs_no_longer_in_the_candidate_pool(tmp_path):
    path = tmp_path / "scored.json"
    record_score(company="Stripe", external_id="1", title="Stale Sales Role", url="u", job_score=35,
                 criteria_known="3 of 5", work_mode="unknown", overrides=[], notes=[],
                 recommendation="Skip", path=path)
    record_score(company="Ramp", external_id="2", title="Still Current PM Role", url="u", job_score=70,
                 criteria_known="4 of 5", work_mode="unknown", overrides=[], notes=[],
                 recommendation="Maybe", path=path)

    pruned_titles = prune_stale_scores([{"company": "Ramp", "external_id": "2"}], path=path)

    assert pruned_titles == ["Stale Sales Role"]
    remaining = load_scored_results(path)
    assert set(remaining.keys()) == {"Ramp::2"}


def test_prune_stale_scores_keeps_everything_still_current(tmp_path):
    path = tmp_path / "scored.json"
    record_score(company="X", external_id="1", title="Still Here", url="u", job_score=80,
                 criteria_known="5 of 5", work_mode="unknown", overrides=[], notes=[],
                 recommendation="Strong", path=path)

    pruned = prune_stale_scores([{"company": "X", "external_id": "1"}], path=path)

    assert pruned == []
    assert len(load_scored_results(path)) == 1


def test_prune_stale_scores_is_a_noop_with_no_scores_yet(tmp_path):
    path = tmp_path / "scored.json"  # file doesn't exist
    assert prune_stale_scores([{"company": "X", "external_id": "1"}], path=path) == []
