# Job Aggregator — Project Plan

## Vision

An open-source job aggregator for job seekers. It finds companies, collects
their open jobs from ATS feeds, matches those jobs against the user's
profile and resumes, and shows a daily dashboard of top matches (e.g. 9am,
top 3–5 to apply to). The user reviews and submits every application
themselves — this tool never applies on its own.

## Principles

- **Free core that works with no AI**: aggregation, filters, Fit Quotient,
  and the dashboard all work without calling any model.
- **Claude is an optional upgrade**: Job Score and application prep use the
  model, but the core pipeline doesn't depend on them.
- **Code for anything deterministic, the model only for judgment.**
- **Hosting-ready but not hosting-built**: the engine (`job_agent/`) is kept
  separate from the dashboard; data is tied to a user ID; paths are
  configurable — so this could run hosted for multiple users later, even
  though today it's built for one person running it locally.
- **Low cost, no terminal after install**, with the eventual goal of a
  double-click install.
- **Never auto-submit applications, create accounts, or solve CAPTCHAs.**

## Architecture

This is a **pipeline**, not a live web app with a database — it runs as
scheduled batch steps that write plain data files, and the dashboard just
reads the latest files. Think of it as an assembly line: each stage reads
what the previous stage produced and hands off a file to the next stage.

1. **Company Finder** (weekly) → builds/updates a watchlist of companies
   and which ATS each one uses.
2. **Job Finder** (daily) → pulls raw postings from each watched company's
   ATS feed, normalizes them into one standard job format, dedups, and
   diffs against the previous run (new/unchanged/edited/gone).
3. **Funnel** → a cheap title-keyword pre-filter first (not location —
   see Key decisions), then Fit Quotient (still code — resume/JD keyword
   overlap), narrowing to the top ~20 — only those go on to Job Score,
   where the model gets involved.
4. **Dashboard** → a thin local web app that only *reads* the latest
   output files and displays them; no pipeline logic lives there.
5. **Scheduler** (step 7) → triggers the daily run automatically.

**Where the model fits in**: `job_agent` will expose an **MCP server**
(step 3d) — the structured doorway Claude uses to call into the engine's
data and functions, instead of operating freeform. The model is only
invoked for the two judgment calls (Job Score, application prep); fetching,
filtering, and deduping stay pure deterministic code. **Job Score is not
a Python function** — the model computes it itself by reading `rubric.md`
and `profile.yaml` directly and following the rubric exactly (see
`CLAUDE.md`), the same way it already did before this engine existed.

**Not yet decided** (to be settled at the matching roadmap step, not
guessed now):
- Scheduler mechanism (macOS `launchd` vs. a simple loop) — step 7.

## Key decisions

- **Two-step discovery**: a weekly **Company Finder** followed by a daily
  **Job Finder**.
- **Sources, in order**: Greenhouse, Lever, and Ashby first; Workday also
  supported (detection added — its job API is real but unofficial:
  undocumented, unversioned, and called with POST instead of GET like the
  other three — fetching it lands at step 4 alongside the others); VC
  portfolio pages, HN Who's Hiring, and YC for company discovery; LinkedIn
  last, as a private, local-only, read-only plugin that runs once a day.
- **Daily runs diff against the previous run**: jobs are marked new,
  unchanged, edited, or gone. A job is marked closed after 2 consecutive
  misses, and reposts are flagged.
- **Funnel**: a cheap title-keyword pre-filter in code, then Fit Quotient
  (code), then Job Score (model-based) on only the top ~20 candidates —
  to keep model usage cheap. **Location filtering is NOT done in code.**
  `rubric.md`'s own "Location rules" require real judgment (e.g. is a
  remote job actually restricted to a non-US country?) that simple code
  can't reliably make — that stays entirely with the model, at Job Score
  time. Code only ever does the cheap title pre-filter, for cost control
  (see Architecture → Funnel).
- **Two scores**:
  - **Fit Quotient**: keyword-overlap percentage between resume and job
    description, computed in code only, no model.
  - **Job Score**: a rubric-based score computed by the model, run only on
    the top ~20 jobs that pass Fit Quotient.
- **Locations**: a ranked list of preferred locations plus an exclude list;
  every job is labeled with a `work_mode` (remote/hybrid/onsite).
