from __future__ import annotations

import time
from dataclasses import dataclass

from personal_recorder.collectors.macos_snapshot import MacOSSnapshotCollector
from personal_recorder.services.pipeline import ProcessingPipeline


@dataclass
class MacOSWatchOptions:
    poll_interval: float = 5.0
    browser_refresh_interval: int = 300
    calendar_refresh_interval: int = 900
    since_hours: int = 24
    max_events_per_source: int = 30


class MacOSWatcher:
    def __init__(self, pipeline: ProcessingPipeline):
        self.pipeline = pipeline
        self.collector = MacOSSnapshotCollector()
        self._last_foreground: tuple[str, str] | None = None
        self._last_clipboard: str | None = None
        self._seen_browser_keys: set[str] = set()
        self._seen_calendar_keys: set[str] = set()

    def serve_forever(self, options: MacOSWatchOptions) -> None:
        last_browser_refresh = 0.0
        last_calendar_refresh = 0.0
        try:
            while True:
                self._collect_foreground()
                self._collect_clipboard()

                now = time.time()
                if now - last_browser_refresh >= options.browser_refresh_interval:
                    self._collect_browser(options)
                    last_browser_refresh = now

                if now - last_calendar_refresh >= options.calendar_refresh_interval:
                    self._collect_calendar(options)
                    last_calendar_refresh = now

                time.sleep(options.poll_interval)
        except KeyboardInterrupt:
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
