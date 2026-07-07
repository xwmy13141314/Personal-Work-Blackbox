"""输入活动监听器 — 直接使用 Windows API 的低级键盘钩子

在调用线程上安装 WH_KEYBOARD_LL 和 WH_GETMESSAGE 钩子，
由该线程的消息泵（如 pywebview 主循环）处理回调。

这解决了 pynput Listener 在 PyInstaller 打包 + pywebview 环境下
监听器线程消息泵不工作的问题。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from enum import Enum, auto
from typing import Callable

from pynput import keyboard  # 仅用于 Key 枚举比较，不使用 Listener

logger = logging.getLogger(__name__)

# ==================== Windows API 常量 ====================

WH_KEYBOARD_LL = 13
WH_GETMESSAGE = 3
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105

WM_IME_COMPOSITION = 0x010F
GCS_RESULTSTR = 0x0800
GCS_COMPSTR = 0x0008

LLKHF_INJECTED = 0x10

# Virtual key codes
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_DELETE = 0x2E
VK_HOME = 0x24
VK_END = 0x23
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5

# ==================== Windows API 绑定 ====================

try:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _imm32 = ctypes.windll.imm32

    _user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, ctypes.c_void_p, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD,
    ]
    _user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
    _user32.CallNextHookEx.restype = ctypes.c_long
    _user32.CallNextHookEx.argtypes = [
        ctypes.wintypes.HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    ]
    _kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
    _kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]
    _kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetLastError.restype = ctypes.wintypes.DWORD
    _kernel32.GetLastError.argtypes = []

    _user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    _user32.GetForegroundWindow.argtypes = []

    _user32.GetKeyboardState.restype = ctypes.wintypes.BOOL
    _user32.GetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_uint8 * 256)]

    _user32.ToUnicodeEx.restype = ctypes.c_int
    _user32.ToUnicodeEx.argtypes = [
        ctypes.wintypes.UINT, ctypes.wintypes.UINT,
        ctypes.POINTER(ctypes.c_uint8 * 256),
        ctypes.POINTER(ctypes.wintypes.WCHAR),
        ctypes.c_int, ctypes.wintypes.HKL,
    ]

    _user32.MapVirtualKeyW.restype = ctypes.wintypes.UINT
    _user32.MapVirtualKeyW.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.UINT]

    _user32.GetKeyboardLayout.restype = ctypes.wintypes.HKL
    _user32.GetKeyboardLayout.argtypes = [ctypes.wintypes.DWORD]

    # IMM API
    _imm32.ImmGetContext.restype = ctypes.c_void_p
    _imm32.ImmGetContext.argtypes = [ctypes.wintypes.HWND]
    _imm32.ImmReleaseContext.restype = ctypes.wintypes.BOOL
    _imm32.ImmReleaseContext.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p]
    _imm32.ImmGetCompositionStringW.restype = ctypes.wintypes.LONG
    _imm32.ImmGetCompositionStringW.argtypes = [
        ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ]

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    )

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.wintypes.HWND),
            ("message", ctypes.wintypes.UINT),
            ("wParam", ctypes.wintypes.WPARAM),
            ("lParam", ctypes.wintypes.LPARAM),
            ("time", ctypes.wintypes.DWORD),
            ("pt", ctypes.wintypes.POINT),
        ]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", ctypes.wintypes.DWORD),
            ("scanCode", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    _HAS_WIN_API = True
except Exception:
    _HAS_WIN_API = False
    logger.warning("Windows API 不可用，键盘监听功能将不可用")


# ==================== IME 辅助函数 ====================

def _get_ime_result_string(hwnd: int) -> str | None:
    """获取 IME 组合结果字符串"""
    if not _HAS_WIN_API:
        return None
    try:
        imc = _imm32.ImmGetContext(hwnd)
        if not imc:
            return None
        try:
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


# ==================== 虚拟键码映射 ====================

_VK_TO_KEY = {
    VK_RETURN: keyboard.Key.enter,
    VK_BACK: keyboard.Key.backspace,
    VK_TAB: keyboard.Key.tab,
    VK_ESCAPE: keyboard.Key.esc,
    VK_DELETE: keyboard.Key.delete,
    VK_SPACE: keyboard.Key.space,
    VK_LEFT: keyboard.Key.left,
    VK_UP: keyboard.Key.up,
    VK_RIGHT: keyboard.Key.right,
    VK_DOWN: keyboard.Key.down,
    VK_HOME: keyboard.Key.home,
    VK_END: keyboard.Key.end,
}

_CTRL_VKS = {VK_CONTROL, VK_LCONTROL, VK_RCONTROL}
_ALT_VKS = {VK_MENU, VK_LMENU, VK_RMENU}
_SHIFT_VKS = {VK_SHIFT, VK_LSHIFT, VK_RSHIFT}


def _vk_to_char(vk: int) -> str | None:
    """将虚拟键码转换为字符（使用 ToUnicodeEx）"""
    if not _HAS_WIN_API:
        return None
    try:
        kb_state = (ctypes.c_uint8 * 256)()
        _user32.GetKeyboardState(kb_state)

        thread_id = _kernel32.GetCurrentThreadId()
        hkl = _user32.GetKeyboardLayout(thread_id)

        scan_code = _user32.MapVirtualKeyW(vk, 0)  # MAPVK_VK_TO_VSC

        buf = (ctypes.wintypes.WCHAR * 16)()
        result = _user32.ToUnicodeEx(vk, scan_code, kb_state, buf, 16, 0, hkl)

        if result > 0:
            char = buf[0]
            if char and char.isprintable():
                return char
        return None
    except Exception:
        return None


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


# ==================== IME 消息钩子 ====================

class IMEMessageHook:
    """IME 消息钩子（WH_GETMESSAGE 拦截 WM_IME_COMPOSITION）

    在调用线程上安装钩子，由该线程的消息泵处理回调。
    必须在有消息泵的线程上调用 start()。
    """

    def __init__(self, on_ime_result: Callable[[str], None]):
        self._on_ime_result = on_ime_result
        self._hook = None
        self._hook_proc = None  # 保持引用防止 GC
        self._running = False

    def start(self):
        if self._hook:
            return
        if not _HAS_WIN_API:
            logger.error("Windows API 不可用，IME 钩子无法安装")
            return
        try:
            self._hook_proc = HOOKPROC(self._hook_callback)
            h_module = _kernel32.GetModuleHandleW(None)
            thread_id = _kernel32.GetCurrentThreadId()
            # WH_GETMESSAGE 传 thread_id=0（全局）需要 DLL 注入，
            # 传当前线程 ID 则只需模块句柄，避免 error 1428
            self._hook = _user32.SetWindowsHookExW(
                WH_GETMESSAGE, self._hook_proc, h_module, thread_id,
            )
            if self._hook:
                self._running = True
                logger.info("IME 消息钩子已安装 (WH_GETMESSAGE, thread_id=%d)", thread_id)
            else:
                err = _kernel32.GetLastError()
                logger.error("IME 消息钩子安装失败 (error=%d)", err)
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


# ==================== 键盘监听器 ====================

class KeyboardHook:
    """键盘监听器 — 直接使用 Windows API WH_KEYBOARD_LL

    在调用线程上安装钩子，由该线程的消息泵处理回调。
    必须在有消息泵的线程上调用 start()（如 pywebview 主线程）。

    不再使用 pynput.Listener，因为它在 PyInstaller 打包 + pywebview
    环境下创建的监听器线程消息泵不工作，导致回调永远不触发。
    """

    def __init__(
        self,
        on_event: Callable[[KeyEvent], None],
        capture_hotkeys: bool = True,
    ):
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys

        self._hook = None
        self._hook_proc = None  # 保持引用防止 GC
        self._ime_hook: IMEMessageHook | None = None
        if _HAS_WIN_API:
            self._ime_hook = IMEMessageHook(on_ime_result=self._on_ime_result_from_hook)

        self._ctrl_pressed = False
        self._alt_pressed = False
        self._shift_pressed = False

        self._last_ime_result = ""
        self._event_count = 0
        self._first_event_logged = False
        self._installed = False

    def start(self):
        """在调用线程上安装键盘钩子。

        重要：调用线程必须有 Windows 消息泵（如 pywebview 的主循环）。
        不要在没有消息泵的线程上调用此方法。
        """
        if self._installed:
            return

        if not _HAS_WIN_API:
            logger.error("Windows API 不可用，无法安装键盘钩子")
            return

        # 保持 HOOKPROC 引用，防止 ctypes 回调被 GC
        self._hook_proc = HOOKPROC(self._kbd_hook_callback)

        h_module = _kernel32.GetModuleHandleW(None)
        thread_id = _kernel32.GetCurrentThreadId()

        # 安装 WH_KEYBOARD_LL 钩子
        self._hook = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, h_module, 0,
        )
        if self._hook:
            logger.info("WH_KEYBOARD_LL 钩子已安装 (thread_id=%d)", thread_id)
        else:
            err = _kernel32.GetLastError()
            logger.error("WH_KEYBOARD_LL 钩子安装失败 (error=%d)", err)

        # 安装 IME 消息钩子（WH_GETMESSAGE）
        if self._ime_hook:
            self._ime_hook.start()

        self._installed = True

    def stop(self):
        """卸载键盘钩子"""
        if self._ime_hook:
            self._ime_hook.stop()

        if self._hook:
            try:
                _user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                logger.exception("WH_KEYBOARD_LL 卸载异常")
            self._hook = None

        self._installed = False
        logger.info("KeyboardHook 已停止 (events=%d)", self._event_count)

    def _kbd_hook_callback(self, nCode, wParam, lParam):
        """WH_KEYBOARD_LL 回调"""
        if nCode == HC_ACTION:
            try:
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = KBDLLHOOKSTRUCT.from_address(lParam)
                    vk = kb.vkCode

                    # 忽略注入事件（SendInput 等）
                    if kb.flags & LLKHF_INJECTED:
                        return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

                    self._event_count += 1
                    if not self._first_event_logged:
                        self._first_event_logged = True
                        logger.info("首次按键事件已收到: vk=0x%02X", vk)

                    self._process_keydown(vk)

                elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                    kb = KBDLLHOOKSTRUCT.from_address(lParam)
                    vk = kb.vkCode
                    self._process_keyup(vk)

            except Exception:
                logger.exception("键盘钩子回调异常")

        return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _process_keydown(self, vk: int):
        """处理按键按下"""
        # 更新修饰键状态
        if vk in _CTRL_VKS:
            self._ctrl_pressed = True
            return
        if vk in _ALT_VKS:
            self._alt_pressed = True
            return
        if vk in _SHIFT_VKS:
            self._shift_pressed = True
            return

        # 检查 IME 结果（Enter/Space/Tab/Backspace 可能确认 IME 候选词）
        if vk in (VK_RETURN, VK_SPACE, VK_TAB, VK_BACK, VK_DELETE):
            self._check_and_emit_ime_result()

        # 特殊键映射
        if vk in _VK_TO_KEY:
            key = _VK_TO_KEY[vk]
            # Enter/Backspace/Delete/Tab/Space 始终传递
            if vk in (VK_RETURN, VK_BACK, VK_DELETE, VK_TAB, VK_SPACE):
                event = KeyEvent(
                    KeyEventType.PRESS, key, ctrl_pressed=self._ctrl_pressed,
                )
                self._on_event(event)
            elif self._capture_hotkeys:
                event = KeyEvent(
                    KeyEventType.PRESS, key, ctrl_pressed=self._ctrl_pressed,
                )
                self._on_event(event)
            return

        # 普通字符键 — 转换为字符
        char = _vk_to_char(vk)
        if char:
            key = keyboard.KeyCode(char=char)
            event = KeyEvent(
                KeyEventType.PRESS, key, char=char,
                ctrl_pressed=self._ctrl_pressed,
            )
            self._on_event(event)

    def _process_keyup(self, vk: int):
        """处理按键释放"""
        if vk in _CTRL_VKS:
            self._ctrl_pressed = False
        elif vk in _ALT_VKS:
            self._alt_pressed = False
        elif vk in _SHIFT_VKS:
            self._shift_pressed = False

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

    @property
    def is_alive(self) -> bool:
        """钩子是否已安装"""
        return self._installed
