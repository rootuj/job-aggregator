"""Install/remove the macOS launchd job that runs the pipeline daily at 9am.

launchd, not a simple loop script — it needs no terminal left open and
survives reboots and sleep (see PLAN.md's "no terminal after install"
principle; a loop script would need to run forever in an open terminal).

This only automates the free, code-only half of the pipeline (fetch,
track, Fit Quotient). Job Score still needs Claude to read rubric.md —
that's by design (see CLAUDE.md), not a gap. Ask Claude to score the
pending jobs whenever you check in.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

LABEL = "com.jobaggregator.dailyrun"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LABEL}.plist"

JOB_AGENT_DIR = Path(__file__).resolve().parent.parent.parent  # .../job_agent
LOG_DIR = JOB_AGENT_DIR / "data" / "logs"


def _uv_path() -> str:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv not found on PATH — install it first (see https://docs.astral.sh/uv/)")
    return uv


def _plist_contents() -> str:
    uv = _uv_path()
    stdout_log = LOG_DIR / "daily_run.out.log"
    stderr_log = LOG_DIR / "daily_run.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv}</string>
        <string>run</string>
        <string>--directory</string>
        <string>{JOB_AGENT_DIR}</string>
        <string>job-agent-daily</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{stdout_log}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_log}</string>
</dict>
</plist>
"""


def install() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_plist_contents())
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)  # ignore error if not loaded yet
    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    print(f"Installed. The pipeline will run every day at 9:00am.\nLogs: {LOG_DIR}")


def uninstall() -> None:
    if not PLIST_PATH.exists():
        print("Not installed — nothing to do.")
        return
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink()
    print("Uninstalled — the daily run is no longer scheduled.")


def status() -> None:
    if not PLIST_PATH.exists():
        print("Not installed.")
        return
    result = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)
    if result.returncode == 0:
        print("Installed and loaded.")
        print(result.stdout)
    else:
        print("Plist file exists but isn't currently loaded — try reinstalling.")
