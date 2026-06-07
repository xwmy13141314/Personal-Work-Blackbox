from __future__ import annotations

import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LaunchAgentOptions:
    label: str = "com.personal-recorder.watch-macos"
    poll_interval: float = 5.0
    browser_refresh_interval: int = 300
    calendar_refresh_interval: int = 900
    terminal_refresh_interval: int = 3
    since_hours: int = 24
    max_events_per_source: int = 30


class LaunchAgentManager:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.launch_agents_dir = Path.home() / "Library" / "LaunchAgents"

    def plist_path(self, label: str) -> Path:
        return self.launch_agents_dir / f"{label}.plist"

    def install(self, options: LaunchAgentOptions) -> Path:
        self.launch_agents_dir.mkdir(parents=True, exist_ok=True)
        plist_path = self.plist_path(options.label)
        python_exec = sys.executable or "python3"
        program_args = [
            python_exec,
            "-m",
            "personal_recorder",
            "watch-macos",
            "--poll-interval",
            str(options.poll_interval),
            "--browser-refresh-interval",
            str(options.browser_refresh_interval),
            "--calendar-refresh-interval",
            str(options.calendar_refresh_interval),
            "--terminal-refresh-interval",
            str(options.terminal_refresh_interval),
            "--hours",
            str(options.since_hours),
            "--max-events-per-source",
            str(options.max_events_per_source),
        ]
        payload = {
            "Label": options.label,
            "ProgramArguments": program_args,
            "WorkingDirectory": str(self.root_dir),
            "EnvironmentVariables": {
                "PYTHONPATH": "src",
            },
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(self.root_dir / "data" / "watch-macos.stdout.log"),
            "StandardErrorPath": str(self.root_dir / "data" / "watch-macos.stderr.log"),
        }
        with plist_path.open("wb") as fh:
            plistlib.dump(payload, fh)
        self._run_launchctl(["unload", str(plist_path)], allow_fail=True)
        self._run_launchctl(["load", str(plist_path)], allow_fail=False)
        return plist_path

    def uninstall(self, label: str) -> Path:
        plist_path = self.plist_path(label)
        self._run_launchctl(["unload", str(plist_path)], allow_fail=True)
        if plist_path.exists():
            plist_path.unlink()
        return plist_path

    def print_status(self, label: str) -> str:
        result = self._run_launchctl(["list", label], allow_fail=True)
        return result.stdout.strip() if result.stdout else result.stderr.strip()

    @staticmethod
    def _run_launchctl(args: list[str], allow_fail: bool) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["launchctl", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if not allow_fail and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "launchctl failed")
        return result
