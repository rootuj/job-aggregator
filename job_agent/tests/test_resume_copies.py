import time

from job_agent.resume_copies import (
    delete_orphaned_copy,
    mark_resume_known,
    save_resume_copy,
    scan_resumes,
)


def _marker(original: str) -> str:
    return f"<!-- Copy of {original} made by the job agent. Edit the original, not this file. -->"


def test_scan_flags_pdf_with_no_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.pdf").write_bytes(b"fake pdf")

    result = scan_resumes(resumes_dir, tmp_path / "known.txt")

    assert result.needs_copy == ["a.pdf"]
    assert result.stale_copies == []


def test_scan_does_not_flag_pdf_with_a_fresh_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.pdf").write_bytes(b"fake pdf")
    (resumes_dir / "a.md").write_text(f"{_marker('a.pdf')}\ncontent")

    result = scan_resumes(resumes_dir, tmp_path / "known.txt")

    assert result.needs_copy == []
    assert result.stale_copies == []


def test_scan_flags_a_stale_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.md").write_text(f"{_marker('a.pdf')}\ncontent")
    time.sleep(0.01)
    (resumes_dir / "a.pdf").write_bytes(b"edited pdf")  # original touched AFTER the copy

    result = scan_resumes(resumes_dir, tmp_path / "known.txt")

    assert result.stale_copies == ["a.pdf"]


def test_scan_ignores_an_unmarked_md_resume_the_user_wrote(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "my_resume.md").write_text("I am my own resume, no marker here.")

    result = scan_resumes(resumes_dir, tmp_path / "known.txt")

    assert result.needs_copy == []  # .md resumes are read directly, never copied


def test_scan_flags_new_resumes_not_in_known_list(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.pdf").write_bytes(b"fake")
    known_path = tmp_path / "known.txt"
    known_path.write_text("")

    result = scan_resumes(resumes_dir, known_path)

    assert result.new_resumes == ["a.pdf"]


def test_scan_does_not_flag_a_resume_already_known(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.pdf").write_bytes(b"fake")
    known_path = tmp_path / "known.txt"
    known_path.write_text("a.pdf\n")

    result = scan_resumes(resumes_dir, known_path)

    assert result.new_resumes == []


def test_scan_flags_an_orphaned_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "gone.md").write_text(f"{_marker('gone.pdf')}\ncontent")  # gone.pdf doesn't exist

    result = scan_resumes(resumes_dir, tmp_path / "known.txt")

    assert result.orphaned_copies == ["gone.pdf"]


def test_scan_ignores_hidden_files(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / ".DS_Store").write_bytes(b"junk")

    result = scan_resumes(resumes_dir, tmp_path / "known.txt")

    assert result == scan_resumes(resumes_dir, tmp_path / "known.txt")  # just doesn't crash, finds nothing
    assert result.needs_copy == [] and result.new_resumes == []


def test_save_resume_copy_writes_the_marker_and_body(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()

    path = save_resume_copy("a.pdf", "# My Resume\nDoes things.", resumes_dir)

    assert path == resumes_dir / "a.md"
    text = path.read_text()
    assert text.startswith(_marker("a.pdf"))
    assert "# My Resume" in text


def test_save_resume_copy_refuses_to_overwrite_a_user_written_md(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "a.md").write_text("My own handwritten resume, no marker.")

    try:
        save_resume_copy("a.pdf", "new content", resumes_dir)
        assert False, "expected FileExistsError"
    except FileExistsError:
        pass
    assert (resumes_dir / "a.md").read_text() == "My own handwritten resume, no marker."


def test_save_resume_copy_can_refresh_its_own_previous_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    save_resume_copy("a.pdf", "old content", resumes_dir)

    save_resume_copy("a.pdf", "new content", resumes_dir)

    assert "new content" in (resumes_dir / "a.md").read_text()


def test_mark_resume_known_appends_without_duplicating(tmp_path):
    known_path = tmp_path / "known.txt"

    mark_resume_known("a.pdf", known_path)
    mark_resume_known("a.pdf", known_path)  # should not duplicate
    mark_resume_known("b.pdf", known_path)

    assert known_path.read_text().splitlines() == ["a.pdf", "b.pdf"]


def test_delete_orphaned_copy_removes_only_a_real_marked_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "gone.md").write_text(f"{_marker('gone.pdf')}\ncontent")

    delete_orphaned_copy("gone.pdf", resumes_dir)

    assert not (resumes_dir / "gone.md").exists()


def test_delete_orphaned_copy_does_not_touch_a_file_that_is_not_its_copy(tmp_path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    (resumes_dir / "other.md").write_text("unrelated content, not a marked copy")

    delete_orphaned_copy("other.pdf", resumes_dir)

    assert (resumes_dir / "other.md").exists()
