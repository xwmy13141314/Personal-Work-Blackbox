from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


class MacOSSnapshotCollector:
    def __init__(self) -> None:
        self._home = Path.home()

    def collect_safari_history(self, since_hours: int, max_events: int) -> list[dict]:
        history_path = self._home / "Library/Safari/History.db"
        if not history_path.exists():
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        events: list[dict] = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                copied = Path(tmpdir) / "SafariHistory.db"
                shutil.copy2(history_path, copied)
                conn = sqlite3.connect(copied)
                rows = conn.execute(
                    """
                    SELECT history_items.url, history_visits.title, history_visits.visit_time
                    FROM history_visits
                    JOIN history_items ON history_items.id = history_visits.history_item
                    ORDER BY history_visits.visit_time DESC
                    LIMIT ?
                    """,
                    (max_events,),
                ).fetchall()
                conn.close()
        except Exception:
            return []
        for url, title, visit_time in rows:
            visited_at = self._safari_time_to_datetime(visit_time)
            if visited_at < cutoff:
                continue
            events.append(
                {
                    "source": "safari_history",
                    "timestamp": visited_at.astimezone().replace(tzinfo=None).isoformat(timespec="seconds"),
                    "app_name": "safari",
                    "window_title": title or url,
                    "content": f"Safari 浏览：{title or url}",
                    "tags": ["browser", "safari"],
                    "metadata": {"url": url, "browser": "safari"},
                }
            )
        return events

    def collect_foreground_app_snapshot(self) -> list[dict]:
        script = (
            'tell application "System Events" to get name of first application process whose frontmost is true'
        )
        app_name = self._run_osascript(script)
        if not app_name:
            return []
        window_title = self._run_osascript(
            f'tell application "System Events" to tell process "{app_name}" to '
            'try\n'
            'set windowName to name of front window\n'
            'on error\n'
            'set windowName to ""\n'
            'end try\n'
            'return windowName'
        )
        now = datetime.now().isoformat(timespec="seconds")
        return [
            {
                "source": "macos_foreground",
                "timestamp": now,
                "app_name": app_name,
                "window_title": window_title or app_name,
                "content": f"当前前台应用：{app_name}" + (f" / {window_title}" if window_title else ""),
                "tags": ["macos", "foreground"],
                "metadata": {"collector": "osascript"},
            }
        ]

    def collect_clipboard_snapshot(self) -> list[dict]:
        try:
            result = subprocess.run(
                ["pbpaste"],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return []
        content = result.stdout.strip()
        if not content:
            return []
        return [
            {
                "source": "macos_clipboard",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "app_name": "clipboard",
                "window_title": "pbpaste",
                "content": content[:1000],
                "tags": ["macos", "clipboard"],
                "sensitivity": "high",
                "metadata": {"collector": "pbpaste", "content_length": len(content)},
            }
        ]

    @staticmethod
    def _run_osascript(script: str) -> str:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    @staticmethod
    def _safari_time_to_datetime(value: float) -> datetime:
        epoch_start = datetime(2001, 1, 1, tzinfo=timezone.utc)
        return epoch_start + timedelta(seconds=value)
