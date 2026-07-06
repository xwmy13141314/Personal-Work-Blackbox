"""输入活动监听器 — 基于 pynput 的低级键盘钩子

支持通过 Windows IMM API 捕获 IME（中文输入法）组合完成后的最终文本，
避免仅记录到逐个拼音字母的问题。
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)

# ==================== Windows IMM API 绑定 ====================
# 通过 ctypes 调用 IMM (Input Method Manager) API，
# 在 Windows 上捕获中文输入法组合完成后的最终文本。

# IMM API 常量
GCS_RESULTSTR = 0x0800  # 获取已完成的组合结果字符串
GCS_COMPSTR = 0x0008   # 获取正在组合中的字符串
WM_IME_COMPOSITION = 0x010F

# 加载 IMM 库（仅 Windows 可用）
try:
    import ctypes
    import ctypes.wintypes

    _imm32 = ctypes.windll.imm32
    _user32 = ctypes.windll.user32

    # 设置函数签名（确保 64 位系统上指针类型正确传递）
    _imm32.ImmGetContext.restype = ctypes.c_void_p
    _imm32.ImmGetContext.argtypes = [ctypes.wintypes.HWND]

    _imm32.ImmReleaseContext.restype = ctypes.wintypes.BOOL
    _imm32.ImmReleaseContext.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p]

    _imm32.ImmGetOpenStatus.restype = ctypes.wintypes.BOOL
    _imm32.ImmGetOpenStatus.argtypes = [ctypes.c_void_p]

    _imm32.ImmGetCompositionStringW.restype = ctypes.wintypes.LONG
    _imm32.ImmGetCompositionStringW.argtypes = [
        ctypes.c_void_p,        # HIMC
        ctypes.wintypes.DWORD,  # DWORD (GCS_*)
        ctypes.c_void_p,        # LPVOID (输出缓冲区)
        ctypes.wintypes.DWORD,  # DWORD (缓冲区大小)
    ]

    _user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    _user32.GetForegroundWindow.argtypes = []

    _HAS_IMM = True
except Exception:
    _HAS_IMM = False
    logger.warning("IMM API 不可用，IME 组合文本捕获功能将不可用")


def _get_ime_result_string(hwnd: int) -> str | None:
    """获取 IME 组合结果字符串（已完成的文本）

    通过 IMM API 检查前台窗口的 IME 状态，如果存在已完成的组合文本则返回。

    Args:
        hwnd: 前台窗口句柄

    Returns:
        已完成的组合文本，如 "继续"；无结果时返回 None
    """
    if not _HAS_IMM:
        return None

    try:
        # 获取 IME 上下文
        imc = _imm32.ImmGetContext(hwnd)
        if not imc:
            return None

        try:
            # 检查 IME 是否开启
            if not _imm32.ImmGetOpenStatus(imc):
                return None

            # 获取结果字符串长度（字节数，WideChar 每字符 2 字节）
            result_len = _imm32.ImmGetCompositionStringW(imc, GCS_RESULTSTR, None, 0)
            if result_len <= 0:
                return None

            # 读取结果字符串
            buf = ctypes.create_string_buffer(result_len)
            _imm32.ImmGetCompositionStringW(imc, GCS_RESULTSTR, buf, result_len)

            # 转换为 Python 字符串（WideChar → Unicode）
            result = buf.raw[:result_len].decode("utf-16-le", errors="ignore")
            return result if result else None
        finally:
            _imm32.ImmReleaseContext(hwnd, imc)
    except Exception:
        logger.debug("获取 IME 结果字符串异常", exc_info=True)
        return None


def _is_ime_active(hwnd: int) -> bool:
    """检查前台窗口的 IME 是否处于活动状态（已开启）

    Args:
        hwnd: 前台窗口句柄

    Returns:
        IME 已开启返回 True，否则 False
    """
    if not _HAS_IMM:
        return False
    try:
        imc = _imm32.ImmGetContext(hwnd)
        if not imc:
            return False
        try:
            return bool(_imm32.ImmGetOpenStatus(imc))
        finally:
            _imm32.ImmReleaseContext(hwnd, imc)
    except Exception:
        return False


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
        self.is_ime_composition = is_ime_composition  # 是否为 IME 组合文本

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
    def is_ctrl_a(self) -> bool:
        """检测 Ctrl+A 全选组合键"""
        if not self.ctrl_pressed:
            return False
        # Ctrl+A 时 pynput 给出 char='\x01'（控制字符）
        if self.char == '\x01':
            return True
        # 或 key 为 KeyCode 且 char 为 'a'（部分环境不转控制字符）
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
        """是否为 IME 组合完成的文本"""
        return self.is_ime_composition

    def __repr__(self):
        char_info = f", char={self.char!r}" if self.char else ""
        ime_info = ", ime=True" if self.is_ime_composition else ""
        return f"KeyEvent({self.event_type.name}, key={self.key}{char_info}{ime_info})"


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

        # IME 状态追踪
        self._ime_active = False
        self._last_ime_result = ""  # 上次获取到的 IME 结果，用于去重

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
            # 停止前检查最后的 IME 组合结果
            self._check_and_emit_ime_result()
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

                # Enter/Backspace/Delete/Tab 始终传递
                if key in (keyboard.Key.enter, keyboard.Key.backspace, keyboard.Key.delete, keyboard.Key.tab):
                    # 在发送特殊键之前，先检查 IME 组合结果
                    self._check_and_emit_ime_result()
                    self._on_event(event)
                # 方向键和 Escape 仅在 capture_hotkeys 时传递
                elif self._capture_hotkeys:
                    self._on_event(event)
            else:
                # 普通字符键
                raw_char = getattr(key, 'char', None)
                if raw_char is not None:
                    char = raw_char
                else:
                    char = str(key)

                # 检查 IME 状态 — IME 活动时不发送单个拼音字母
                if _HAS_IMM:
                    hwnd = _user32.GetForegroundWindow()
                    if hwnd and _is_ime_active(hwnd):
                        # IME 活动中 — 检查组合结果而非发送单个字符
                        self._ime_active = True
                        self._check_and_emit_ime_result()
                        return  # 不发送单个拼音字母

                self._ime_active = False
                event = KeyEvent(
                    KeyEventType.PRESS, key, char=char,
                    ctrl_pressed=self._ctrl_pressed,
                )
                self._on_event(event)
        except Exception:
            logger.exception("键盘事件处理异常")

    def _check_and_emit_ime_result(self):
        """检查并发射 IME 组合结果文本

        通过 IMM API 获取前台窗口的 IME 组合结果字符串，
        若与上次结果不同则生成一个 is_ime_composition=True 的 KeyEvent。
        """
        if not _HAS_IMM:
            return

        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return

            result = _get_ime_result_string(hwnd)
            if result and result != self._last_ime_result:
                # 发射 IME 组合文本事件
                event = KeyEvent(
                    KeyEventType.PRESS,
                    key=None,  # IME 组合文本没有对应的单个键
                    char=result,
                    is_ime_composition=True,
                )
                self._on_event(event)
                self._last_ime_result = result
            elif not result:
                # 无组合结果时重置去重缓存
                self._last_ime_result = ""
        except Exception:
            logger.debug("IME 结果检查异常", exc_info=True)

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
