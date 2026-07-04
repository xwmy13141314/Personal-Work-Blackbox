"""剪贴板监控器 — 监听系统剪贴板变化"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable

import win32clipboard
import win32con

logger = logging.getLogger(__name__)


@dataclass
class ClipboardRecord:
    """剪贴板记录"""
    content: str
    timestamp: float = field(default_factory=time.time)
    source_process: str = ""
    source_window: str = ""


class ClipboardMonitor:
    """剪贴板变化监控器

    通过轮询方式检测剪贴板内容变化。
    使用 pywin32 的 win32clipboard 替代原始 ctypes 调用，
    避免 64 位环境下指针截断导致段错误。
    """

    def __init__(
        self,
        on_change: Callable[[ClipboardRecord], None],
        max_length: int = 10240,
        poll_interval: float = 0.5,
    ):
        """
        Args:
            on_change: 剪贴板内容变化回调
            max_length: 单条记录最大长度
            poll_interval: 轮询间隔（秒）
        """
        self._on_change = on_change
        self._max_length = max_length
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._last_content: str = ""

    def start(self):
        """启动监控"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        # 初始化时读取当前剪贴板内容作为基线
        self._last_content = self._read_clipboard() or ""
        self._thread = Thread(target=self._poll_loop, daemon=True, name="ClipboardMonitor")
        self._thread.start()
        logger.info("ClipboardMonitor 已启动")

    def stop(self):
        """停止监控"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("ClipboardMonitor 已停止")

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                content = self._read_clipboard()
                if content and content != self._last_content:
                    self._last_content = content
                    # 截断超长内容
                    truncated = len(content) > self._max_length
                    if truncated:
                        content = content[:self._max_length]

                    record = ClipboardRecord(
                        content=content,
                        timestamp=time.time(),
                    )
                    self._on_change(record)
            except Exception:
                logger.exception("剪贴板监控异常")

            self._stop_event.wait(self._poll_interval)

    @staticmethod
    def _read_clipboard() -> str | None:
        """读取剪贴板文本内容（使用 pywin32，64 位安全）"""
        try:
            win32clipboard.OpenClipboard()
            try:
                handle = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                if handle:
                    return handle
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            logger.debug("读取剪贴板失败")
        return None
