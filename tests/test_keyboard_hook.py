"""KeyboardHook 单元测试（macOS 版适配）

测试覆盖：
1. KeyEvent 属性测试（pynput Key 枚举）— 跨平台，Mac 版 KeyEvent 复用
2. KeyboardHook IME 去重逻辑 — Windows 专属（Mac 版 IME 由 ImeWatcher 处理，此处保留 Windows 测试并跳过）
"""

import sys

import pytest

from src.collector.keyboard_hook import (
    KeyboardHook,
    KeyEventType,
    KeyEvent,
)
from src.collector.key_types import Key


# ==================== KeyboardHook IME 去重测试（Windows 专属）===================

@pytest.mark.skip(reason="macOS 版 KeyboardHook 无 _on_ime_result_from_hook（IME 改由 ImeWatcher 处理）")
class TestKeyboardHookIMEResultDedup:
    """KeyboardHook IME 结果去重逻辑测试（Windows 版实现）"""

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


# ==================== KeyEvent 属性测试（跨平台）====================

class TestKeyEventProperties:
    """KeyEvent 属性测试 — 验证 pynput Key 枚举后的行为（Mac 版复用同一 KeyEvent）"""

    def test_enter_detection(self):
        event = KeyEvent(KeyEventType.PRESS, Key.enter)
        assert event.is_enter is True
        assert event.is_backspace is False

    def test_backspace_detection(self):
        event = KeyEvent(KeyEventType.PRESS, Key.backspace)
        assert event.is_backspace is True
        assert event.is_enter is False

    def test_tab_detection(self):
        event = KeyEvent(KeyEventType.PRESS, Key.tab)
        assert event.is_tab is True

    def test_delete_detection(self):
        event = KeyEvent(KeyEventType.PRESS, Key.delete)
        assert event.is_delete is True

    def test_escape_detection(self):
        event = KeyEvent(KeyEventType.PRESS, Key.esc)
        assert event.is_escape is True

    def test_arrow_detection(self):
        for key in (Key.up, Key.down, Key.left, Key.right):
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
        event = KeyEvent(KeyEventType.PRESS, Key.enter)
        assert "enter" in repr(event).lower()


class TestPhysicalKeyFallback:
    """即使输入法不提供 Unicode，也能保留实际按下的键。"""

    def test_letter_and_shifted_letter(self):
        assert KeyboardHook._keycode_to_ascii(0x00, False) == "a"
        assert KeyboardHook._keycode_to_ascii(0x00, True) == "A"

    def test_shifted_punctuation(self):
        assert KeyboardHook._keycode_to_ascii(0x12, True) == "!"

    def test_unknown_key_is_not_text(self):
        assert KeyboardHook._keycode_to_ascii(0x7A, False) is None

    def test_event_marks_physical_keycode_fallback(self):
        event = KeyEvent(KeyEventType.PRESS, "a", char="a", is_physical_fallback=True)
        assert event.is_physical_fallback is True
