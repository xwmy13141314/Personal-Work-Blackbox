from __future__ import annotations

import time
from dataclasses import dataclass

from personal_recorder.collectors.macos_snapshot import MacOSSnapshotCollector
from personal_recorder.services.pipeline import ProcessingPipeline
from personal_recorder.services.state_store import StateStore


@dataclass
class MacOSWatchOptions:
    poll_interval: float = 5.0
    browser_refresh_interval: int = 300
    calendar_refresh_interval: int = 900
    terminal_refresh_interval: int = 3
    since_hours: int = 24
    max_events_per_source: int = 30


class MacOSWatcher:
    def __init__(self, pipeline: ProcessingPipeline, state_store: StateStore):
        self.pipeline = pipeline
        self.collector = MacOSSnapshotCollector()
        self.state_store = state_store
        self._last_foreground: tuple[str, str] | None = None
        self._last_clipboard: str | None = None
        self._seen_browser_keys: set[str] = set()
        self._seen_calendar_keys: set[str] = set()
        self._shell_offsets: dict[str, int] = {}
        self._load_state()

    def serve_forever(self, options: MacOSWatchOptions) -> None:
        last_browser_refresh = 0.0
        last_calendar_refresh = 0.0
        last_terminal_refresh = 0.0
        try:
            while True:
                self._collect_foreground()
                self._collect_clipboard()

                now = time.time()
                if now - last_terminal_refresh >= options.terminal_refresh_interval:
                    self._collect_terminal_history(options)
                    last_terminal_refresh = now

                if now - last_browser_refresh >= options.browser_refresh_interval:
                    self._collect_browser(options)
                    last_browser_refresh = now

                if now - last_calendar_refresh >= options.calendar_refresh_interval:
                    self._collect_calendar(options)
                    last_calendar_refresh = now

                self._save_state()
                time.sleep(options.poll_interval)
        except KeyboardInterrupt:
            self._save_state()
            return

    def _collect_foreground(self) -> None:
        events = self.collector.collect_foreground_app_snapshot()
        if not events:
            return
        event = events[0]
        key = (event.get("app_name") or "", event.get("window_title") or "")
        if key == self._last_foreground:
            return
        self._last_foreground = key
        self.pipeline.ingest(event)

    def _collect_clipboard(self) -> None:
        events = self.collector.collect_clipboard_snapshot()
        if not events:
            return
        event = events[0]
        content = event.get("content") or ""
        if content == self._last_clipboard:
            return
        self._last_clipboard = content
        self.pipeline.ingest(event)

    def _collect_browser(self, options: MacOSWatchOptions) -> None:
        events = self.collector.collect_safari_history(
            since_hours=options.since_hours,
            max_events=options.max_events_per_source,
        )
        for event in events:
            key = f"{event.get('timestamp')}|{event.get('metadata', {}).get('url', '')}"
            if key in self._seen_browser_keys:
                continue
            self._seen_browser_keys.add(key)
            self.pipeline.ingest(event)

    def _collect_calendar(self, options: MacOSWatchOptions) -> None:
        events = self.collector.collect_calendar_events(
            since_hours=options.since_hours,
            max_events=options.max_events_per_source,
        )
        for event in events:
            meta = event.get("metadata", {})
            key = f"{meta.get('calendar_name','')}|{meta.get('start_at','')}|{event.get('window_title','')}"
            if key in self._seen_calendar_keys:
                continue
            self._seen_calendar_keys.add(key)
            self.pipeline.ingest(event)

    def _collect_terminal_history(self, options: MacOSWatchOptions) -> None:
        for shell_name, path in self.collector.history_files():
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            start_index = self._shell_offsets.get(shell_name, max(0, len(lines) - options.max_events_per_source))
            new_lines = lines[start_index:]
            for line in new_lines:
                event = self.collector.parse_history_line(shell_name, line)
                if event:
                    self.pipeline.ingest(event)
            self._shell_offsets[shell_name] = len(lines)

    def _load_state(self) -> None:
        data = self.state_store.load()
        if not data:
            return
        fg = data.get("last_foreground")
        if isinstance(fg, list) and len(fg) == 2:
            self._last_foreground = (fg[0], fg[1])
        self._last_clipboard = data.get("last_clipboard")
        self._seen_browser_keys = set(data.get("seen_browser_keys", []))
        self._seen_calendar_keys = set(data.get("seen_calendar_keys", []))
        self._shell_offsets = {
            key: int(value) for key, value in data.get("shell_offsets", {}).items()
        }

    def _save_state(self) -> None:
        data = {
            "last_foreground": list(self._last_foreground) if self._last_foreground else None,
            "last_clipboard": self._last_clipboard,
            "seen_browser_keys": list(sorted(self._seen_browser_keys))[-200:],
            "seen_calendar_keys": list(sorted(self._seen_calendar_keys))[-200:],
            "shell_offsets": self._shell_offsets,
        }
        self.state_store.save(data)
