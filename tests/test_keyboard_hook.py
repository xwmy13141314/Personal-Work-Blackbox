"""KeyboardHook 单元测试

测试覆盖：
1. KeyboardHook._on_ime_result_from_hook 去重逻辑
2. KeyEvent 属性测试（pynput Key 枚举）
"""

import ctypes
import ctypes.wintypes
from unittest.mock import MagicMock, patch

import pytest

from pynput import keyboard

from src.collector import keyboard_hook
from src.collector.keyboard_hook import (
    KeyboardHook,
    KeyEventType,
    KeyEvent,
    HC_ACTION,
    WM_IME_COMPOSITION,
    GCS_RESULTSTR,
    _HAS_WIN_API,
)


# ==================== KeyboardHook IME 去重测试 ====================

class TestKeyboardHookIMEResultDedup:
    """KeyboardHook IME 结果去重逻辑测试"""

    def test_hook_result_emitted_once(self):
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))
        hook._on_ime_result_from_hook("你好")

        assert len(events) == 1
        assert events[0].char == "你好"
        assert events[0].is_ime_composition is True
        assert events[0].event_type == KeyEventType.PRESS

    def test_duplicate_result_not_emitted(self):
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))
        hook._on_ime_result_from_hook("你好")
        hook._on_ime_result_from_hook("你好")

        assert len(events) == 1

    def test_different_result_emitted(self):
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))
        hook._on_ime_result_from_hook("你好")
        hook._on_ime_result_from_hook("世界")

        assert len(events) == 2
        assert events[0].char == "你好"
        assert events[1].char == "世界"

    def test_empty_result_not_emitted(self):
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))
        hook._on_ime_result_from_hook("")

        assert events == []


# ==================== KeyEvent 属性测试 ====================

class TestKeyEventProperties:
    """KeyEvent 属性测试 — 验证 pynput Key 枚举后的行为"""

    def test_enter_detection(self):
        event = KeyEvent(KeyEventType.PRESS, keyboard.Key.enter)
        assert event.is_enter is True
        assert event.is_backspace is False

    def test_backspace_detection(self):
        event = KeyEvent(KeyEventType.PRESS, keyboard.Key.backspace)
        assert event.is_backspace is True
        assert event.is_enter is False

    def test_tab_detection(self):
        event = KeyEvent(KeyEventType.PRESS, keyboard.Key.tab)
        assert event.is_tab is True

    def test_delete_detection(self):
        event = KeyEvent(KeyEventType.PRESS, keyboard.Key.delete)
        assert event.is_delete is True

    def test_escape_detection(self):
        event = KeyEvent(KeyEventType.PRESS, keyboard.Key.esc)
        assert event.is_escape is True

    def test_arrow_detection(self):
        for key in (keyboard.Key.up, keyboard.Key.down, keyboard.Key.left, keyboard.Key.right):
            event = KeyEvent(KeyEventType.PRESS, key)
            assert event.is_arrow is True

    def test_printable_char(self):
        event = KeyEvent(KeyEventType.PRESS, "a", char="a")
        assert event.is_printable_char is True

    def test_non_printable_multi_char(self):
        event = KeyEvent(KeyEventType.PRESS, None, char="你好", is_ime_composition=True)
        assert event.is_printable_char is False
        assert event.is_ime_text is True

    def test_ctrl_a_detection(self):
        """Ctrl+A 检测（控制字符 \x01）"""
        event = KeyEvent(KeyEventType.PRESS, "a", char="\x01", ctrl_pressed=True)
        assert event.is_ctrl_a is True

    def test_ctrl_a_without_ctrl(self):
        event = KeyEvent(KeyEventType.PRESS, "a", char="\x01", ctrl_pressed=False)
        assert event.is_ctrl_a is False

    def test_repr(self):
        event = KeyEvent(KeyEventType.PRESS, keyboard.Key.enter)
        assert "enter" in repr(event).lower()
