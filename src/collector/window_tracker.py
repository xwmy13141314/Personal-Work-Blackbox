"""窗口活动追踪器 — 通过 Win32 API 轮询前台窗口"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)

# Win32 API 声明
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# 进程权限
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010


@dataclass
class WindowContext:
    """窗口上下文快照"""
    hwnd: int = 0
    process_name: str = ""
    window_title: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        return self.hwnd != 0


class WindowTracker:
    """前台窗口追踪器"""

    def __init__(
        self,
        on_switch: Callable[[WindowContext, WindowContext, float], None],
        poll_interval: float = 1.0,
    ):
        """
        Args:
            on_switch: 窗口切换回调 (from_ctx, to_ctx, duration_seconds)
            poll_interval: 轮询间隔（秒）
        """
        self._on_switch = on_switch
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._last_ctx = WindowContext()
        self._last_switch_time = time.time()

    def start(self):
        """启动轮询线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True, name="WindowTracker")
        self._thread.start()
        logger.info("WindowTracker 已启动，轮询间隔 %.1f 秒", self._poll_interval)

    def stop(self):
        """停止轮询"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WindowTracker 已停止")

    @property
    def current_context(self) -> WindowContext:
        """当前窗口上下文"""
        return self._last_ctx

    def _poll_loop(self):
        """轮询主循环"""
        while not self._stop_event.is_set():
            try:
                ctx = self._capture_context()
                if ctx.hwnd != self._last_ctx.hwnd:
                    now = time.time()
                    duration = now - self._last_switch_time
                    if self._last_ctx.is_valid:
                        self._on_switch(self._last_ctx, ctx, duration)
                    self._last_ctx = ctx
                    self._last_switch_time = now
            except Exception:
                logger.exception("窗口轮询异常")
            self._stop_event.wait(self._poll_interval)

    def _capture_context(self) -> WindowContext:
        """捕获当前前台窗口上下文"""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return WindowContext()

        # 窗口标题
        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        title = title_buf.value.strip()

        # 进程名
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = self._get_process_name(pid.value)

        return WindowContext(
            hwnd=hwnd,
            process_name=process_name,
            window_title=title,
            timestamp=time.time(),
        )

    @staticmethod
    def _get_process_name(pid: int) -> str:
        """通过 PID 获取进程名"""
        try:
            PROCESS_FLAGS = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
            handle = kernel32.OpenProcess(PROCESS_FLAGS, False, pid)
            if not handle:
                return ""

            buf = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(handle, None, buf, 260)
            kernel32.CloseHandle(handle)
            return buf.value.lower()
        except Exception:
            return ""
