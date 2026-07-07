"""输入活动监听器 — 基于 pynput 的低级键盘钩子

支持通过 Windows IMM API 捕获 IME（中文输入法）组合完成后的最终文本，
避免仅记录到逐个拼音字母的问题。
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)

# ==================== Windows IMM API 绑定 ====================

GCS_RESULTSTR = 0x0800
GCS_COMPSTR = 0x0008
WM_IME_COMPOSITION = 0x010F
WH_GETMESSAGE = 3
HC_ACTION = 0

try:
    import ctypes
    import ctypes.wintypes

    _imm32 = ctypes.windll.imm32
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _imm32.ImmGetContext.restype = ctypes.c_void_p
    _imm32.ImmGetContext.argtypes = [ctypes.wintypes.HWND]

    _imm32.ImmReleaseContext.restype = ctypes.wintypes.BOOL
    _imm32.ImmReleaseContext.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p]

    _imm32.ImmGetOpenStatus.restype = ctypes.wintypes.BOOL
    _imm32.ImmGetOpenStatus.argtypes = [ctypes.c_void_p]

    _imm32.ImmGetCompositionStringW.restype = ctypes.wintypes.LONG
    _imm32.ImmGetCompositionStringW.argtypes = [
        ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ]

    _user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    _user32.GetForegroundWindow.argtypes = []

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.wintypes.HWND),
            ("message", ctypes.wintypes.UINT),
            ("wParam", ctypes.wintypes.WPARAM),
            ("lParam", ctypes.wintypes.LPARAM),
            ("time", ctypes.wintypes.DWORD),
            ("pt", ctypes.wintypes.POINT),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    )

    _user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, HOOKPROC, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD,
    ]
    _user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
    _user32.CallNextHookEx.restype = ctypes.c_long
    _user32.CallNextHookEx.argtypes = [
        ctypes.wintypes.HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    ]
    _kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
    _kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]

    _HAS_IMM = True
except Exception:
    _HAS_IMM = False
    logger.warning("IMM API 不可用，IME 组合文本捕获功能将不可用")


def _get_ime_result_string(hwnd: int) -> str | None:
    """获取 IME 组合结果字符串"""
    if not _HAS_IMM:
        return None
    try:
        imc = _imm32.ImmGetContext(hwnd)
        if not imc:
            return None
        try:
            if not _imm32.ImmGetOpenStatus(imc):
                return None
            result_len = _imm32.ImmGetCompositionStringW(imc, GCS_RESULTSTR, None, 0)
            if result_len <= 0:
                return None
            buf = ctypes.create_string_buffer(result_len)
            _imm32.ImmGetCompositionStringW(imc, GCS_RESULTSTR, buf, result_len)
            result = buf.raw[:result_len].decode("utf-16-le", errors="ignore")
            return result if result else None
        finally:
            _imm32.ImmReleaseContext(hwnd, imc)
    except Exception:
        return None


# ==================== IME 消息钩子 ====================

class IMEMessageHook:
    """IME 消息钩子（WH_GETMESSAGE 拦截 WM_IME_COMPOSITION）"""

    def __init__(self, on_ime_result: Callable[[str], None]):
        self._on_ime_result = on_ime_result
        self._hook = None
        self._hook_proc = HOOKPROC(self._hook_callback)
        self._running = False

    def start(self):
        if self._hook:
            return
        try:
            h_module = _kernel32.GetModuleHandleW(None)
            self._hook = _user32.SetWindowsHookExW(WH_GETMESSAGE, self._hook_proc, h_module, 0)
            if self._hook:
                self._running = True
                logger.info("IME 消息钩子已安装 (WH_GETMESSAGE)")
            else:
                logger.error("IME 消息钩子安装失败")
        except Exception:
            logger.exception("IME 消息钩子启动异常")

    def stop(self):
        if self._hook:
            try:
                _user32.UnhookWindowsHookEx(self._hook)
                logger.info("IME 消息钩子已卸载")
            except Exception:
                logger.exception("IME 消息钩子卸载异常")
            self._hook = None
            self._running = False

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode == HC_ACTION and lParam:
            try:
                msg = MSG.from_address(lParam)
                if msg.message == WM_IME_COMPOSITION:
                    if msg.lParam & GCS_RESULTSTR:
                        result = _get_ime_result_string(msg.hwnd)
                        if result:
                            self._on_ime_result(result)
            except Exception:
                logger.debug("IME 消息钩子回调异常", exc_info=True)
        return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    @property
    def is_running(self) -> bool:
        return self._running


# ==================== 事件类型 ====================

class KeyEventType(Enum):
    PRESS = auto()
    RELEASE = auto()


class KeyEvent:
    """键盘事件"""

    def __init__(
        self,
        event_type: KeyEventType,
        key,
        char: str | None = None,
        ctrl_pressed: bool = False,
        is_ime_composition: bool = False,
    ):
        self.event_type = event_type
        self.key = key
        self.char = char
        self.timestamp = time.time()
        self.ctrl_pressed = ctrl_pressed
        self.is_ime_composition = is_ime_composition

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
        return self.key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    @property
    def is_alt(self) -> bool:
        return self.key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r)

    @property
    def is_ctrl_a(self) -> bool:
        if not self.ctrl_pressed:
            return False
        if self.char == '\x01':
            return True
        if hasattr(self.key, 'char') and self.key.char and self.key.char.lower() == 'a':
            return True
        return False

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

    @property
    def is_ime_text(self) -> bool:
        return self.is_ime_composition

    def __repr__(self):
        char_info = f", char={self.char!r}" if self.char else ""
        ime_info = ", ime=True" if self.is_ime_composition else ""
        return f"KeyEvent({self.event_type.name}, key={self.key}{char_info}{ime_info})"


# ==================== 键盘监听器 ====================

class KeyboardHook:
    """键盘监听器 — 基于 pynput 的 Listener

    通过 pynput 的 Listener 捕获键盘事件，转换为 KeyEvent 对象后
    传递给处理回调。

    注意：不再使用 ImmGetOpenStatus 检查 IME 状态。
    原因：Windows 上 ImmGetOpenStatus 在英文模式下也返回 True，
    导致所有按键被丢弃。现在所有按键正常传递，IME 消息钩子负责
    捕获中文组合结果，InputBuffer 在收到组合结果时自动移除拼音字母。
    """

    def __init__(
        self,
        on_event: Callable[[KeyEvent], None],
        capture_hotkeys: bool = True,
    ):
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys
        self._listener: keyboard.Listener | None = None

        self._ctrl_pressed = False
        self._alt_pressed = False
        self._shift_pressed = False

        self._last_ime_result = ""
        self._ime_hook: IMEMessageHook | None = None
        if _HAS_IMM:
            self._ime_hook = IMEMessageHook(on_ime_result=self._on_ime_result_from_hook)

        self._first_event_logged = False
        self._event_count = 0
        self._heartbeat_thread = None

    def start(self):
        """启动键盘监听"""
        if self._listener:
            return

        if self._ime_hook:
            self._ime_hook.start()

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

        backend = type(self._listener).__module__
        logger.info("KeyboardHook 已启动 (backend=%s, alive=%s)",
                     backend, self._listener.is_alive())
        if '_dummy' in backend:
            logger.error("pynput 后端为 _dummy！键盘事件将无法捕获")

        # 心跳线程：每 30 秒输出事件计数和监听器状态
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat, daemon=True, name="KbHeartbeat",
        )
        self._heartbeat_thread.start()

    def _heartbeat(self):
        """周期性输出键盘监听状态（诊断用）"""
        while self._listener and self._listener.is_alive():
            time.sleep(30)
            try:
                alive = self._listener.is_alive() if self._listener else False
                logger.info("键盘心跳: events=%d, listener_alive=%s",
                            self._event_count, alive)
            except Exception:
                break

    def stop(self):
        """停止键盘监听"""
        if self._ime_hook:
            self._ime_hook.stop()

        if self._listener:
            self._check_and_emit_ime_result()
            self._listener.stop()
            self._listener = None
        logger.info("KeyboardHook 已停止")

    def _on_press(self, key):
        """按键按下回调"""
        try:
            self._event_count += 1

            # 首次按键日志（诊断用）
            if not self._first_event_logged:
                self._first_event_logged = True
                logger.info("首次按键事件已收到: key=%s", key)

            # 更新修饰键状态
            if isinstance(key, keyboard.Key):
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._ctrl_pressed = True
                elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._alt_pressed = True
                elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self._shift_pressed = True

                # Enter/Backspace/Delete/Tab/Space 始终传递
                # Space 也触发 IME 结果检查（中文输入法用空格确认候选词）
                if key in (keyboard.Key.enter, keyboard.Key.backspace,
                           keyboard.Key.delete, keyboard.Key.tab, keyboard.Key.space):
                    self._check_and_emit_ime_result()
                    event = KeyEvent(
                        KeyEventType.PRESS, key, ctrl_pressed=self._ctrl_pressed,
                    )
                    self._on_event(event)
                # 方向键和 Escape 仅在 capture_hotkeys 时传递
                elif self._capture_hotkeys:
                    event = KeyEvent(
                        KeyEventType.PRESS, key, ctrl_pressed=self._ctrl_pressed,
                    )
                    self._on_event(event)
            else:
                # 普通字符键 — 始终传递到缓冲区
                # 不再检查 ImmGetOpenStatus（会导致所有按键被丢弃）
                raw_char = getattr(key, 'char', None)
                if raw_char is not None:
                    char = raw_char
                else:
                    char = str(key)

                event = KeyEvent(
                    KeyEventType.PRESS, key, char=char,
                    ctrl_pressed=self._ctrl_pressed,
                )
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
            pass

    def _on_ime_result_from_hook(self, result: str):
        """IME 消息钩子回调"""
        if result and result != self._last_ime_result:
            event = KeyEvent(
                KeyEventType.PRESS, key=None, char=result,
                is_ime_composition=True,
            )
            self._on_event(event)
            self._last_ime_result = result

    def _check_and_emit_ime_result(self):
        """兜底：检查 IME 组合结果"""
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return
            result = _get_ime_result_string(hwnd)
            if result and result != self._last_ime_result:
                event = KeyEvent(
                    KeyEventType.PRESS, key=None, char=result,
                    is_ime_composition=True,
                )
                self._on_event(event)
                self._last_ime_result = result
            elif not result:
                self._last_ime_result = ""
        except Exception:
            pass

    @property
    def is_ctrl_held(self) -> bool:
        return self._ctrl_pressed

    @property
    def is_alt_held(self) -> bool:
        return self._alt_pressed

    @property
    def is_shift_held(self) -> bool:
        return self._shift_pressed
