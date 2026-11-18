import job_agent.scheduler as scheduler_module


def _redirect_paths(monkeypatch, tmp_path):
    plist_path = tmp_path / "LaunchAgents" / "com.jobaggregator.dailyrun.plist"
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(scheduler_module, "LAUNCH_AGENTS_DIR", plist_path.parent)
    monkeypatch.setattr(scheduler_module, "PLIST_PATH", plist_path)
    monkeypatch.setattr(scheduler_module, "LOG_DIR", log_dir)
    return plist_path, log_dir


def _fake_run(monkeypatch, calls):
    def fake(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setattr(scheduler_module.subprocess, "run", fake)


def test_install_writes_a_valid_plist_and_loads_it(tmp_path, monkeypatch):
    plist_path, log_dir = _redirect_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduler_module, "_uv_path", lambda: "/usr/local/bin/uv")
    calls = []
    _fake_run(monkeypatch, calls)

    scheduler_module.install()

    assert plist_path.exists()
    content = plist_path.read_text()
    assert "<string>/usr/local/bin/uv</string>" in content
    assert "<integer>9</integer>" in content  # 9am
    assert str(log_dir) in content
    assert log_dir.exists()
    assert ["launchctl", "unload", str(plist_path)] in calls
    assert ["launchctl", "load", str(plist_path)] in calls


def test_install_raises_a_clear_error_without_uv(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduler_module.shutil, "which", lambda name: None)

    try:
        scheduler_module.install()
        assert False, "expected a RuntimeError"
    except RuntimeError as exc:
        assert "uv not found" in str(exc)


def test_uninstall_removes_the_plist(tmp_path, monkeypatch):
    plist_path, _ = _redirect_paths(monkeypatch, tmp_path)
    plist_path.parent.mkdir(parents=True)
    plist_path.write_text("<plist></plist>")
    calls = []
    _fake_run(monkeypatch, calls)

    scheduler_module.uninstall()

    assert not plist_path.exists()
    assert ["launchctl", "unload", str(plist_path)] in calls


def test_uninstall_when_not_installed_is_a_no_op(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)

    scheduler_module.uninstall()

    assert "Not installed" in capsys.readouterr().out


def test_status_when_not_installed(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)

    scheduler_module.status()

    assert "Not installed" in capsys.readouterr().out
