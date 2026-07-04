"""macOS 原生采集桥接：复用 Windows 端的 adapter + 缓冲器 + inbox 落盘。

结构与 BlackboxRuntimeBridge 一致，但：
- 不依赖外部采集项目（三器均为内置 pyobjc 实现）；
- 平台守卫为 darwin；
- 四个回调契约与 Windows 端完全相同，因此 BlackboxAdapter / KeyboardTextBuffer 零改动复用。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from personal_recorder.bridges.blackbox_runtime import KeyboardTextBuffer
from personal_recorder.collectors.blackbox import BlackboxAdapter
from personal_recorder.collectors.file_drop import FileDropCollector
from personal_recorder.collectors.macos_collectors import (
    MacClipboardMonitor,
    MacKeyboardHook,
    MacWindowTracker,
)


class MacRuntimeBridge:
    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
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
        if sys.platform != "darwin":
            raise RuntimeError("Mac runtime bridge requires macOS (darwin)")

        print("[bridge-macos] 启动采集：", end="")
        parts = []
        if enable_window:
            parts.append("窗口")
        if enable_clipboard:
            parts.append("剪贴板")
        if enable_keyboard:
            parts.append("键盘(需输入监控权限)")
        print("/".join(parts) or "无")
        print(f"[bridge-macos] 事件落盘：{self.inbox_dir}（Ctrl+C 退出）")

        runtime_objects = []

        if enable_window:
            tracker = MacWindowTracker(on_switch=self._on_window_switch, poll_interval=poll_interval)
            tracker.start()
            runtime_objects.append(tracker)

        if enable_clipboard:
            monitor = MacClipboardMonitor(on_change=self._on_clipboard_change, max_length=clipboard_max_length)
            monitor.start()
            runtime_objects.append(monitor)

        if enable_keyboard:
            self._text_buffer = KeyboardTextBuffer(
                on_commit=self._on_text_commit,
                timeout=keyboard_buffer_timeout,
                max_length=keyboard_buffer_max_length,
            )
            hook = MacKeyboardHook(on_event=self._on_keyboard_event, capture_hotkeys=capture_hotkeys)
            hook.start()
            runtime_objects.append(hook)  # 权限缺失会自动降级，不抛异常

        try:
            while True:
                if self._text_buffer:
                    self._text_buffer.flush_if_idle()
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[bridge-macos] 正在停止...")
        finally:
            if self._text_buffer:
                self._text_buffer.flush()
            for obj in reversed(runtime_objects):
                stop = getattr(obj, "stop", None)
                if callable(stop):
                    stop()

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