- **Dashboard never pads results**: it shows fewer matches rather than
  padding with weak ones.
- **Settings tab** in the dashboard, built for non-technical users.
- **Resume required at setup** — the pipeline doesn't run without one.

## Roadmap

1. *(done — see Current status)*
2. *(done — see Current status)*
3. *(done — see Current status)* **Company Finder**
   - 3a. Python project scaffolding with `uv`
   - 3b. ATS detector
   - 3c. Company watchlist
   - 3d. First MCP server
4. *(done — see Current status)* **Job Finder**: Greenhouse/Lever/Ashby/Workday
   feeds, a standard job format, deduplication, daily comparison
   (new/unchanged/edited/gone)
5. *(done — see Current status)* **Funnel and Job Score**
6. **Dashboard** (web app, run on the user's Mac) with a Settings tab
7. **9am scheduled run**
8. **Fit Quotient and best-resume pick**
9. **More sources and company discovery**
10. **Bulk prepare** (application prep assistance across several jobs)
11. **LinkedIn private plugin**

**Later / someday**: build-a-resume-with-me, warm-intro finder, easy
double-click install, hosted version.

## File structure

Kept up to date as real folders/files are added (not every tiny file —
just the shape of the project).

```
Job Aggregator/
├── PLAN.md              — this file
├── CLAUDE.md            — agent rules for this project (committed, shared)
├── CLAUDE.local.md      — personal preferences (gitignored, not shared)
├── .gitignore
├── profile.yaml         — your real preferences (gitignored, private)
├── profile.example.yaml — template version (committed)
├── rubric.md            — your real Job Score rubric (gitignored, private)
├── rubric.example.md    — template version (committed)
├── setup_questions.md   — questions used to build profile.yaml
├── my-job-search/       — resumes + known_resumes.txt (gitignored, private)
└── job_agent/           — the engine (step 3+), separate from the dashboard
    ├── pyproject.toml   — project metadata + dependencies
    ├── uv.lock          — exact locked dependency versions
    ├── .python-version  — Python version for this project (3.13)
    ├── README.md
    └── src/job_agent/
        ├── __init__.py  — placeholder entry point
        ├── ats.py       — ATS detector (Greenhouse/Lever/Ashby)
        ├── watchlist.py — tracked companies (data/watchlist.json, gitignored)
        ├── mcp_server.py — MCP server exposing watchlist tools to Claude
        ├── jobs.py      — standard Job format + fetchers (Greenhouse/Lever/Ashby/Workday)
        ├── tracking.py  — daily diff (new/unchanged/edited/gone/repost), data/jobs/*.json
        └── funnel.py    — title pre-filter + Fit Quotient (reads ../profile.yaml, ../my-job-search/)
    └── tests/           — pytest suite (fakes.py stands in for the network)
```

## Current status

- **Automated tests added**: `job_agent/tests/` (`pytest`, run with
  `uv run pytest` from `job_agent/`) — 29 tests covering `ats.py`,
  `watchlist.py`, `jobs.py` (all four fetchers, plus the Workday pagination
  and rate-limit bugs as permanent regression tests), and `tracking.py`'s
  full diff lifecycle. All network calls are faked (`tests/fakes.py`), so
  the suite runs in about a second with no live API dependency.

- **Step 2 is done, confirmed**: `profile.yaml`, `rubric.md`, and real
  resumes are now physically present in this project (`my-job-search/`,
  all gitignored). They previously lived in a separate, disconnected
  repo (`~/code/job-agent/`, 10 commits) that was never merged with this
  one — that repo also had its own `CLAUDE.md` with operational rules
  this project hadn't seen yet (resume versioning with Markdown copies
  and a `known_resumes.txt` registry, `work_mode` string format, honesty
  and safety rules). That `CLAUDE.md` is now copied in here as the real
  one; `~/code/job-agent/` is retired but left untouched on disk as a
  backup, not deleted.
  - **Not yet built**: the resume-copy-versioning system `CLAUDE.md`
    describes (Markdown copies of PDF/Word resumes, staleness refresh,
    `known_resumes.txt` tracking). This belongs with step 8
    ("Fit Quotient and best-resume pick").
- **Step 3a is done**: `job_agent/` scaffolded as a `uv`-managed Python
  project (Python 3.13, `src/job_agent/` package layout).
