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

    def collect_calendar_events(self, since_hours: int, max_events: int) -> list[dict]:
        script = f'''
        set horizonDate to (current date) - ({since_hours} * hours)
        tell application "Calendar"
            set outputLines to {{}}
            repeat with cal in calendars
                set matchedEvents to (every event of cal whose start date ≥ horizonDate)
                repeat with ev in matchedEvents
                    set eventTitle to summary of ev
                    set eventStart to start date of ev
                    set eventEnd to end date of ev
                    set eventLine to (name of cal) & "||" & eventTitle & "||" & ((eventStart as «class isot») as text) & "||" & ((eventEnd as «class isot») as text)
                    set end of outputLines to eventLine
                end repeat
            end repeat
            return outputLines as string
        end tell
        '''
        output = self._run_osascript(script)
        if not output:
            return []
        events: list[dict] = []
        for line in output.split(", "):
            parts = line.split("||")
            if len(parts) != 4:
                continue
            calendar_name, title, start_at, end_at = parts
            events.append(
                {
                    "source": "calendar_event",
                    "timestamp": self._coerce_osascript_iso(start_at),
                    "app_name": "Calendar",
                    "window_title": title,
                    "content": f"日历事件：{title}",
                    "tags": ["calendar", calendar_name],
                    "metadata": {
                        "calendar_name": calendar_name,
                        "start_at": start_at,
                        "end_at": end_at,
                    },
                }
            )
            if len(events) >= max_events:
                break
        return events

    def check_permissions(self) -> list[dict]:
        checks = []

        safari_db = self._home / "Library/Safari/History.db"
        checks.append(
            {
                "permission": "Safari History",
                "status": "ok" if safari_db.exists() else "missing",
                "detail": str(safari_db),
            }
        )

        pbpaste = shutil.which("pbpaste")
        checks.append(
            {
                "permission": "Clipboard Access",
                "status": "ok" if pbpaste else "missing",
                "detail": pbpaste or "pbpaste not found",
            }
        )

        osascript = shutil.which("osascript")
        checks.append(
            {
                "permission": "AppleScript",
                "status": "ok" if osascript else "missing",
                "detail": osascript or "osascript not found",
            }
        )

        foreground = self.collect_foreground_app_snapshot()
        checks.append(
            {
                "permission": "Accessibility / Foreground App",
                "status": "ok" if foreground else "needs_attention",
                "detail": "If empty, grant Accessibility to Terminal or your runtime host.",
            }
        )

        calendar_probe = self.collect_calendar_events(since_hours=24, max_events=1)
        checks.append(
            {
                "permission": "Calendar Access",
                "status": "ok" if calendar_probe else "needs_attention",
                "detail": "If empty, macOS may require Calendar permission or there may be no recent events.",
            }
        )

        return checks

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

    @staticmethod
    def _coerce_osascript_iso(value: str) -> str:
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            return cleaned.replace("Z", "+00:00")
        return cleaned
