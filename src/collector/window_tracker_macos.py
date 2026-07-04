"""窗口活动追踪器（macOS）— NSWorkspace 前台应用 + Quartz 窗口标题

契约与 Windows 版 window_tracker.py 对齐：
- WindowContext 含 is_valid 属性、timestamp 字段
- on_switch(from_ctx, to_ctx, duration_seconds)
- current_context 属性

pyobjc 调用延迟到方法内 import，保证非 darwin 平台 import 本模块不崩。
缺“屏幕录制”权限时 kCGWindowName 取不到 → window_title 为空，
process_name 仍有效（来自 NSWorkspace，无需该权限）。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class WindowContext:
    """窗口上下文快照（macOS）"""
    process_name: str = ""
    window_title: str = ""
    bundle_id: str = ""
    pid: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        # macOS 无 hwnd，以前台进程名非空判定有效
        return bool(self.process_name)


class WindowTracker:
    """前台窗口追踪器（macOS）"""

    def __init__(
        self,
        on_switch: Callable[[WindowContext, WindowContext, float], None],
        poll_interval: float = 1.0,
    ):
        self._on_switch = on_switch
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._last_ctx = WindowContext()
        self._last_switch_time = time.time()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True, name="WindowTrackerMac")
        self._thread.start()
        logger.info("WindowTracker(macOS)已启动，轮询间隔 %.1f 秒", self._poll_interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WindowTracker(macOS)已停止")

    @property
    def current_context(self) -> WindowContext:
        return self._last_ctx

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                ctx = self._snapshot()
                if not ctx.is_valid:
                    self._stop_event.wait(self._poll_interval)
                    continue

                switched = (
                    ctx.process_name != self._last_ctx.process_name
                    or ctx.window_title != self._last_ctx.window_title
                )
                if switched:
                    now = time.time()
                    duration = now - self._last_switch_time
                    if self._last_ctx.is_valid:
                        self._on_switch(self._last_ctx, ctx, duration)
                    self._last_switch_time = now
                self._last_ctx = ctx
            except Exception:
                logger.exception("窗口轮询异常（macOS）")
            self._stop_event.wait(self._poll_interval)

    def _snapshot(self) -> WindowContext:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return WindowContext()
        name = str(app.localizedName() or "")
        bid = str(app.bundleIdentifier() or "")
        pid = int(app.processIdentifier() or 0)
        title = self._window_title_for_pid(pid)
        return WindowContext(
            process_name=name,
            window_title=title,
            bundle_id=bid,
            pid=pid,
            timestamp=time.time(),
        )

    @staticmethod
    def _window_title_for_pid(pid: int) -> str:
        try:
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
                kCGWindowOwnerPID,
                kCGWindowName,
                kCGWindowLayer,
            )
            windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
            for w in windows:
                if w.get(kCGWindowOwnerPID) == pid and w.get(kCGWindowLayer, 0) == 0:
                    name = w.get(kCGWindowName, "")
                    if name:
                        return str(name)
        except Exception:
            pass
        return ""
