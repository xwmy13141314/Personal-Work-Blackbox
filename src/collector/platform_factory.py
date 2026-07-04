"""采集器平台工厂 — 按 sys.platform 提供采集器实现，统一类型符号

main.py 与 processor 仅依赖本模块导出的符号，不直接 import 平台专有采集器，
从而避免在 macOS 上 import Win32 模块（ctypes.windll / win32clipboard）即崩。

- 键盘：两端均用 pynput（跨平台），InputBuffer 零改动复用
        （macOS 需“辅助功能”权限）
- 窗口 / 剪贴板 / 空闲：Windows 用 Win32 原版，macOS 用 pyobjc 重写版
"""
from __future__ import annotations

import sys

_IS_MACOS = sys.platform == "darwin"

if _IS_MACOS:
    from .idle_detector_macos import IdleDetector, IdleState
    from .window_tracker_macos import WindowContext, WindowTracker
    from .clipboard_monitor_macos import ClipboardMonitor, ClipboardRecord
    from .keyboard_hook import KeyEvent, KeyEventType
    from .keyboard_macos import MacKeyboardAdapter as KeyboardHook  # CGEventTap（避免 pynput 主线程 TSM 崩溃）
else:
    from .idle_detector import IdleDetector, IdleState
    from .window_tracker import WindowContext, WindowTracker
    from .clipboard_monitor import ClipboardMonitor, ClipboardRecord
    from .keyboard_hook import KeyEvent, KeyboardHook


__all__ = [
    "IdleDetector",
    "IdleState",
    "WindowTracker",
    "WindowContext",
    "ClipboardMonitor",
    "ClipboardRecord",
    "KeyboardHook",
    "KeyEvent",
    "is_macos",
]


def is_macos() -> bool:
    """当前进程是否运行在 macOS（供上层做权限引导等分流）"""
    return _IS_MACOS
