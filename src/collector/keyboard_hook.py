"""输入活动监听器 — macOS 原生实现（Quartz CGEventTap）

使用专用线程 + 该线程的 CFRunLoop 安装 CGEventTap，监听全局键盘事件。
不依赖 pywebview 主线程的运行循环。

权限要求：需在「系统设置 > 隐私与安全性 > 辅助功能」中授权运行本程序的
终端/Python/.app，否则 CGEventTapCreate 返回 None，监听无法启动。

中文输入法（IME）说明：
  首版仅捕获按键流（英文/数字/符号/功能键直接转字符）。
  中文输入时，用户敲击的拼音字母会被记录；IME 确认后的最终汉字文本
  将在后续 P5 阶段通过 AXUIElement 监听补充（is_ime_composition 通道已预留）。
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from typing import Callable

from src.collector.key_types import Key, KeyCode

logger = logging.getLogger(__name__)

# ==================== macOS Quartz 绑定 ====================
try:
    import Quartz
    # CFRunLoop 函数：优先从 CoreFoundation 导入（需 pyobjc-framework-CoreFoundation），
    # 失败则从 Quartz 取（Quartz 链接 CoreFoundation，通常重新导出 CF 函数）
    try:
        from CoreFoundation import CFRunLoopGetCurrent, CFRunLoopRun, CFRunLoopStop, \
            CFMachPortCreateRunLoopSource, CFRunLoopAddSource, kCFRunLoopDefaultMode
    except ImportError:
        CFRunLoopGetCurrent = Quartz.CFRunLoopGetCurrent
        CFRunLoopRun = Quartz.CFRunLoopRun
        CFRunLoopStop = Quartz.CFRunLoopStop
        CFMachPortCreateRunLoopSource = Quartz.CFMachPortCreateRunLoopSource
        CFRunLoopAddSource = Quartz.CFRunLoopAddSource
        kCFRunLoopDefaultMode = Quartz.kCFRunLoopDefaultMode

    _HAS_MAC_API = True
except Exception:
    _HAS_MAC_API = False
    logger.warning("macOS Quartz API 不可用，键盘监听功能将不可用（需 pyobjc-framework-Quartz）")

# ==================== CGEvent 常量 ====================
if _HAS_MAC_API:
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11
    kCGEventFlagsChanged = 12

    # 修饰键 flag mask
    kCGEventFlagMaskShift = 0x020000
    kCGEventFlagMaskControl = 0x040000      # Mac Control 键（对应 Windows Ctrl）
    kCGEventFlagMaskAlternate = 0x080000    # Mac Option/Alt 键
    kCGEventFlagMaskCommand = 0x100000      # Mac Command 键

    # CGEventField
    kCGKeyboardEventKeycode = 9

# ==================== Mac 虚拟键码 → 应用内部 Key 映射 ====================
# 参考 macOS HID Usage Tables (HUT) + IOKit/hidsystem/IOLLEvent.h
_MAC_KEYCODE_TO_KEY = {
    0x24: Key.enter,        # 36  Return
    0x33: Key.backspace,    # 51  Delete（Mac 的退格键）
    0x75: Key.delete,       # 117 Forward Delete（fn+Delete）
    0x30: Key.tab,          # 48  Tab
    0x35: Key.esc,          # 53  Escape
    0x31: Key.space,        # 49  Space
    0x7B: Key.left,         # 123 Left
    0x7C: Key.right,        # 124 Right
    0x7D: Key.down,         # 125 Down
    0x7E: Key.up,           # 126 Up
    0x73: Key.home,         # 115 Home
    0x77: Key.end,          # 117 End
}

# 功能键 keycode 集合（这些键不发字符，仅作为特殊键事件）
_FUNCTION_KEYCODES = set(_MAC_KEYCODE_TO_KEY.keys())

# 当中文输入法或部分沙盒 App 不向 CGEvent 提供 Unicode 字符时，仍可从
# macOS 虚拟键码还原物理 QWERTY 按键。这里的结果代表实际敲击的键（通常是
# 拼音/英文），而不是试图猜测尚未提交的中文候选词。
_MAC_KEYCODE_TO_ASCII = {
    0x00: "a", 0x01: "s", 0x02: "d", 0x03: "f", 0x04: "h", 0x05: "g",
    0x06: "z", 0x07: "x", 0x08: "c", 0x09: "v", 0x0B: "b", 0x0C: "q",
    0x0D: "w", 0x0E: "e", 0x0F: "r", 0x10: "y", 0x11: "t", 0x12: "1",
    0x13: "2", 0x14: "3", 0x15: "4", 0x16: "6", 0x17: "5", 0x18: "=",
    0x19: "9", 0x1A: "7", 0x1B: "-", 0x1C: "8", 0x1D: "0", 0x1E: "]",
    0x1F: "o", 0x20: "u", 0x21: "[", 0x22: "i", 0x23: "p", 0x25: "l",
    0x26: "j", 0x27: "'", 0x28: "k", 0x29: ";", 0x2A: "\\", 0x2B: ",",
    0x2C: "/", 0x2D: "n", 0x2E: "m", 0x2F: ".", 0x32: "`",
}
_SHIFTED_ASCII = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^",
    "7": "&", "8": "*", "9": "(", "0": ")", "-": "_", "=": "+",
    "[": "{", "]": "}", "\\": "|", ";": ":", "'": '"', ",": "<",
    ".": ">", "/": "?", "`": "~",
}


# ==================== 事件类型 ====================
class KeyEventType(Enum):
    PRESS = auto()
    RELEASE = auto()


class KeyEvent:
    """键盘事件（与 Windows 版接口完全一致，确保 InputBuffer 无缝兼容）"""

    def __init__(
        self,
        event_type: KeyEventType,
        key,
        char: str | None = None,
        ctrl_pressed: bool = False,
        shortcut_pressed: bool = False,
        is_ime_composition: bool = False,
        is_final_ime_result: bool = False,
        is_physical_fallback: bool = False,
    ):
        self.event_type = event_type
        self.key = key
        self.char = char
        self.timestamp = time.time()
        self.ctrl_pressed = ctrl_pressed
        # Command / Control / Option 组合键属于快捷操作，不应当作文本记录。
        self.shortcut_pressed = shortcut_pressed
        self.is_ime_composition = is_ime_composition
        # AX 监听器只发送输入法已经确认并写入目标输入框的结果。这类事件不应
        # 等待 Enter 或 30 秒超时，必须立即提交，尤其是豆包/搜狗的语音转文字。
        self.is_final_ime_result = is_final_ime_result
        # True 代表 CGEvent 没有提供 Unicode，字符由物理键码还原。
        # 这是无法获得输入框/输入法最终文本时的第二策略，不等同于中文识别结果。
        self.is_physical_fallback = is_physical_fallback
        self.input_source = ""

    @property
    def is_enter(self) -> bool:
        return self.key == Key.enter

    @property
    def is_backspace(self) -> bool:
        return self.key == Key.backspace

    @property
    def is_delete(self) -> bool:
        return self.key == Key.delete

    @property
    def is_tab(self) -> bool:
        return self.key == Key.tab

    @property
    def is_ctrl(self) -> bool:
        return self.key in (Key.ctrl, Key.ctrl_l, Key.ctrl_r)

    @property
    def is_alt(self) -> bool:
        return self.key in (Key.alt, Key.alt_l, Key.alt_r)

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
            Key.up, Key.down, Key.left, Key.right,
        )

    @property
    def is_escape(self) -> bool:
        return self.key == Key.esc

    @property
    def is_printable_char(self) -> bool:
        return self.char is not None and len(self.char) == 1 and self.char.isprintable()

    @property
    def is_printable_text(self) -> bool:
        """是否为可记录的单字符或整段 Unicode 文本事件。"""
        return bool(self.char) and all(ch.isprintable() for ch in self.char)

    @property
    def is_ime_text(self) -> bool:
        return self.is_ime_composition

    def __repr__(self):
        char_info = f", char={self.char!r}" if self.char else ""
        ime_info = ", ime=True" if self.is_ime_composition else ""
        return f"KeyEvent({self.event_type.name}, key={self.key}{char_info}{ime_info})"


# ==================== 键盘监听器（CGEventTap + 专用线程 CFRunLoop）====================

class KeyboardHook:
    """键盘监听器 — macOS Quartz CGEventTap 实现

    在专用线程上创建 CGEventTap（kCGSessionEventTap，ListenOnly），
    并将该 tap 加入该线程的 CFRunLoop。事件回调在专用线程触发，
    不依赖 pywebview 主线程。

    stop() 通过 CFRunLoopStop 停止该线程的运行循环。
    """

    # 类级别保持 callback 引用，防止 PyObjC 回调被 GC
    _tap_callback_ref = None

    def __init__(
        self,
        on_event: Callable[[KeyEvent], None],
        capture_hotkeys: bool = True,
    ):
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys

        self._tap = None
        self._source = None
        self._loop = None
        self._hook_thread: threading.Thread | None = None

        self._ctrl_pressed = False
        self._alt_pressed = False
        self._shift_pressed = False
        self._command_pressed = False

        self._event_count = 0
        self._first_event_logged = False
        self._installed = False
        self._stop_flag = False

    def start(self):
        """启动键盘监听（创建专用线程）"""
        if self._installed:
            return

        if not _HAS_MAC_API:
            logger.error("macOS Quartz API 不可用，无法创建键盘事件监听")
            return

        self._stop_flag = False
        self._hook_thread = threading.Thread(
            target=self._hook_thread_main, daemon=True, name="KbHookThread",
        )
        self._hook_thread.start()

        # 等待线程安装完成（最多2秒）
        for _ in range(20):
            if self._installed or self._stop_flag:
                break
            time.sleep(0.1)

        if self._installed:
            logger.info("键盘事件监听已启动 (CGEventTap)")
        else:
            logger.error("键盘事件监听启动失败——请检查「辅助功能」权限是否已授予")

    def _hook_thread_main(self):
        """专用线程主函数：创建 CGEventTap + 运行 CFRunLoop"""
        try:
            # 保持回调引用在类级别，防止 GC 导致崩溃
            KeyboardHook._tap_callback_ref = self._tap_callback

            # 事件掩码：KeyDown + KeyUp + FlagsChanged
            mask = (
                Quartz.CGEventMaskBit(kCGEventKeyDown)
                | Quartz.CGEventMaskBit(kCGEventKeyUp)
                | Quartz.CGEventMaskBit(kCGEventFlagsChanged)
            )

            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,  # 只监听，不拦截/不修改事件
                mask,
                KeyboardHook._tap_callback_ref,
                None,
            )

            if not self._tap:
                logger.error(
                    "CGEventTapCreate 返回 None——未授予辅助功能权限，"
                    "请在「系统设置 > 隐私与安全性 > 辅助功能」中授权本程序"
                )
                return

            self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
            self._loop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(self._loop, self._source, kCFRunLoopDefaultMode)

            self._installed = True
            logger.info("CGEventTap 已安装，运行 CFRunLoop 等待键盘事件...")

            # 启用 tap（防止被系统禁用）
            Quartz.CGEventTapEnable(self._tap, True)

            # 阻塞运行 CFRunLoop
            CFRunLoopRun()

            logger.info("CFRunLoop 已停止 (events=%d)", self._event_count)

        except Exception:
            logger.exception("键盘监听线程异常")
        finally:
            self._installed = False

    def stop(self):
        """停止键盘监听（停止 CFRunLoop）"""
        self._stop_flag = True

        if self._loop:
            try:
                CFRunLoopStop(self._loop)
            except Exception:
                pass

        if self._hook_thread:
            self._hook_thread.join(timeout=2)

        logger.info("KeyboardHook 已停止 (events=%d)", self._event_count)

    # CGEventTapCallBack 签名：(proxy, event_type, event, refcon) -> event
    def _tap_callback(self, proxy, event_type, event, refcon):
        """CGEventTap 回调"""
        try:
            if event_type == kCGEventKeyDown:
                self._event_count += 1
                if not self._first_event_logged:
                    self._first_event_logged = True
                    logger.info("首次按键事件已收到")
                self._process_keydown(event)

            elif event_type == kCGEventKeyUp:
                self._process_keyup(event)

            elif event_type == kCGEventFlagsChanged:
                self._update_modifiers(event)

        except Exception:
            logger.exception("键盘事件回调异常")

        # ListenOnly 模式仍需返回原事件
        return event

    def _get_modifiers(self, event) -> None:
        """从事件的 flags 更新修饰键状态"""
        flags = Quartz.CGEventGetFlags(event)
        self._ctrl_pressed = bool(flags & kCGEventFlagMaskControl)
        self._alt_pressed = bool(flags & kCGEventFlagMaskAlternate)
        self._shift_pressed = bool(flags & kCGEventFlagMaskShift)
        self._command_pressed = bool(flags & kCGEventFlagMaskCommand)

    def _update_modifiers(self, event):
        """FlagsChanged 事件：更新修饰键状态"""
        self._get_modifiers(event)

    def _process_keydown(self, event):
        """处理按键按下"""
        # 先刷新修饰键状态（keydown 事件的 flags 反映当前修饰键）
        self._get_modifiers(event)

        keycode = Quartz.CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

        # 功能键映射（Return / Backspace / Tab / Escape / Space / 方向键 / Home / End / Delete）
        if keycode in _MAC_KEYCODE_TO_KEY:
            key = _MAC_KEYCODE_TO_KEY[keycode]
            # Space/Return/Backspace/Delete/Tab 始终发射；其余功能键按 capture_hotkeys
            if keycode in (0x24, 0x33, 0x75, 0x30, 0x31) or self._capture_hotkeys:
                evt = KeyEvent(
                    KeyEventType.PRESS, key, ctrl_pressed=self._ctrl_pressed,
                )
                self._on_event(evt)
            return

        # 普通字符键 — 优先用 CGEventKeyboardGetUnicodeString 取字符（考虑键盘布局）
        char = self._event_to_char(event)
        used_physical_fallback = not char
        if used_physical_fallback:
            char = self._keycode_to_ascii(keycode, self._shift_pressed)
        if char:
            key = KeyCode(char=char)
            evt = KeyEvent(
                KeyEventType.PRESS, key, char=char,
                ctrl_pressed=self._ctrl_pressed,
                shortcut_pressed=(
                    self._ctrl_pressed or self._alt_pressed or self._command_pressed
                ),
                is_physical_fallback=used_physical_fallback,
            )
            self._on_event(evt)
            # 诊断：前10个字符转换日志
            if self._event_count <= 10:
                logger.info("按键转换: keycode=0x%02X → char=%r (shift=%s, ctrl=%s)",
                            keycode, char, self._shift_pressed, self._ctrl_pressed)
        else:
            if self._event_count <= 10:
                logger.info("按键无法转换: keycode=0x%02X (shift=%s)",
                            keycode, self._shift_pressed)

    def _process_keyup(self, event):
        """处理按键释放（Mac 版仅在 FlagsChanged 跟踪修饰键，keyup 此处空实现）"""
        pass

    @staticmethod
    def _event_to_char(event) -> str | None:
        """从 CGEvent 提取字符（考虑当前键盘布局）

        PyObjC 用法：length, chars = CGEventKeyboardGetUnicodeString(event, max, None, None)
        返回 (length, chars)；chars 为 str（新版 PyObjC）或整数序列（旧版，需 join）。
        对于组合键（如 Ctrl+A）可能返回控制字符（\\x01），由 KeyEvent.is_ctrl_a 判断。
        """
        try:
            result = Quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)
            length = result[0]
            chars = result[1] if len(result) > 1 else ""
            if not length:
                return None
            # chars 可能是 str（新版 PyObjC）或整数序列（旧版）
            if isinstance(chars, str):
                s = chars
            else:
                s = "".join(chr(c) for c in chars)
            if s and len(s) >= 1:
                # 常规按键只返回一个字符；但部分输入法的语音转写会以一次
                # Unicode 键盘事件提交整段最终文本，不能只取第一个字符。
                # 整段文本会在引擎侧仅限豆包/搜狗来源时作为最终 IME 结果处理。
                if any(not ch.isascii() for ch in s):
                    return s
                ch = s[0]
                if ch.isprintable() or ord(ch) < 32:  # 控制字符也保留（如 \x01）
                    return ch
            return None
        except Exception:
            return None

    @staticmethod
    def _keycode_to_ascii(keycode: int, shift_pressed: bool) -> str | None:
        """不依赖目标 App Unicode 回调的物理按键回退。"""
        char = _MAC_KEYCODE_TO_ASCII.get(keycode)
        if not char:
            return None
        if char.isalpha():
            return char.upper() if shift_pressed else char
        return _SHIFTED_ASCII.get(char, char) if shift_pressed else char

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
        """监听线程是否存活"""
        return self._installed and self._hook_thread is not None and self._hook_thread.is_alive()

    def status(self) -> dict[str, int | bool]:
        """返回键盘监听健康状态，不包含任何用户输入内容。"""
        return {"active": self.is_alive, "event_count": self._event_count}
