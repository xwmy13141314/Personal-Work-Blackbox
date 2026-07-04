from __future__ import annotations

import sys
import time
from pathlib import Path

from personal_recorder.collectors.blackbox import BlackboxAdapter
from personal_recorder.collectors.file_drop import FileDropCollector


class KeyboardTextBuffer:
    def __init__(self, on_commit, timeout: float = 3.0, max_length: int = 120):
        self.on_commit = on_commit
        self.timeout = timeout
        self.max_length = max_length
        self._chars: list[str] = []
        self._last_event_at: float | None = None

    def handle_key_event(self, event) -> None:
        now = time.time()
        self.flush_if_idle(now)

        if getattr(event, "is_printable_char", False):
            self._chars.append(event.char)
            self._last_event_at = now
            if len(self._chars) >= self.max_length:
                self.flush()
            return

        if getattr(event, "is_backspace", False):
            if self._chars:
                self._chars.pop()
            self._last_event_at = now
            return

        if getattr(event, "is_enter", False) or getattr(event, "is_tab", False):
            self.flush()
            return

    def flush_if_idle(self, now: float | None = None) -> None:
        if not self._chars or self._last_event_at is None:
            return
        current = now or time.time()
        if current - self._last_event_at >= self.timeout:
            self.flush()

    def flush(self) -> None:
        text = "".join(self._chars).strip()
        self._chars.clear()
        self._last_event_at = None
        if text:
            self.on_commit(text)


class BlackboxRuntimeBridge:
    def __init__(self, inbox_dir: Path, blackbox_src: Path):
        self.inbox_dir = inbox_dir
        self.blackbox_src = blackbox_src
        self.adapter = BlackboxAdapter()
        self.file_drop = FileDropCollector(inbox_dir)
        self._current_window = {"process_name": "", "window_title": ""}
        self._text_buffer: KeyboardTextBuffer | None = None

    def run(
        self,
        enable_window: bool = True,
        enable_clipboard: bool = True,
        enable_keyboard: bool = True,
        clipboard_max_length: int = 400,
        poll_interval: float = 1.0,
        keyboard_buffer_timeout: float = 3.0,
        keyboard_buffer_max_length: int = 120,
        capture_hotkeys: bool = False,
    ) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Blackbox runtime bridge requires Windows")

        self._ensure_import_path()
        window_tracker_cls, clipboard_monitor_cls, keyboard_hook_cls = self._load_collectors()

        runtime_objects = []

        if enable_window:
            tracker = window_tracker_cls(
                on_switch=self._on_window_switch,
                poll_interval=poll_interval,
            )
            tracker.start()
            runtime_objects.append(tracker)

        if enable_clipboard:
            monitor = clipboard_monitor_cls(
                on_change=self._on_clipboard_change,
                max_length=clipboard_max_length,
            )
            monitor.start()
            runtime_objects.append(monitor)

        if enable_keyboard:
            self._text_buffer = KeyboardTextBuffer(
                on_commit=self._on_text_commit,
                timeout=keyboard_buffer_timeout,
                max_length=keyboard_buffer_max_length,
            )
            hook = keyboard_hook_cls(
                on_event=self._on_keyboard_event,
                capture_hotkeys=capture_hotkeys,
            )
            hook.start()
            runtime_objects.append(hook)

        try:
            while True:
                if self._text_buffer:
                    self._text_buffer.flush_if_idle()
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            if self._text_buffer:
                self._text_buffer.flush()
            for obj in reversed(runtime_objects):
                stop = getattr(obj, "stop", None)
                if callable(stop):
                    stop()

    def emit_text(
        self,
        text: str,
        source: str = "keyboard",
        process_name: str = "",
        window_title: str = "",
    ) -> Path:
        raw_event = self.adapter.runtime_text(
            text=text,
            source=source,
            process_name=process_name,
            window_title=window_title,
        )
        return self.file_drop.write_event(raw_event)

    def _on_window_switch(self, from_ctx, to_ctx, duration_seconds: float) -> None:
        self._current_window = {
            "process_name": getattr(to_ctx, "process_name", ""),
            "window_title": getattr(to_ctx, "window_title", ""),
        }
        raw_event = self.adapter.runtime_window_switch(
            from_process=getattr(from_ctx, "process_name", ""),
            from_title=getattr(from_ctx, "window_title", ""),
            to_process=getattr(to_ctx, "process_name", ""),
            to_title=getattr(to_ctx, "window_title", ""),
            duration_seconds=duration_seconds,
        )
        self.file_drop.write_event(raw_event)

    def _on_clipboard_change(self, record) -> None:
        raw_event = self.adapter.runtime_clipboard(
            content=getattr(record, "content", ""),
            source_process=getattr(record, "source_process", ""),
            source_window=getattr(record, "source_window", ""),
        )
        self.file_drop.write_event(raw_event)

    def _on_keyboard_event(self, event) -> None:
        if self._text_buffer:
            self._text_buffer.handle_key_event(event)

    def _on_text_commit(self, text: str) -> None:
        raw_event = self.adapter.runtime_text(
            text=text,
            source="keyboard",
            process_name=self._current_window["process_name"],
            window_title=self._current_window["window_title"],
        )
        self.file_drop.write_event(raw_event)

    def _ensure_import_path(self) -> None:
        src_path = str(self.blackbox_src)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

    def _load_collectors(self):
        try:
            from collector.clipboard_monitor import ClipboardMonitor
            from collector.keyboard_hook import KeyboardHook
            from collector.window_tracker import WindowTracker
        except ImportError:
            from src.collector.clipboard_monitor import ClipboardMonitor
            from src.collector.keyboard_hook import KeyboardHook
            from src.collector.window_tracker import WindowTracker
        return WindowTracker, ClipboardMonitor, KeyboardHook
