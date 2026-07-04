"""键盘监听器 — 基于 pynput 的低级键盘钩子"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)


class KeyEventType(Enum):
    PRESS = auto()
    RELEASE = auto()


class KeyEvent:
    """键盘事件"""

    def __init__(self, event_type: KeyEventType, key, char: str | None = None):
        self.event_type = event_type
        self.key = key
        self.char = char
        self.timestamp = time.time()

    @property
    def is_enter(self) -> bool:
        return self.key == keyboard.Key.enter

    @property
    def is_backspace(self) -> bool:
        return self.key == keyboard.Key.backspace

    @property
    def is_delete(self) -> bool:
        return self.key == keyboard.Key.delete

    @property
    def is_tab(self) -> bool:
        return self.key == keyboard.Key.tab

    @property
    def is_ctrl(self) -> bool:
        return self.key == keyboard.Key.ctrl or self.key == keyboard.Key.ctrl_l or self.key == keyboard.Key.ctrl_r

    @property
    def is_alt(self) -> bool:
        return self.key == keyboard.Key.alt or self.key == keyboard.Key.alt_l or self.key == keyboard.Key.alt_r

    @property
    def is_arrow(self) -> bool:
        return self.key in (
            keyboard.Key.up, keyboard.Key.down,
            keyboard.Key.left, keyboard.Key.right,
        )

    @property
    def is_escape(self) -> bool:
        return self.key == keyboard.Key.esc

    @property
    def is_printable_char(self) -> bool:
        return self.char is not None and len(self.char) == 1 and self.char.isprintable()

    def __repr__(self):
        char_info = f", char={self.char!r}" if self.char else ""
        return f"KeyEvent({self.event_type.name}, key={self.key}{char_info})"


class KeyboardHook:
    """键盘监听器

    通过 pynput 的 Listener 捕获键盘事件，转换为 KeyEvent 对象后
    传递给处理回调。
    """

    def __init__(
        self,
        on_event: Callable[[KeyEvent], None],
        capture_hotkeys: bool = True,
    ):
        """
        Args:
            on_event: 键盘事件回调
            capture_hotkeys: 是否记录快捷键组合
        """
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys
        self._listener: keyboard.Listener | None = None

        # 修饰键状态追踪
        self._ctrl_pressed = False
        self._alt_pressed = False
        self._shift_pressed = False

    def start(self):
        """启动键盘监听"""
        if self._listener:
            return

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.info("KeyboardHook 已启动")

    def stop(self):
        """停止键盘监听"""
        if self._listener:
            self._listener.stop()
            self._listener = None
        logger.info("KeyboardHook 已停止")

    def _on_press(self, key):
        """按键按下回调"""
        try:
            # 更新修饰键状态
            if isinstance(key, keyboard.Key):
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._ctrl_pressed = True
                elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._alt_pressed = True
                elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self._shift_pressed = True

                # 特殊键处理
                event = KeyEvent(KeyEventType.PRESS, key)

                # Enter/Backspace/Delete 始终传递
                if key in (keyboard.Key.enter, keyboard.Key.backspace, keyboard.Key.delete, keyboard.Key.tab):
                    self._on_event(event)
                # 方向键和 Escape 仅在 capture_hotkeys 时传递
                elif self._capture_hotkeys:
                    self._on_event(event)
            else:
                # 普通字符键
                char = getattr(key, 'char', None) or str(key) if hasattr(key, 'char') else str(key)
                event = KeyEvent(KeyEventType.PRESS, key, char=char)
                self._on_event(event)
        except Exception:
            logger.exception("键盘事件处理异常")

    def _on_release(self, key):
        """按键释放回调"""
        try:
            if isinstance(key, keyboard.Key):
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._ctrl_pressed = False
                elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._alt_pressed = False
                elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self._shift_pressed = False
        except Exception:
            logger.exception("键盘释放事件处理异常")

    @property
    def is_ctrl_held(self) -> bool:
        return self._ctrl_pressed

    @property
    def is_alt_held(self) -> bool:
        return self._alt_pressed

    @property
    def is_shift_held(self) -> bool:
        return self._shift_pressed
