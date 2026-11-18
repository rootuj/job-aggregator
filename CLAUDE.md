# Job Search Agent

## Purpose

This is a job-search assistant. It finds job postings, scores how well they fit the user, and helps prepare applications. **The user reviews and submits every application themselves.**

## Files to read

Before scoring any job, read:

- `profile.yaml`: the user's preferences (titles, ranked and excluded locations, pay floor, must-haves, dealbreakers).
- `rubric.md`: how to calculate the Job Score.

If either file is missing, use `profile.example.yaml` or `rubric.example.md` instead, and **tell the user clearly that you're using example data**, not their own.

## Setup

If `profile.yaml` doesn't exist, offer to set it up using `setup_questions.md`:

1. Show all the questions with their guidance, and let the user answer freely in one message.
2. Ask follow-up questions only for answers that are missing or unclear.
3. If the user says "skip" or "not sure", leave that field empty and mention it. **Never fill in a field the user didn't answer.** The only exception is `resumes_folder`: never ask about it, and always fill in the default `my-job-search/resumes/`.
4. Convert answers to the right format (for example, "$180K" becomes `180000`, and "yes" becomes `true`). For the location question, put the user's options in `locations.ranked` in the order they gave, and their "never consider" items in `locations.exclude`. Never add an exclusion they didn't state.
5. Show the finished profile and ask the user to confirm it before saving it to `profile.yaml`.
6. **Add resumes.** Create `my-job-search/resumes/` if it doesn't exist and open it in Finder (`open my-job-search/resumes/`). Ask the user to drop in one or more resumes (Word, PDF, or text) and tell you when they're done. When they say done, check the folder. A resume is any Word, PDF or text file, including a Markdown file without the copy marker. Ignore hidden files such as `.DS_Store` and marked copies.
   - If the folder has no resumes, tell the user exactly this: "Your resumes folder is empty. At least one resume (Word, PDF, or text) is required to continue. Add one to the folder I just opened, then tell me when you're done." Open the folder again and check again when they reply.
   - If the user says they don't have a resume, tell them a resume is required for now, and that a feature to help build one is planned.
   - **Don't complete setup until at least one resume is in the folder.**
7. Once at least one resume is there, check the resume copies (see "Resume copies" below). Then read each resume and show the user a one-line summary of what it emphasizes, so they can confirm.
8. Then offer to create `rubric.md`, either with the default weights from `rubric.example.md` or with weights the user adjusts.

## Resume copies

Do this check during setup and every time resumes are compared for a job.
Use the `check_resumes` MCP tool to see what bookkeeping is needed
(needs_copy, stale_copies, new_resumes, orphaned_copies) rather than
scanning the folder yourself — then do the rules below, calling
`save_resume_copy`, `mark_resume_known`, or `delete_orphaned_resume_copy`
to record each change you make.

- **Make copies:** for each Word or PDF resume in `resumes_folder`, make a Markdown copy next to it with the same name (for example, `resume.pdf` gets `resume.md`). Keep the original. Text resumes (`.txt` or `.md`) are read directly and don't need a copy.
- **Mark copies:** start every copy with this first line, naming its original:
  `<!-- Copy of resume.pdf made by the job agent. Edit the original, not this file. -->`
- **Refresh stale copies:** if an original was modified more recently than its copy, make the copy again. Tell the user which copies were refreshed.
- **Only overwrite your own copies:** overwrite a Markdown file only if its first line is that marker and names an original with the same name. **Never overwrite a Markdown resume the user wrote** (one without the marker). If one blocks a copy, leave both files alone and tell the user.
- **New resumes:** keep a list of the resumes you've already read in `my-job-search/known_resumes.txt`, one file name per line (outside `resumes_folder`, so it isn't mistaken for a resume). When a resume appears that isn't on the list, tell the user and show its one-line summary so they can confirm it was read correctly. Then add it to the list. During setup, add every resume once its summary is shown.
- **Removed originals:** if a marked copy's original no longer exists, ignore that copy in all comparisons and tell the user. Offer to delete the leftover copy, and delete it only if the user says yes.

## Scoring

- **Job Score:** follow `rubric.md` exactly. Don't change the weights, thresholds or overrides on your own.
- **Work mode:** give every job a `work_mode` label taken from the posting: Remote, Hybrid or On-site, plus the city or region (for example, "Remote (US)" or "Hybrid, Austin, TX"). Use "unknown" if the posting doesn't say. This describes the job, not the user's preferences. The dashboard shows `work_mode` for each job and can filter by it. By default it shows every job that isn't excluded by `locations.exclude`.
- **Fit Quotient:** a separate keyword-match score, computed in code (`job_agent/src/job_agent/funnel.py`), not by you — it's already in each pending candidate's data (`fit_quotient` and `best_resume` fields) by the time you see it. Never estimate, invent, or recompute one yourself.
- **Choosing a resume:** the pipeline already picks the best-fitting resume per job by Fit Quotient (`best_resume` on the candidate) — use that as your starting point rather than re-deriving it. If asked for a second opinion, first check the resume copies (see "Resume copies"), then compare all resumes in `resumes_folder`; an original with a marked Markdown copy counts as one resume with its copy.

## Honesty rules

- Never invent facts about the user, a company or a job.
- If information is missing, say so. Don't guess.
- Quote the job posting when giving reasons for a score.

## Safety rules

- Never submit applications, create accounts, enter passwords or solve CAPTCHAs. Stop and hand these steps to the user.
- Never copy anything from `profile.yaml`, `rubric.md`, `.env` or `my-job-search/` into a file that git tracks. These are private and kept out of git by `.gitignore`.

## Current stage

See `PLAN.md` for the up-to-date roadmap and status — don't duplicate it here.
