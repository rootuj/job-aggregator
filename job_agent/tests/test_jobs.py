from job_agent.jobs import Job, dedup_jobs, fetch_jobs, fetch_workday_description
from job_agent.watchlist import Company
from fakes import FakeClient, FakeResponse


def test_dedup_jobs_keeps_first_occurrence():
    jobs = [
        Job(external_id="1", company="X", ats="greenhouse", title="A", location=None, url="u1"),
        Job(external_id="1", company="X", ats="greenhouse", title="A (dup)", location=None, url="u1"),
        Job(external_id="2", company="X", ats="greenhouse", title="B", location=None, url="u2"),
    ]
    deduped = dedup_jobs(jobs)
    assert [j.external_id for j in deduped] == ["1", "2"]
    assert deduped[0].title == "A"


def test_fetch_greenhouse_parses_real_response_shape():
    company = Company(name="Stripe", careers_url="x", ats="greenhouse", slug="stripe",
                       board_url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs")
    # content=true is appended to the SAME list call to get the description for free
    url = company.board_url + "?content=true"
    raw = {
        "jobs": [{
            "id": 8172508, "title": "Abuse Investigator",
            "location": {"name": "Dublin"}, "absolute_url": "https://stripe.com/jobs/search?gh_jid=8172508",
            "first_published": "2026-09-03T13:32:53-04:00",
            # real Greenhouse content is HTML-entity-escaped on top of being HTML
            "content": "&lt;p&gt;We fight &lt;strong&gt;fraud&lt;/strong&gt;.&lt;/p&gt;",
        }]
    }
    client = FakeClient(get_responses={url: FakeResponse(raw)})

    jobs = fetch_jobs(company, client=client)

    assert jobs == [Job(
        external_id="8172508", company="Stripe", ats="greenhouse", title="Abuse Investigator",
        location="Dublin", url="https://stripe.com/jobs/search?gh_jid=8172508",
        posted_at="2026-09-03T13:32:53-04:00",
        description="We fight fraud .",
    )]


def test_fetch_lever_parses_real_response_shape():
    company = Company(name="Palantir", careers_url="x", ats="lever", slug="palantir",
                       board_url="https://api.lever.co/v0/postings/palantir?mode=json")
    raw = [{
        "id": "6ed76ce8-4156-4b60-b120-403538bd66cd", "text": "Administrative Business Partner",
        "categories": {"location": "Singapore, Singapore", "team": "Administrative"},
        "hostedUrl": "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd",
        "createdAt": 1786469891368,
    }]
    client = FakeClient(get_responses={company.board_url: FakeResponse(raw)})

    jobs = fetch_jobs(company, client=client)

    assert jobs == [Job(
        external_id="6ed76ce8-4156-4b60-b120-403538bd66cd", company="Palantir", ats="lever",
        title="Administrative Business Partner", location="Singapore, Singapore", department="Administrative",
        url="https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd", posted_at="1786469891368",
    )]


def test_fetch_lever_combines_opening_body_and_additional_but_skips_the_duplicate_field():
    # Lever's own `descriptionPlain` duplicates `openingPlain` (verified live
    # against a real posting) — using it would double-count that section.
    company = Company(name="Palantir", careers_url="x", ats="lever", slug="palantir",
                       board_url="https://api.lever.co/v0/postings/palantir?mode=json")
    raw = [{
        "id": "1", "text": "Role", "categories": {}, "hostedUrl": "u", "createdAt": 1,
        "openingPlain": "Opening text.",
        "descriptionPlain": "Opening text.",  # duplicate of openingPlain — must be ignored
        "descriptionBodyPlain": "Body text.",
        "additionalPlain": "Additional text.",
    }]
    client = FakeClient(get_responses={company.board_url: FakeResponse(raw)})

    jobs = fetch_jobs(company, client=client)

    assert jobs[0].description == "Opening text.\n\nBody text.\n\nAdditional text."


def test_fetch_ashby_parses_real_response_shape():
    company = Company(name="Ramp", careers_url="x", ats="ashby", slug="ramp",
                       board_url="https://api.ashbyhq.com/posting-api/job-board/ramp")
    raw = {
        "jobs": [{
            "id": "34413f8d-26bf-4bbc-8ade-eb309a0e2245", "title": " Software Engineer, Security, Cloud",
            "department": "Engineering", "location": "New York, NY (HQ)",
            "publishedAt": "2026-04-07T17:12:35.753+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/34413f8d-26bf-4bbc-8ade-eb309a0e2245",
            "descriptionPlain": "ABOUT RAMP\n\nWe build finance tools.",
        }]
    }
    client = FakeClient(get_responses={company.board_url: FakeResponse(raw)})

    jobs = fetch_jobs(company, client=client)

    assert jobs == [Job(
        external_id="34413f8d-26bf-4bbc-8ade-eb309a0e2245", company="Ramp", ats="ashby",
        title="Software Engineer, Security, Cloud", location="New York, NY (HQ)", department="Engineering",
        url="https://jobs.ashbyhq.com/ramp/34413f8d-26bf-4bbc-8ade-eb309a0e2245",
        posted_at="2026-04-07T17:12:35.753+00:00",
        description="ABOUT RAMP\n\nWe build finance tools.",
    )]


def _workday_company():
    return Company(name="TestCo", careers_url="x", ats="workday", slug="testco/TestCareers",
                    board_url="https://testco.wd5.myworkdayjobs.com/wday/cxs/testco/TestCareers/jobs")


def _workday_posting(n):
    return {
        "title": f"Engineer {n}", "externalPath": f"/job/loc/Engineer-{n}_JR{n}",
        "locationsText": "Remote", "postedOn": "Posted Today", "bulletFields": [f"JR{n}"],
    }


def test_fetch_workday_paginates_despite_total_resetting_to_zero_after_page_one():
    # Real-world bug found by testing live against NVIDIA: `total` is only
    # correct on the FIRST page; every later page reports total: 0 even
    # though it still returns real postings. The fetcher must capture
    # `total` once, from page 1, not re-read it every page.
    company = _workday_company()

    def post_handler(url, json_body):
        offset = json_body["offset"]
        postings = [_workday_posting(offset + i) for i in range(min(20, max(0, 45 - offset)))]
        total = 45 if offset == 0 else 0
        return FakeResponse({"total": total, "jobPostings": postings})

    client = FakeClient(post_handler=post_handler)

    jobs = fetch_jobs(company, client=client)

    assert len(jobs) == 45
    assert [j.external_id for j in jobs[:2]] == ["JR0", "JR1"]
    assert jobs[0].url == "https://testco.wd5.myworkdayjobs.com/TestCareers/job/loc/Engineer-0_JR0"


def test_fetch_workday_retries_once_after_a_429(monkeypatch):
    # Also found live: Workday's Cloudflare rate limiter can return 429.
    import job_agent.jobs as jobs_module

    monkeypatch.setattr(jobs_module.time, "sleep", lambda _seconds: None)  # don't actually wait 15s in a test
    company = _workday_company()
    attempts = {"count": 0}

    def post_handler(url, json_body):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return FakeResponse(status_code=429, text="rate limited")
        return FakeResponse({"total": 1, "jobPostings": [_workday_posting(0)]})

    client = FakeClient(post_handler=post_handler)

    jobs = fetch_jobs(company, client=client)

    assert len(jobs) == 1
    assert attempts["count"] == 2


def test_fetch_workday_raises_loudly_on_repeated_failure(monkeypatch):
    import job_agent.jobs as jobs_module

    monkeypatch.setattr(jobs_module.time, "sleep", lambda _seconds: None)
    company = _workday_company()
    client = FakeClient(post_handler=lambda url, body: FakeResponse(status_code=500, text="server error"))

    try:
        fetch_jobs(company, client=client)
        assert False, "expected a RuntimeError"
    except RuntimeError as exc:
        assert "500" in str(exc)


def test_fetch_workday_description_hits_the_detail_endpoint_and_strips_html():
    company = _workday_company()
    job = Job(external_id="JR1", company="TestCo", ats="workday", title="Engineer", location=None,
              url="https://testco.wd5.myworkdayjobs.com/TestCareers/job/loc/Engineer_JR1")
    # the detail endpoint is the board_url's host, minus "/jobs", plus the job's own path
    detail_url = "https://testco.wd5.myworkdayjobs.com/wday/cxs/testco/TestCareers/job/loc/Engineer_JR1"
    client = FakeClient(get_responses={detail_url: FakeResponse({"jobPostingInfo": {"jobDescription": "<p>Build things.</p>"}})})

    description = fetch_workday_description(job, company, client)

    assert description == "Build things."


def test_fetch_workday_description_raises_on_failure():
    company = _workday_company()
    job = Job(external_id="JR1", company="TestCo", ats="workday", title="Engineer", location=None,
              url="https://testco.wd5.myworkdayjobs.com/TestCareers/job/loc/Engineer_JR1")
    client = FakeClient(get_responses={})  # falls through to the 404 default

    try:
        fetch_workday_description(job, company, client)
        assert False, "expected a RuntimeError"
    except RuntimeError:
        pass
