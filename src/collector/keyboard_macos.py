"""macOS 键盘适配器 — 用 CGEventTap（MacKeyboardHook）替代 pynput

pynput 在 macOS 26+ 的监听线程内会调用 TSMGetInputSourceProperty（Carbon 文本输入法
API，仅限主线程），触发 _dispatch_assert_queue_fail → SIGTRAP 崩溃。

改用 personal_recorder 的 MacKeyboardHook（Quartz CGEventTap，ListenOnly 模式，
只需「输入监控」权限，比辅助功能更轻），并把它的 KeyEvent 转换为 BlackboxEngine
的 KeyEvent 契约（event_type/key/char），使 InputBuffer 零改动复用。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 注入 src 到 sys.path，使 personal_recorder 成为顶层包（与 snapshot_importer 同）
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


class MacKeyboardAdapter:
    """把 MacKeyboardHook（CGEventTap）包装成 BlackboxEngine KeyboardHook 契约。

    对外接口与 src.collector.keyboard_hook.KeyboardHook 一致：
        __init__(on_event, capture_hotkeys)
        start() / stop()
    回调 on_event 收到的是 BlackboxEngine 的 KeyEvent（InputBuffer 兼容）。
    """

    def __init__(self, on_event, capture_hotkeys: bool = False):
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys
        self._hook = None

    def start(self):
        from personal_recorder.collectors.macos_collectors import MacKeyboardHook
        self._hook = MacKeyboardHook(
            on_event=self._convert,
            capture_hotkeys=self._capture_hotkeys,
        )
        self._hook.start()

    def stop(self):
        if self._hook is not None:
            self._hook.stop()
            self._hook = None

    def _convert(self, mac_ev):
        """MacKeyboardHook.KeyEvent → BlackboxEngine KeyEvent（InputBuffer 兼容）"""
        from pynput import keyboard
        from src.collector.keyboard_hook import KeyEvent, KeyEventType

        key = None
        if mac_ev.is_backspace:
            key = keyboard.Key.backspace
        elif mac_ev.is_enter:
            key = keyboard.Key.enter
        elif mac_ev.is_tab:
            key = keyboard.Key.tab
        char = mac_ev.char if mac_ev.is_printable_char else None
        # KeyEvent(event_type, key, char)：InputBuffer 仅处理 PRESS，
        # 并依据 key==Key.backspace / is_enter / is_tab / is_printable_char 分流
        self._on_event(KeyEvent(KeyEventType.PRESS, key, char=char))
