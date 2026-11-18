"""Detects what resume bookkeeping needs doing, per CLAUDE.md's "Resume
copies" rules. Pure deterministic checks (file exists? which is newer?
does this line match the marker?) — the actual reading of a PDF/Word
resume and writing a readable Markdown copy is the model's job, not
this module's; this only figures out WHAT needs doing and lets the
model DO it via save_resume_copy/mark_resume_known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RESUMES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "my-job-search" / "resumes"
DEFAULT_KNOWN_RESUMES_PATH = DEFAULT_RESUMES_DIR.parent / "known_resumes.txt"

_SOURCE_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
_NEEDS_COPY_EXTENSIONS = {".pdf", ".doc", ".docx"}  # these can't be read as plain text directly
_MARKER_RE = re.compile(r"^<!-- Copy of (.+) made by the job agent\. Edit the original, not this file\. -->$")


@dataclass
class ResumeScanResult:
    needs_copy: list[str]  # PDF/Word originals with no Markdown copy at all
    stale_copies: list[str]  # originals newer than their existing copy
    new_resumes: list[str]  # resumes not yet in known_resumes.txt
    orphaned_copies: list[str]  # marked copies whose named original no longer exists


def _marked_copy_target(path: Path) -> str | None:
    """The original filename this .md file claims to be a copy of, or None."""
    if path.suffix != ".md":
        return None
    try:
        first_line = path.read_text().split("\n", 1)[0]
    except (UnicodeDecodeError, OSError):
        return None
    match = _MARKER_RE.match(first_line.strip())
    return match.group(1) if match else None


def scan_resumes(
    resumes_dir: Path = DEFAULT_RESUMES_DIR, known_resumes_path: Path = DEFAULT_KNOWN_RESUMES_PATH
) -> ResumeScanResult:
    if not resumes_dir.exists():
        return ResumeScanResult([], [], [], [])

    files = [p for p in resumes_dir.iterdir() if p.is_file() and not p.name.startswith(".")]

    copies_by_original: dict[str, Path] = {}
    sources: list[Path] = []
    for path in files:
        original_name = _marked_copy_target(path)
        if original_name is not None:
            copies_by_original[original_name] = path
        elif path.suffix.lower() in _SOURCE_EXTENSIONS:
            sources.append(path)

    needs_copy = []
    stale_copies = []
    for source in sources:
        if source.suffix.lower() not in _NEEDS_COPY_EXTENSIONS:
            continue  # a plain .txt or unmarked .md is read directly — no copy needed
        copy = copies_by_original.get(source.name)
        if copy is None:
            needs_copy.append(source.name)
        elif source.stat().st_mtime > copy.stat().st_mtime:
            stale_copies.append(source.name)

    source_names = {s.name for s in sources}
    known = set(known_resumes_path.read_text().splitlines()) if known_resumes_path.exists() else set()
    new_resumes = sorted(source_names - known)
    orphaned_copies = sorted(original for original in copies_by_original if original not in source_names)

    return ResumeScanResult(
        needs_copy=sorted(needs_copy),
        stale_copies=sorted(stale_copies),
        new_resumes=new_resumes,
        orphaned_copies=orphaned_copies,
    )


def save_resume_copy(
    original_filename: str, markdown_body: str, resumes_dir: Path = DEFAULT_RESUMES_DIR
) -> Path:
    """Write (or refresh) a marked Markdown copy of a PDF/Word resume.

    Refuses to overwrite a .md file that isn't already one of our own
    marked copies — e.g. a resume you wrote directly in Markdown — per
    CLAUDE.md: "Never overwrite a Markdown resume the user wrote."
    """
    copy_path = resumes_dir / f"{Path(original_filename).stem}.md"
    if copy_path.exists() and _marked_copy_target(copy_path) is None:
        raise FileExistsError(
            f"{copy_path.name} already exists and wasn't made by the job agent — "
            "refusing to overwrite a file you wrote yourself."
        )
    marker = f"<!-- Copy of {original_filename} made by the job agent. Edit the original, not this file. -->"
    copy_path.write_text(f"{marker}\n{markdown_body}")
    return copy_path


def mark_resume_known(name: str, known_resumes_path: Path = DEFAULT_KNOWN_RESUMES_PATH) -> None:
    known = known_resumes_path.read_text().splitlines() if known_resumes_path.exists() else []
    if name not in known:
        known.append(name)
        known_resumes_path.parent.mkdir(parents=True, exist_ok=True)
        known_resumes_path.write_text("\n".join(known) + "\n")


def delete_orphaned_copy(original_name: str, resumes_dir: Path = DEFAULT_RESUMES_DIR) -> None:
    """Delete a copy whose original is gone. Only call this after the user
    says yes — per CLAUDE.md: "Offer to delete... delete it only if the
    user says yes.\""""
    copy_path = resumes_dir / f"{Path(original_name).stem}.md"
    if copy_path.exists() and _marked_copy_target(copy_path) == original_name:
        copy_path.unlink()
