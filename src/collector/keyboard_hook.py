"""输入活动监听器 — 直接使用 Windows API 的低级键盘钩子

使用专用线程 + 独立消息泵（GetMessageW 循环）安装 WH_KEYBOARD_LL，
不依赖 pywebview 的主线程消息循环。

WH_KEYBOARD_LL 要求安装线程必须有标准 Win32 消息泵（GetMessageW/
DispatchMessageW），但 pywebview 主线程使用自己的事件循环，
不处理钩子回调。因此必须在专用线程中安装钩子并运行消息泵。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from enum import Enum, auto
from typing import Callable

from pynput import keyboard  # 仅用于 Key 枚举比较

logger = logging.getLogger(__name__)

# ==================== 64 位正确的 Windows 类型 ====================
# ctypes.wintypes 把 WPARAM/LPARAM 定义为 32 位，但在 64 位 Windows 上
# 它们是指针大小（64 位）。使用 c_ssize_t/c_size_t 确保正确。

_LRESULT = ctypes.c_ssize_t   # LONG_PTR
_WPARAM = ctypes.c_size_t     # UINT_PTR
_LPARAM = ctypes.c_ssize_t    # LONG_PTR

# ==================== Windows API 常量 ====================

WH_KEYBOARD_LL = 13
WH_GETMESSAGE = 3
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

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

    # SetWindowsHookExW
    _user32.SetWindowsHookExW.restype = ctypes.wintypes.HHOOK
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, ctypes.c_void_p, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD,
    ]
    # UnhookWindowsHookEx
    _user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HHOOK]
    # CallNextHookEx — 返回值 LRESULT 是 64 位
    _user32.CallNextHookEx.restype = _LRESULT
    _user32.CallNextHookEx.argtypes = [
        ctypes.wintypes.HHOOK, ctypes.c_int, _WPARAM, _LPARAM,
    ]
    # GetMessageW — 消息泵核心
    _user32.GetMessageW.restype = ctypes.wintypes.BOOL
    _user32.GetMessageW.argtypes = [
        ctypes.POINTER(ctypes.wintypes.MSG), ctypes.wintypes.HWND,
        ctypes.wintypes.UINT, ctypes.wintypes.UINT,
    ]
    # PeekMessageW
    _user32.PeekMessageW.restype = ctypes.wintypes.BOOL
    _user32.PeekMessageW.argtypes = [
        ctypes.POINTER(ctypes.wintypes.MSG), ctypes.wintypes.HWND,
        ctypes.wintypes.UINT, ctypes.wintypes.UINT, ctypes.wintypes.UINT,
    ]
    # DispatchMessageW
    _user32.DispatchMessageW.restype = ctypes.c_long  # LRESULT 但标准调用
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
    # PostThreadMessageW — 向指定线程发消息（用于停止消息泵）
    _user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
    _user32.PostThreadMessageW.argtypes = [
        ctypes.wintypes.DWORD, ctypes.wintypes.UINT, _WPARAM, _LPARAM,
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

    # HOOKPROC — 返回值 LRESULT 是 64 位
    HOOKPROC = ctypes.WINFUNCTYPE(
        _LRESULT, ctypes.c_int, _WPARAM, _LPARAM,
    )

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


def _vk_to_char(vk: int, shift_pressed: bool = False) -> str | None:
    """将虚拟键码转换为字符

    不依赖 GetKeyboardState（钩子线程的键盘状态全为零，不可用）。
    改用硬编码映射 + MapVirtualKeyW，shift 状态由调用方传入。
    """
    if not _HAS_WIN_API:
        return None

    # 字母键 A-Z (vk 0x41-0x5A)
    if 0x41 <= vk <= 0x5A:
        if shift_pressed:
            return chr(vk)  # 大写 A-Z
        return chr(vk + 32)  # 小写 a-z

    # 数字键 0-9 (vk 0x30-0x39)
    if 0x30 <= vk <= 0x39:
        if shift_pressed:
            shift_digits = ")!@#$%^&*("
            return shift_digits[vk - 0x30]
        return chr(vk)

    # 空格
    if vk == VK_SPACE:
        return " "

    # OEM 键 — 使用 MapVirtualKeyW(MAPVK_VK_TO_CHAR)
    # MapVirtualKeyW 返回的是不按 shift 时的字符（小写形式）
    char_code = _user32.MapVirtualKeyW(vk, 2)  # MAPVK_VK_TO_CHAR
    if char_code and char_code < 0x10000:
        char = chr(char_code)
        if char and char.isprintable():
            # 如果按了 shift 且字符是小写字母，转大写
            if shift_pressed and char.isalpha():
                return char.upper()
            return char
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


# ==================== 键盘监听器（专用线程 + 独立消息泵）====================

class KeyboardHook:
    """键盘监听器 — 专用线程 + 独立消息泵

    创建一个专用线程，在该线程上安装 WH_KEYBOARD_LL 钩子并运行
    GetMessageW 消息泵。这样钩子回调由专用线程的消息泵处理，
    不依赖 pywebview 主线程的消息循环。

    stop() 通过 PostThreadMessageW 发送 WM_QUIT 来停止消息泵。
    """

    # 类级别保持 HOOKPROC 引用，防止 ctypes 回调被 GC
    _hook_proc_ref = None
    _ime_hook_proc_ref = None

    def __init__(
        self,
        on_event: Callable[[KeyEvent], None],
        capture_hotkeys: bool = True,
    ):
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys

        self._kb_hook = None
        self._ime_hook = None
        self._hook_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._thread_id: int | None = None

        self._ctrl_pressed = False
        self._alt_pressed = False
        self._shift_pressed = False

        self._last_ime_result = ""
        self._event_count = 0
        self._first_event_logged = False
        self._installed = False
        self._stop_flag = False

    def start(self):
        """启动键盘监听（创建专用线程）"""
        if self._installed:
            return

        if not _HAS_WIN_API:
            logger.error("Windows API 不可用，无法安装键盘钩子")
            return

        # 保持 HOOKPROC 引用在类级别，防止 GC 导致崩溃
        KeyboardHook._hook_proc_ref = HOOKPROC(self._kbd_hook_callback)
        KeyboardHook._ime_hook_proc_ref = HOOKPROC(self._ime_getmsg_callback)

        self._stop_flag = False
        self._hook_thread = threading.Thread(
            target=self._hook_thread_main, daemon=True, name="KbHookThread",
        )
        self._hook_thread.start()

        # 启动看门狗：钩子线程崩溃后自动重启（防静默停采）
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="KbHookWatchdog",
        )
        self._watchdog_thread.start()

        # 等待线程安装完成（最多2秒）
        for _ in range(20):
            if self._installed:
                break
            time.sleep(0.1)

        if self._installed:
            logger.info("键盘钩子线程已启动 (thread_id=%s)", self._thread_id)
        else:
            logger.error("键盘钩子线程启动超时")

    def _hook_thread_main(self):
        """专用线程主函数：安装钩子 + 运行消息泵（含崩溃保护，由看门狗自恢复）"""
        try:
            thread_id = _kernel32.GetCurrentThreadId()
            self._thread_id = thread_id

            h_module = _kernel32.GetModuleHandleW(None)

            # 1. 安装 WH_KEYBOARD_LL
            self._kb_hook = _user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, KeyboardHook._hook_proc_ref, h_module, 0,
            )
            if self._kb_hook:
                logger.info("WH_KEYBOARD_LL 钩子已安装 (thread_id=%d)", thread_id)
            else:
                err = _kernel32.GetLastError()
                logger.error("WH_KEYBOARD_LL 钩子安装失败 (error=%d)", err)
                return

            # 2. 安装 WH_GETMESSAGE（IME 消息钩子，同线程）
            self._ime_hook = _user32.SetWindowsHookExW(
                WH_GETMESSAGE, KeyboardHook._ime_hook_proc_ref, h_module, thread_id,
            )
            if self._ime_hook:
                logger.info("IME 消息钩子已安装 (WH_GETMESSAGE, thread_id=%d)", thread_id)
            else:
                err = _kernel32.GetLastError()
                logger.warning("IME 消息钩子安装失败 (error=%d)", err)

            self._installed = True

            # 3. 消息泵：GetMessageW 循环
            logger.info("消息泵已启动，等待键盘事件...")
            msg = ctypes.wintypes.MSG()
            while not self._stop_flag:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:  # WM_QUIT 或错误
                    break
                _user32.DispatchMessageW(ctypes.byref(msg))

            logger.info("消息泵已停止 (events=%d)", self._event_count)
        except Exception:
            logger.exception("键盘钩子线程异常崩溃")
        finally:
            # 4. 确保钩子卸载 + 状态重置（崩溃或正常退出都执行）
            if self._kb_hook:
                try:
                    _user32.UnhookWindowsHookEx(self._kb_hook)
                except Exception:
                    pass
                self._kb_hook = None
            if self._ime_hook:
                try:
                    _user32.UnhookWindowsHookEx(self._ime_hook)
                except Exception:
                    pass
                self._ime_hook = None
            self._installed = False
            self._thread_id = None

    def _watchdog_loop(self):
        """看门狗：钩子线程意外退出后自动重启（防静默停采），最多重试 5 次防崩溃循环"""
        restarts = 0
        while not self._stop_flag:
            time.sleep(5)
            if self._stop_flag:
                break
            t = self._hook_thread
            if t is not None and not t.is_alive():
                if restarts >= 5:
                    logger.error("键盘钩子连续崩溃 %d 次，已放弃自恢复", restarts)
                    break
                restarts += 1
                logger.warning("键盘钩子线程异常退出，第 %d 次尝试重启...", restarts)
                self._installed = False
                self._thread_id = None
                try:
                    self._hook_thread = threading.Thread(
                        target=self._hook_thread_main, daemon=True, name="KbHookThread",
                    )
                    self._hook_thread.start()
                    for _ in range(20):
                        if self._installed:
                            break
                        time.sleep(0.1)
                    if self._installed:
                        logger.info("键盘钩子已自恢复 (thread_id=%s)", self._thread_id)
                    else:
                        logger.error("键盘钩子重启后安装超时")
                except Exception:
                    logger.exception("键盘钩子重启异常")

    def stop(self):
        """停止键盘监听（发送 WM_QUIT 到钩子线程）"""
        self._stop_flag = True

        if self._thread_id:
            # 向钩子线程发送 WM_QUIT，使其 GetMessageW 返回
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

        if self._hook_thread:
            self._hook_thread.join(timeout=2)

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
                        return _user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)

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

        return _user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)

    def _ime_getmsg_callback(self, nCode, wParam, lParam):
        """WH_GETMESSAGE 回调（IME 组合结果）"""
        if nCode == HC_ACTION and lParam:
            try:
                msg = ctypes.wintypes.MSG.from_address(lParam)
                if msg.message == WM_IME_COMPOSITION:
                    if msg.lParam & GCS_RESULTSTR:
                        result = _get_ime_result_string(msg.hwnd)
                        if result and result != self._last_ime_result:
                            self._last_ime_result = result
                            event = KeyEvent(
                                KeyEventType.PRESS, key=None, char=result,
                                is_ime_composition=True,
                            )
                            self._on_event(event)
            except Exception:
                logger.debug("IME 消息钩子回调异常", exc_info=True)
        return _user32.CallNextHookEx(self._ime_hook, nCode, wParam, lParam)

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

        # IME 确认键：Enter/Space/Tab/Backspace 可能确认了 IME 候选词
        # 直接从前台窗口的 IME 上下文获取组合结果
        # （WH_GETMESSAGE 钩子无法收到其他线程的 IME 消息，只能主动轮询）
        if vk in (VK_RETURN, VK_SPACE, VK_TAB, VK_BACK, VK_DELETE):
            self._check_and_emit_ime_result()

        # 特殊键映射
        if vk in _VK_TO_KEY:
            key = _VK_TO_KEY[vk]
            if vk in (VK_RETURN, VK_BACK, VK_DELETE, VK_TAB, VK_SPACE) or self._capture_hotkeys:
                event = KeyEvent(
                    KeyEventType.PRESS, key, ctrl_pressed=self._ctrl_pressed,
                )
                self._on_event(event)
            return

        # 普通字符键 — 转换为字符
        char = _vk_to_char(vk, shift_pressed=self._shift_pressed)
        if char:
            key = keyboard.KeyCode(char=char)
            event = KeyEvent(
                KeyEventType.PRESS, key, char=char,
                ctrl_pressed=self._ctrl_pressed,
            )
            self._on_event(event)
            # 诊断：前10个字符转换日志
            if self._event_count <= 10:
                logger.info("按键转换: vk=0x%02X → char=%r (shift=%s)",
                            vk, char, self._shift_pressed)
        else:
            # 诊断：前10个无法转换的按键
            if self._event_count <= 10:
                logger.info("按键无法转换: vk=0x%02X (shift=%s)",
                            vk, self._shift_pressed)

    def _process_keyup(self, vk: int):
        """处理按键释放"""
        if vk in _CTRL_VKS:
            self._ctrl_pressed = False
        elif vk in _ALT_VKS:
            self._alt_pressed = False
        elif vk in _SHIFT_VKS:
            self._shift_pressed = False

    def _check_and_emit_ime_result(self):
        """兜底：检查 IME 组合结果"""
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return
            result = _get_ime_result_string(hwnd)
            if result:
                logger.info("IME 结果检测到: %r", result[:30])
            self._on_ime_result_from_hook(result)
        except Exception:
            pass

    def _on_ime_result_from_hook(self, result: str | None):
        """处理 IME 结果（去重后发射事件）"""
        if not result:
            return
        if result != self._last_ime_result:
            self._last_ime_result = result
            logger.info("IME 文本已发射: %r", result[:30])
            event = KeyEvent(
                KeyEventType.PRESS, key=None, char=result,
                is_ime_composition=True,
            )
            self._on_event(event)

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
        """钩子线程是否存活"""
        return self._installed and self._hook_thread is not None and self._hook_thread.is_alive()
