"""剪贴板监控器（macOS）— NSPasteboard changeCount 轮询

契约与 Windows 版 clipboard_monitor.py 对齐：ClipboardRecord 含 timestamp 字段。
pyobjc 调用延迟 import，非 darwin 平台 import 本模块不崩。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ClipboardRecord:
    """剪贴板记录（macOS）"""
    content: str
    timestamp: float = field(default_factory=time.time)
    source_process: str = ""
    source_window: str = ""


class ClipboardMonitor:
    """剪贴板变化监控器（macOS）

    通过轮询 NSPasteboard.changeCount 检测变化；macOS 不暴露“谁复制了”，
    故 source_process 用前台应用名近似。
    """

    def __init__(
        self,
        on_change: Callable[[ClipboardRecord], None],
        max_length: int = 10240,
        poll_interval: float = 0.5,
    ):
        self._on_change = on_change
        self._max_length = max_length
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._last_count: int | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True, name="ClipboardMonitorMac")
        self._thread.start()
        logger.info("ClipboardMonitor(macOS)已启动")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("ClipboardMonitor(macOS)已停止")

    def _poll_loop(self):
        from AppKit import NSPasteboard, NSStringPboardType

        while not self._stop_event.is_set():
            try:
                pb = NSPasteboard.generalPasteboard()
                count = pb.changeCount()
                if self._last_count is not None and count != self._last_count:
                    self._handle(pb, NSStringPboardType)
                self._last_count = count
            except Exception:
                logger.exception("剪贴板监控异常（macOS）")
            self._stop_event.wait(self._poll_interval)

    def _handle(self, pb, pb_type) -> None:
        content = pb.stringForType_(pb_type)
        if not content:
            return
        content = str(content)
        if len(content) > self._max_length:
            content = content[: self._max_length]

        proc = ""
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is not None:
                proc = str(app.localizedName() or "")
        except Exception:
            pass

        record = ClipboardRecord(
            content=content,
            timestamp=time.time(),
            source_process=proc,
        )
        try:
            self._on_change(record)
        except Exception:
            logger.exception("剪贴板回调异常")
