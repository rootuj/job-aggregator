import httpx

from job_agent.funnel import (
    ensure_description,
    fit_quotient,
    load_profile,
    load_resume_keywords,
    prefilter_by_title,
    run_funnel,
    title_matches,
)
from job_agent.jobs import Job
from job_agent.watchlist import Company
from fakes import FakeClient, FakeResponse


def _job(eid, title, description=None, ats="greenhouse"):
    return Job(external_id=eid, company="X", ats=ats, title=title, location=None, url=f"u{eid}", description=description)


def test_title_matches_on_shared_meaningful_word():
    assert title_matches("Senior Product Manager, Payments", ["Principal Product Manager"])


def test_title_does_not_match_unrelated_title():
    assert not title_matches("Warehouse Associate", ["Principal Product Manager", "Head of Product"])


def test_title_with_no_words_is_not_dropped():
    assert title_matches("", ["Principal Product Manager"])


def test_prefilter_keeps_only_matching_jobs():
    jobs = [_job("1", "Product Manager"), _job("2", "Warehouse Associate")]
    survivors = prefilter_by_title(jobs, ["Principal Product Manager"])
    assert [j.external_id for j in survivors] == ["1"]


def test_prefilter_with_empty_target_titles_keeps_everything():
    jobs = [_job("1", "Anything"), _job("2", "Something else")]
    assert prefilter_by_title(jobs, []) == jobs


def test_fit_quotient_is_percentage_of_resume_words_found_in_description():
    resume_keywords = {"python", "marketplace", "payments", "leadership"}
    job = _job("1", "PM", description="We need someone who knows python and payments.")
    assert fit_quotient(resume_keywords, job) == 50.0


def test_fit_quotient_is_none_without_a_description():
    job = _job("1", "PM", description=None)
    assert fit_quotient({"python"}, job) is None


def test_fit_quotient_is_none_with_no_resume_keywords():
    job = _job("1", "PM", description="python payments")
    assert fit_quotient(set(), job) is None


def test_ensure_description_is_a_noop_for_non_workday_jobs_that_already_have_one():
    job = _job("1", "PM", description="already here", ats="greenhouse")
    company = Company(name="X", careers_url="x", ats="greenhouse", slug="x", board_url="https://x/jobs")
    result = ensure_description(job, company, client=None)  # no client needed — must not be used
    assert result.description == "already here"


def test_ensure_description_backfills_workday_jobs():
    company = Company(name="TestCo", careers_url="x", ats="workday", slug="testco/TestCareers",
                       board_url="https://testco.wd5.myworkdayjobs.com/wday/cxs/testco/TestCareers/jobs")
    job = Job(external_id="1", company="TestCo", ats="workday", title="PM", location=None,
              url="https://testco.wd5.myworkdayjobs.com/TestCareers/job/x_1", description=None)
    detail_url = "https://testco.wd5.myworkdayjobs.com/wday/cxs/testco/TestCareers/job/x_1"
    client = FakeClient(get_responses={detail_url: FakeResponse({"jobPostingInfo": {"jobDescription": "<p>Hello</p>"}})})

    result = ensure_description(job, company, client)

    assert result.description == "Hello"


def test_load_profile_reads_yaml(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("target_titles:\n  - Product Manager\n")

    profile = load_profile(profile_path)

    assert profile["target_titles"] == ["Product Manager"]


def test_load_profile_raises_a_clear_error_when_missing(tmp_path):
    try:
        load_profile(tmp_path / "does-not-exist.yaml")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_load_resume_keywords_skips_the_copy_marker_line(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.md").write_text(
        "<!-- Copy of a.pdf made by the job agent. Edit the original, not this file. -->\n"
        "Marketplace payments leadership"
    )

    keywords = load_resume_keywords(resumes_dir)

    assert {"marketplace", "payments", "leadership"} <= keywords


def test_run_funnel_sorts_by_fit_quotient_and_respects_top_n():
    profile = {"target_titles": ["Product Manager"]}
    resume_keywords = {"marketplace", "payments"}
    jobs = [
        _job("1", "Product Manager", description="This role touches marketplace and payments daily."),
        _job("2", "Product Manager", description="This role is about marketplace only."),
        _job("3", "Warehouse Associate", description="marketplace payments"),  # filtered by title
    ]

    with httpx.Client() as client:
        top = run_funnel(Company(name="X", careers_url="x", ats="greenhouse", slug="x", board_url="u"),
                          jobs, profile, resume_keywords, client, top_n=1)

    assert len(top) == 1
    assert top[0][0].external_id == "1"
    assert top[0][1] == 100.0
