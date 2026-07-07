"""KeyboardHook 与 IME 消息钩子单元测试

测试覆盖：
1. IMEMessageHook._hook_callback 对 WM_IME_COMPOSITION + GCS_RESULTSTR 的识别与发射
2. 钩子回调对非 IME 消息、不含 GCS_RESULTSTR 标志消息的忽略
3. CallNextHookEx 始终被调用（保证消息链不阻断）
4. IMEMessageHook.start/stop 生命周期（安装/卸载钩子）
5. KeyboardHook._on_ime_result_from_hook 去重逻辑（与兜底方案共享缓存）
6. KeyEvent 属性测试（pynput Key 枚举）
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
    IMEMessageHook,
    WH_GETMESSAGE,
    HC_ACTION,
    WM_IME_COMPOSITION,
    GCS_RESULTSTR,
    _HAS_IMM,
)

# MSG 仅在 Windows（_HAS_IMM=True）下定义，条件导入以支持跨平台测试收集
if _HAS_IMM:
    from src.collector.keyboard_hook import MSG


# ==================== IMEMessageHook 钩子回调测试 ====================

@pytest.mark.skipif(not _HAS_IMM, reason="需要 Windows IMM / 消息钩子 API")
class TestIMEMessageHookCallback:
    """IMEMessageHook._hook_callback 行为测试（mock Windows API）"""

    _keepalive: list = []

    def _make_msg(self, message: int, lparam: int, hwnd: int = 12345) -> int:
        msg = MSG()
        msg.hwnd = hwnd
        msg.message = message
        msg.wParam = 0
        msg.lParam = lparam
        msg.time = 0
        msg.pt = ctypes.wintypes.POINT(0, 0)
        self._keepalive.append(msg)
        return ctypes.addressof(msg)

    def test_callback_emits_on_ime_composition_with_resultstr(self):
        results: list[str] = []
        hook = IMEMessageHook(on_ime_result=lambda r: results.append(r))
        msg_addr = self._make_msg(WM_IME_COMPOSITION, GCS_RESULTSTR)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 0

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_get_ime_result_string", return_value="你好"):
            ret = hook._hook_callback(HC_ACTION, 0, msg_addr)

        assert results == ["你好"]
        assert ret == 0
        mock_user32.CallNextHookEx.assert_called_once()

    def test_callback_ignores_non_ime_message(self):
        results: list[str] = []
        hook = IMEMessageHook(on_ime_result=lambda r: results.append(r))
        msg_addr = self._make_msg(0x0100, 0)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 0

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_get_ime_result_string") as mock_get:
            hook._hook_callback(HC_ACTION, 0, msg_addr)

        assert results == []
        mock_get.assert_not_called()

    def test_callback_ignores_ime_without_resultstr_flag(self):
        results: list[str] = []
        hook = IMEMessageHook(on_ime_result=lambda r: results.append(r))
        msg_addr = self._make_msg(WM_IME_COMPOSITION, 0x0008)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 0

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_get_ime_result_string") as mock_get:
            hook._hook_callback(HC_ACTION, 0, msg_addr)

        assert results == []
        mock_get.assert_not_called()

    def test_callback_always_calls_call_next_hook(self):
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 42

        with patch.object(keyboard_hook, "_user32", mock_user32):
            ret = hook._hook_callback(-1, 0, 0)

        assert ret == 42
        mock_user32.CallNextHookEx.assert_called_once()


# ==================== IMEMessageHook 生命周期测试 ====================

@pytest.mark.skipif(not _HAS_IMM, reason="需要 Windows IMM / 消息钩子 API")
class TestIMEMessageHookLifecycle:
    """IMEMessageHook.start/stop 生命周期测试（mock Windows API）"""

    def test_start_installs_wh_getmessage_hook(self):
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.SetWindowsHookExW.return_value = 999
        mock_kernel32 = MagicMock()
        mock_kernel32.GetModuleHandleW.return_value = 888

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_kernel32", mock_kernel32):
            hook.start()

        assert hook.is_running is True
        mock_kernel32.GetModuleHandleW.assert_called_once_with(None)
        mock_user32.SetWindowsHookExW.assert_called_once()
        call_args = mock_user32.SetWindowsHookExW.call_args
        assert call_args[0][0] == WH_GETMESSAGE

    def test_stop_unhooks_and_resets_state(self):
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.SetWindowsHookExW.return_value = 999
        mock_kernel32 = MagicMock()
        mock_kernel32.GetModuleHandleW.return_value = 888

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_kernel32", mock_kernel32):
            hook.start()
            assert hook.is_running
            hook.stop()

        assert hook.is_running is False
        mock_user32.UnhookWindowsHookEx.assert_called_once_with(999)

    def test_start_when_already_running_is_noop(self):
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.SetWindowsHookExW.return_value = 999
        mock_kernel32 = MagicMock()
        mock_kernel32.GetModuleHandleW.return_value = 888

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_kernel32", mock_kernel32):
            hook.start()
            hook.start()

        mock_user32.SetWindowsHookExW.assert_called_once()


# ==================== KeyboardHook._on_ime_result_from_hook 去重测试 ====================

class TestKeyboardHookIMEResultDedup:
    """KeyboardHook._on_ime_result_from_hook 去重逻辑测试"""

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
