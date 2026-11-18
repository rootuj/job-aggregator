from job_agent.discovery import (
    CompanyCandidate,
    add_discovered_companies,
    discover_from_hn,
    discover_from_yc,
    fetch_whoishiring_thread_id,
)
from job_agent.watchlist import Company, load_watchlist, save_watchlist
from fakes import FakeClient, FakeResponse


def _hn_url(path):
    return f"https://hacker-news.firebaseio.com/v0/{path}"


def test_fetch_whoishiring_thread_id_picks_the_hiring_thread_not_the_others():
    responses = {
        _hn_url("user/whoishiring.json"): FakeResponse({"submitted": [3, 2, 1]}),
        _hn_url("item/3.json"): FakeResponse({"id": 3, "title": "Ask HN: Freelancer? Seeking freelancer?"}),
        _hn_url("item/2.json"): FakeResponse({"id": 2, "title": "Ask HN: Who wants to be hired?"}),
        _hn_url("item/1.json"): FakeResponse({"id": 1, "title": "Ask HN: Who is hiring? (November 2026)"}),
    }
    client = FakeClient(get_responses=responses)

    thread_id = fetch_whoishiring_thread_id(client)

    assert thread_id == 1


def test_discover_from_hn_extracts_company_names_and_skips_junk():
    responses = {
        _hn_url("user/whoishiring.json"): FakeResponse({"submitted": [10]}),
        _hn_url("item/10.json"): FakeResponse({"title": "Ask HN: Who is hiring? (November 2026)", "kids": [1, 2, 3, 4]}),
        _hn_url("item/1.json"): FakeResponse({"text": "Fly.io | REMOTE | Full time | $190k"}),
        _hn_url("item/2.json"): FakeResponse({"text": "", "dead": True}),  # dead comment, skipped
        _hn_url("item/3.json"): FakeResponse({}),  # no text at all, skipped
        _hn_url("item/4.json"): FakeResponse({"text": "MONUMENTAL &amp; Co | Amsterdam | Full Time"}),
    }
    client = FakeClient(get_responses=responses)

    candidates = discover_from_hn(client)

    assert [c.name for c in candidates] == ["Fly.io", "MONUMENTAL & Co"]
    assert all(c.source == "hn" for c in candidates)


def test_discover_from_yc_paginates_and_filters_to_active():
    url = "https://api.ycombinator.com/v0.1/companies"
    page1 = {
        "companies": [
            {"name": "ActiveCo", "status": "Active", "website": "https://activeco.com"},
            {"name": "DeadCo", "status": "Inactive", "website": "https://deadco.com"},
        ],
        "totalPages": 2,
    }
    page2 = {
        "companies": [{"name": "SecondPageCo", "status": "Active", "website": "https://second.com"}],
        "totalPages": 2,
    }

    def get(request_url, params=None, timeout=None):
        return FakeResponse(page1 if params["page"] == 1 else page2)

    client = FakeClient()
    client.get = get

    candidates = discover_from_yc(["W27"], client)

    assert [c.name for c in candidates] == ["ActiveCo", "SecondPageCo"]
    assert candidates[0].hint_url == "https://activeco.com"
    assert all(c.source == "yc" for c in candidates)


def test_add_discovered_companies_adds_only_when_ats_is_detected(tmp_path, monkeypatch):
    import job_agent.discovery as discovery_module

    watchlist_path = tmp_path / "watchlist.json"
    save_watchlist([], watchlist_path)
    monkeypatch.setattr(discovery_module, "load_watchlist", lambda: load_watchlist(watchlist_path))
    monkeypatch.setattr(discovery_module, "save_watchlist", lambda companies: save_watchlist(companies, watchlist_path))

    from job_agent.ats import ATSMatch

    def fake_detect_ats(careers_url):
        return ATSMatch("greenhouse", "found", "https://x", "probed") if careers_url == "FoundCo" else None

    monkeypatch.setattr(discovery_module, "detect_ats", fake_detect_ats)

    candidates = [CompanyCandidate(name="FoundCo", source="test"), CompanyCandidate(name="NotFoundCo", source="test")]
    result = add_discovered_companies(candidates)

    assert result == {"added": ["FoundCo"], "skipped_no_ats": ["NotFoundCo"], "skipped_duplicate": []}
    assert [c.name for c in load_watchlist(watchlist_path)] == ["FoundCo"]


def test_add_discovered_companies_skips_existing_watchlist_entries(tmp_path, monkeypatch):
    import job_agent.discovery as discovery_module

    watchlist_path = tmp_path / "watchlist.json"
    save_watchlist([Company(name="Existing", careers_url="x", ats="greenhouse", slug="e", board_url="u")], watchlist_path)
    monkeypatch.setattr(discovery_module, "load_watchlist", lambda: load_watchlist(watchlist_path))
    monkeypatch.setattr(discovery_module, "save_watchlist", lambda companies: save_watchlist(companies, watchlist_path))
    monkeypatch.setattr(discovery_module, "detect_ats", lambda url: None)

    result = add_discovered_companies([CompanyCandidate(name="Existing", source="test")])

    assert result["skipped_duplicate"] == ["Existing"]
    assert len(load_watchlist(watchlist_path)) == 1


def test_add_discovered_companies_dedups_within_the_candidate_list(tmp_path, monkeypatch):
    import job_agent.discovery as discovery_module

    watchlist_path = tmp_path / "watchlist.json"
    save_watchlist([], watchlist_path)
    monkeypatch.setattr(discovery_module, "load_watchlist", lambda: load_watchlist(watchlist_path))
    monkeypatch.setattr(discovery_module, "save_watchlist", lambda companies: save_watchlist(companies, watchlist_path))
    monkeypatch.setattr(discovery_module, "detect_ats", lambda url: None)

    result = add_discovered_companies([
        CompanyCandidate(name="SameCo", source="hn"),
        CompanyCandidate(name="SameCo", source="yc"),
    ])

    assert result["skipped_no_ats"] == ["SameCo"]  # counted once, not twice
