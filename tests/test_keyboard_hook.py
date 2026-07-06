"""KeyboardHook 与 IME 消息钩子（WH_GETMESSAGE 方案）单元测试

测试覆盖：
1. IMEMessageHook._hook_callback 对 WM_IME_COMPOSITION + GCS_RESULTSTR 的识别与发射
2. 钩子回调对非 IME 消息、不含 GCS_RESULTSTR 标志消息的忽略
3. CallNextHookEx 始终被调用（保证消息链不阻断）
4. IMEMessageHook.start/stop 生命周期（安装/卸载钩子）
5. KeyboardHook._on_ime_result_from_hook 去重逻辑（与兜底方案共享缓存）
"""

import ctypes
import ctypes.wintypes
from unittest.mock import MagicMock, patch

import pytest

from src.collector import keyboard_hook
from src.collector.keyboard_hook import (
    KeyboardHook,
    KeyEventType,
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

    # 保持 MSG 对象引用，防止被 GC 回收导致地址失效
    _keepalive: list = []

    def _make_msg(self, message: int, lparam: int, hwnd: int = 12345) -> int:
        """构造一个伪造的 MSG 结构体，返回其内存地址

        注意：MSG 对象必须保持引用存活，否则地址在 GC 后失效。
        """
        msg = MSG()
        msg.hwnd = hwnd
        msg.message = message
        msg.wParam = 0
        msg.lParam = lparam
        msg.time = 0
        msg.pt = ctypes.wintypes.POINT(0, 0)
        self._keepalive.append(msg)  # 防止 GC 回收
        return ctypes.addressof(msg)

    def test_callback_emits_on_ime_composition_with_resultstr(self):
        """钩子回调在 WM_IME_COMPOSITION + GCS_RESULTSTR 时应发射组合结果"""
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
        """钩子回调应忽略非 WM_IME_COMPOSITION 消息"""
        results: list[str] = []
        hook = IMEMessageHook(on_ime_result=lambda r: results.append(r))
        # WM_KEYDOWN = 0x0100，非 IME 消息
        msg_addr = self._make_msg(0x0100, 0)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 0

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_get_ime_result_string") as mock_get:
            hook._hook_callback(HC_ACTION, 0, msg_addr)

        assert results == []
        mock_get.assert_not_called()

    def test_callback_ignores_ime_without_resultstr_flag(self):
        """钩子回调应忽略不含 GCS_RESULTSTR 标志的 WM_IME_COMPOSITION"""
        results: list[str] = []
        hook = IMEMessageHook(on_ime_result=lambda r: results.append(r))
        # lParam 只有 GCS_COMPSTR(0x0008)，不含 GCS_RESULTSTR(0x0800)
        msg_addr = self._make_msg(WM_IME_COMPOSITION, 0x0008)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 0

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_get_ime_result_string") as mock_get:
            hook._hook_callback(HC_ACTION, 0, msg_addr)

        assert results == []
        mock_get.assert_not_called()

    def test_callback_always_calls_call_next_hook(self):
        """钩子回调应始终调用 CallNextHookEx，即使 nCode != HC_ACTION"""
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.CallNextHookEx.return_value = 42

        with patch.object(keyboard_hook, "_user32", mock_user32):
            # nCode = -1（非 HC_ACTION），lParam = 0
            ret = hook._hook_callback(-1, 0, 0)

        assert ret == 42
        mock_user32.CallNextHookEx.assert_called_once()


# ==================== IMEMessageHook 生命周期测试 ====================

@pytest.mark.skipif(not _HAS_IMM, reason="需要 Windows IMM / 消息钩子 API")
class TestIMEMessageHookLifecycle:
    """IMEMessageHook.start/stop 生命周期测试（mock Windows API）"""

    def test_start_installs_wh_getmessage_hook(self):
        """start 应通过 SetWindowsHookExW 安装 WH_GETMESSAGE 钩子"""
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.SetWindowsHookExW.return_value = 999  # 假钩子句柄
        mock_kernel32 = MagicMock()
        mock_kernel32.GetModuleHandleW.return_value = 888

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_kernel32", mock_kernel32):
            hook.start()

        assert hook.is_running is True
        mock_kernel32.GetModuleHandleW.assert_called_once_with(None)
        mock_user32.SetWindowsHookExW.assert_called_once()
        # 验证第一个参数是 WH_GETMESSAGE
        call_args = mock_user32.SetWindowsHookExW.call_args
        assert call_args[0][0] == WH_GETMESSAGE

    def test_stop_unhooks_and_resets_state(self):
        """stop 应调用 UnhookWindowsHookEx 并重置状态"""
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
        """重复调用 start 不应重复安装钩子"""
        hook = IMEMessageHook(on_ime_result=lambda r: None)

        mock_user32 = MagicMock()
        mock_user32.SetWindowsHookExW.return_value = 999
        mock_kernel32 = MagicMock()
        mock_kernel32.GetModuleHandleW.return_value = 888

        with patch.object(keyboard_hook, "_user32", mock_user32), \
             patch.object(keyboard_hook, "_kernel32", mock_kernel32):
            hook.start()
            hook.start()  # 重复调用

        mock_user32.SetWindowsHookExW.assert_called_once()


# ==================== KeyboardHook._on_ime_result_from_hook 去重测试 ====================

class TestKeyboardHookIMEResultDedup:
    """KeyboardHook._on_ime_result_from_hook 去重逻辑测试

    这些测试不依赖 Windows API（_on_ime_result_from_hook 仅做去重和事件发射），
    可在任意平台运行。
    """

    def test_hook_result_emitted_once(self):
        """消息钩子结果应被发射一次"""
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))

        hook._on_ime_result_from_hook("你好")

        assert len(events) == 1
        assert events[0].char == "你好"
        assert events[0].is_ime_composition is True
        assert events[0].event_type == KeyEventType.PRESS

    def test_duplicate_result_not_emitted(self):
        """相同组合结果不应重复发射（与兜底方案共享去重缓存）"""
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))

        hook._on_ime_result_from_hook("你好")
        hook._on_ime_result_from_hook("你好")  # 相同结果

        assert len(events) == 1

    def test_different_result_emitted(self):
        """不同的组合结果应分别发射"""
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))

        hook._on_ime_result_from_hook("你好")
        hook._on_ime_result_from_hook("世界")

        assert len(events) == 2
        assert events[0].char == "你好"
        assert events[1].char == "世界"

    def test_empty_result_not_emitted(self):
        """空结果不应被发射"""
        events = []
        hook = KeyboardHook(on_event=lambda e: events.append(e))

        hook._on_ime_result_from_hook("")

        assert events == []
