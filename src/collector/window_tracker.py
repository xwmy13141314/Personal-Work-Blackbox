"""窗口活动追踪器 — macOS 原生实现（AppKit NSWorkspace）

通过轮询 NSWorkspace.sharedWorkspace().frontmostApplication 获取前台应用，
对比变化触发切换回调。与 Windows 版 WindowContext / WindowTracker 接口一致。

权限要求：辅助功能（Accessibility）——获取窗口标题需通过 AXUIElement，
未授权时 window_title 可能为空，但不影响应用名/进程采集。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)

# ==================== macOS AppKit / ApplicationServices 绑定 ====================
try:
    from AppKit import NSWorkspace
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCreateSystemWide,
            AXUIElementCopyAttributeValue,
        )
    except ImportError:
        # 某些 PyObjC 版本 AX API 在 HIServices 而非 ApplicationServices
        from HIServices import (
            AXUIElementCreateApplication,
            AXUIElementCreateSystemWide,
            AXUIElementCopyAttributeValue,
        )
    # AX 属性用字符串字面量（"AXFocusedWindow"/"AXTitle"），避免常量导入差异
    _HAS_MAC_API = True
except Exception:
    _HAS_MAC_API = False
    # 回退：用 osascript 获取前台应用（不依赖 PyObjC，但较慢且无进程信息）
    NSWorkspace = None
    logger.warning("AppKit 不可用，将回退到 osascript 轮询（功能受限）")


@dataclass
class WindowContext:
    """窗口上下文快照（与 Windows 版字段一致）

    Mac 版 hwnd 字段保留但语义为进程 PID（Mac 无 HWND 概念）。
    """
    hwnd: int = 0          # Mac 版存 PID
    process_name: str = ""  # 应用名（如 "Safari"），对应 Windows 的 .exe 名
    window_title: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        return self.hwnd != 0


class WindowTracker:
    """前台窗口追踪器（macOS NSWorkspace 轮询）"""

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
        logger.info("WindowTracker 已启动（NSWorkspace 轮询），间隔 %.1f 秒", self._poll_interval)

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

    def capture_current_context(self) -> WindowContext:
        """立即读取当前前台上下文，供输入事件做准确归属。

        常规轮询间隔为 1 秒；输入法确认后用户若立刻切换 App，直接读取可避免
        把文本错误写入上一条会话。
        """
        return self._capture_context()

    def _poll_loop(self):
        """轮询主循环"""
        while not self._stop_event.is_set():
            try:
                ctx = self._capture_context()
                # 用 PID 判断切换（Mac 应用名可能含大小写差异，PID 最稳定）
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
        """捕获当前前台应用上下文"""
        if _HAS_MAC_API:
            return self._capture_native()
        return self._capture_osascript()

    def _capture_native(self) -> WindowContext:
        """原生 AppKit + AX 方式捕获"""
        try:
            ws = NSWorkspace.sharedWorkspace()
            app = ws.frontmostApplication()
            if app is None:
                return WindowContext()

            pid = app.processIdentifier()
            app_name = app.localizedName() or ""
            bundle_id = app.bundleIdentifier() or ""

            # 获取窗口标题（需辅助功能权限 + AXUIElement）
            title = self._get_front_window_title(pid)

            # process_name 统一用小写应用名（便于黑名单匹配，与 Windows .exe 风格对齐）
            # Mac 上无 .exe 后缀，存应用名小写
            process_name = (app_name or bundle_id or "").lower()

            return WindowContext(
                hwnd=pid,
                process_name=process_name,
                window_title=title,
                timestamp=time.time(),
            )
        except Exception:
            logger.debug("原生窗口捕获异常", exc_info=True)
            return WindowContext()

    @staticmethod
    def _get_front_window_title(pid: int) -> str:
        """通过 AXUIElement 获取前台应用窗口标题（需辅助功能权限）

        PyObjC 用法：AXUIElementCopyAttributeValue(elem, attr, None) 返回 (error, value)，
        error == 0 (kAXErrorSuccess) 表示成功。
        """
        try:
            app_ref = AXUIElementCreateApplication(pid)
            # 有些 Electron/浏览器应用不把当前窗口挂到应用根元素；系统级焦点
            # 才是实际输入窗口。因此按“应用焦点 -> 系统焦点窗口 -> 系统焦点应用”回退。
            candidates = [app_ref]
            system_ref = AXUIElementCreateSystemWide()
            for attribute in ("AXFocusedWindow", "AXFocusedApplication"):
                err, value = AXUIElementCopyAttributeValue(system_ref, attribute, None)
                if err == 0 and value:
                    candidates.append(value)

            for candidate in candidates:
                err, window_ref = AXUIElementCopyAttributeValue(candidate, "AXFocusedWindow", None)
                windows = [window_ref] if err == 0 and window_ref else [candidate]
                for window in windows:
                    err2, title_ref = AXUIElementCopyAttributeValue(window, "AXTitle", None)
                    if err2 == 0 and title_ref:
                        return str(title_ref)
            return ""
        except Exception:
            return ""

    @staticmethod
    def _capture_osascript() -> WindowContext:
        """osascript 回退方案（无 PyObjC 时）"""
        import subprocess
        try:
            app_name = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip()
            if not app_name:
                return WindowContext()
            return WindowContext(
                hwnd=0,
                process_name=app_name.lower(),
                window_title=app_name,
                timestamp=time.time(),
            )
        except Exception:
            return WindowContext()
