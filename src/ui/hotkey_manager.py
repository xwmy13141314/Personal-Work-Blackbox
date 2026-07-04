"""全局快捷键管理"""

from __future__ import annotations

import logging
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyManager:
    """全局快捷键管理器

    Ctrl+Alt+P: 暂停/恢复采集
    Ctrl+Alt+R: 导出今日日志
    Ctrl+Alt+N: 隐私模式
    """

    def __init__(
        self,
        on_toggle_pause: Callable[[], None],
        on_export: Callable[[], None],
        on_privacy_mode: Callable[[], None],
    ):
        self._on_toggle_pause = on_toggle_pause
        self._on_export = on_export
        self._on_privacy_mode = on_privacy_mode
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self):
        """注册全局快捷键"""
        try:
            self._listener = keyboard.GlobalHotKeys({
                '<ctrl>+<alt>+p': self._on_toggle_pause,
                '<ctrl>+<alt>+r': self._on_export,
                '<ctrl>+<alt>+n': self._on_privacy_mode,
            })
            self._listener.start()
            logger.info("全局快捷键已注册")
        except Exception:
            logger.exception("注册全局快捷键失败（可能需要管理员权限）")

    def stop(self):
        """注销快捷键"""
        if self._listener:
            self._listener.stop()
            self._listener = None