- **Step 3b is done**: ATS detector (`job_agent/src/job_agent/ats.py`) —
  detects Greenhouse/Lever/Ashby/Workday from a known careers URL, or (for
  Greenhouse/Lever/Ashby only — Workday's URL can't be guessed) by
  guessing a slug from a company name/domain and probing each ATS's
  public API. Verified live against a real Workday site (NVIDIA).
- **Step 3c is done**: company watchlist (`job_agent/src/job_agent/watchlist.py`)
  — stores companies you add, tagged with their ATS via the detector.
  Saved as JSON at `job_agent/data/watchlist.json` (gitignored — personal
  data, not shared code).
- **Step 3d is done**: first MCP server (`job_agent/src/job_agent/mcp_server.py`),
  exposing `watchlist_add` and `watchlist_list` as tools — add companies by
  asking Claude instead of running Python. Run it with `uv run job-agent-mcp`.
  (Note: the `mcp` package did a breaking v2 API change after this plan was
  written — `FastMCP` is now `MCPServer`, imported from `mcp.server.mcpserver`.)
- **Open items**:
  - Confirm resume summaries.
  - Make must-haves specific (not generic).
- **Step 4 is done**: Job Finder.
  - A standard `Job` format plus fetchers for all four ATS types
    (`job_agent/src/job_agent/jobs.py`), verified against real companies.
    Two real Workday bugs found and fixed: it rejects `limit > 20` with
    a 400 (undocumented), and its `total` field is only correct on the
    *first* paginated page — every later page reports `total: 0` even
    with real postings still coming back, so the fetcher now captures
    `total` once, from page 1. Also hit Workday's Cloudflare-based rate
    limiting live while testing a large company (NVIDIA, ~2000 jobs ≈
    100 requests); added pacing (0.5s between pages) and one longer
    backoff-retry on a 429.
  - Dedup (`dedup_jobs` in `jobs.py`) and daily comparison
    (`job_agent/src/job_agent/tracking.py`) — each company's job state
    is persisted at `job_agent/data/jobs/{company}.json` (gitignored)
    and diffed on every run into new/unchanged/edited/gone/repost. A
    job missing from a run isn't immediately "gone" — it quietly gets a
    miss counter; only after 2 consecutive misses is it marked closed
    and reported as "gone". A job reappearing (same external_id, or a
    new id with the same title+location as a closed job) is flagged
    "repost" instead of "new". Verified end-to-end with a simulated
    4-run scenario covering every transition, plus a save/load
    round-trip check.
  - Each job also carries a `repost_count` (how many times it's been
    relisted) and `age_days` — days since we *first* saw this job,
    counted from its original listing and never reset by a repost or a
    closed gap in between. Together these double as an indirect
    "phantom job" signal: a listing open unusually long, or reposted
    several times, may be evergreen rather than an actively-filled role
    — useful input for Job Score later.
- **Step 5 is done (the code half — Job Score itself needs no code, see
  Architecture)**: the Funnel (`job_agent/src/job_agent/funnel.py`).
  - **Discovered along the way**: `Job` never captured description text
    at all until now — needed for Fit Quotient. Checked live rather than
    assumed: Greenhouse needs `?content=true` added to the same list
    call (free); Lever and Ashby already include it in the list response
    (free); Workday's list endpoint never includes it — getting it costs
    **one extra request per job** via a newly-found detail endpoint
    (`fetch_workday_description`), which is why a cheap pre-filter has to
    run before fetching descriptions, not after.
  - **Title pre-filter**: deliberately lenient keyword-overlap check
    against `profile.yaml`'s `target_titles` (e.g. shares the word "Head"
    with "Head of Product" is enough to pass) — it exists only for cost
    control, not precision. Real title/seniority precision is Job
    Score's job (25-point criterion in `rubric.md`), not the Funnel's.
  - **Location filtering is NOT done here** — see Key decisions.
  - **Fit Quotient**: % of a resume's significant words found in a job's
    description, using the union of keywords across every resume `.md`
    file in `my-job-search/resumes/` (picking the single *best* resume
    per job is step 8's job, not this one).
  - Verified against real companies (Stripe, Palantir, Ramp) using the
    real `profile.yaml` and real resumes, plus 14 new pytest tests.

---

*Keep this file updated as decisions change — it's the source of truth for
what this project is and why, across sessions.*
