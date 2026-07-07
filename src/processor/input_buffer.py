"""输入缓冲区状态机 — 处理退格等编辑逻辑，还原可读文本

线程安全：内部使用 threading.Lock 保护所有缓冲区操作，
确保键盘线程的 process_event 与窗口/空闲线程的 force_commit 不会竞态。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from pynput import keyboard
from src.collector.keyboard_hook import KeyEvent, KeyEventType

logger = logging.getLogger(__name__)


class InputBuffer:
    """输入缓冲区状态机（线程安全）

    将原始键码流还原为可读文本：
    - 普通字符 → 追加到缓冲区
    - Backspace → 删除末字符
    - Delete → 删除光标后字符
    - Ctrl+A → 标记全选，下次输入替换全部内容
    - Enter → 提交缓冲区
    - 方向键 → 暂停追加（光标移动）
    - 窗口切换 → 强制提交
    """

    def __init__(
        self,
        on_commit: Callable[[str], None],
        max_length: int = 5000,
        timeout: float = 30.0,
    ):
        """
        Args:
            on_commit: 缓冲区提交回调，参数为提交的文本
            max_length: 缓冲区最大长度
            timeout: 超时提交时间（秒）
        """
        self._on_commit = on_commit
        self._max_length = max_length
        self._timeout = timeout

        self._buffer: list[str] = []
        self._cursor_pos: int = 0
        self._last_activity_time: float = time.time()
        self._select_all: bool = False
        self._lock = threading.Lock()

    @property
    def current_text(self) -> str:
        """当前缓冲区文本"""
        return "".join(self._buffer)

    @property
    def is_empty(self) -> bool:
        return len(self._buffer) == 0

    @property
    def last_activity_time(self) -> float:
        return self._last_activity_time

    def process_event(self, event: KeyEvent):
        """处理一个键盘事件（线程安全）"""
        if event.event_type != KeyEventType.PRESS:
            return

        with self._lock:
            self._last_activity_time = time.time()

            # IME 组合文本 — 将整段组合文本作为一个片段处理（不逐字符追加）
            if getattr(event, 'is_ime_composition', False) and event.char:
                self._on_ime_text(event.char)
                return

            # Ctrl+A → 标记全选（下次输入替换全部）
            if event.is_ctrl_a:
                self._select_all = True
                return

            # Enter → 提交
            if event.is_enter:
                self._commit()
                return

            # Backspace
            if event.is_backspace:
                self._on_backspace()
                return

            # Delete
            if event.is_delete:
                self._on_delete()
                return

            # Tab → 提交当前缓冲区（通常切换输入字段）
            if event.is_tab:
                self._commit()
                return

            # Escape → 丢弃当前缓冲区
            if event.is_escape:
                self._buffer.clear()
                self._cursor_pos = 0
                self._select_all = False
                return

            # 方向键 → 仅更新光标位置
            if event.is_arrow:
                self._on_arrow(event)
                return

            # 可打印字符
            if event.is_printable_char and event.char:
                self._on_char(event.char)

    def force_commit(self):
        """强制提交当前缓冲区（窗口切换/空闲时调用，线程安全）"""
        with self._lock:
            if not self.is_empty:
                self._commit()

    def check_timeout(self) -> bool:
        """检查是否超时，超时则自动提交。返回是否发生了提交。（线程安全）"""
        with self._lock:
            if self.is_empty:
                return False
            if time.time() - self._last_activity_time >= self._timeout:
                self._commit()
                return True
            return False

    def clear(self):
        """清空缓冲区"""
        self._buffer.clear()
        self._cursor_pos = 0
        self._select_all = False

    def _on_char(self, char: str):
        """处理普通字符"""
        # 如果之前全选了，先清空
        if self._select_all:
            self._buffer.clear()
            self._cursor_pos = 0
            self._select_all = False

        # 长度限制
        if len(self._buffer) >= self._max_length:
            self._commit()

        # 插入字符
        if self._cursor_pos >= len(self._buffer):
            self._buffer.append(char)
        else:
            self._buffer.insert(self._cursor_pos, char)
        self._cursor_pos += 1

    def _on_ime_text(self, text: str):
        """处理 IME 组合完成的文本（整段作为一个片段插入）

        与 _on_char 不同，IME 组合文本是输入法已完成的整段汉字，
        作为一个语义片段整体插入缓冲区，而非逐字符追加。

        智能去重：当 IME 组合结果到达时，自动移除缓冲区末尾的连续 ASCII
        小写字母（它们是输入该汉字时敲下的拼音字母），避免缓冲区同时
        包含拼音和汉字（如 "jixu继续"）。
        """
        # 如果之前全选了，先清空（下次输入替换全部）
        if self._select_all:
            self._buffer.clear()
            self._cursor_pos = 0
            self._select_all = False

        # 智能去重：移除光标前方连续的 ASCII 小写字母（拼音字母）
        # 这些字母是用户输入拼音时 pynput 捕获的，现在被 IME 组合结果替换
        removed_count = 0
        while self._cursor_pos > 0 and removed_count < 12:
            idx = self._cursor_pos - 1
            if idx < len(self._buffer):
                ch = self._buffer[idx]
                # 只移除单个 ASCII 小写字母（拼音由 a-z 组成）
                if len(ch) == 1 and ch.isascii() and ch.islower():
                    self._buffer.pop(idx)
                    self._cursor_pos -= 1
                    removed_count += 1
                else:
                    break
            else:
                break

        # 长度限制检查（按当前缓冲区元素数）
        if len(self._buffer) >= self._max_length:
            self._commit()

        # 将整段组合文本作为单个片段插入到光标位置
        if self._cursor_pos >= len(self._buffer):
            self._buffer.append(text)
        else:
            self._buffer.insert(self._cursor_pos, text)
        # 光标移动到插入文本之后（缓冲区末尾）
        self._cursor_pos = len(self._buffer)

    def _on_backspace(self):
        """处理退格键"""
        if self._select_all:
            self._buffer.clear()
            self._cursor_pos = 0
            self._select_all = False
            return

        if self._cursor_pos > 0:
            self._cursor_pos -= 1
            if self._cursor_pos < len(self._buffer):
                self._buffer.pop(self._cursor_pos)

    def _on_delete(self):
        """处理 Delete 键"""
        if self._select_all:
            self._buffer.clear()
            self._cursor_pos = 0
            self._select_all = False
            return

        if self._cursor_pos < len(self._buffer):
            self._buffer.pop(self._cursor_pos)

    def _on_arrow(self, event: KeyEvent):
        """处理方向键（移动光标）"""
        if event.key == keyboard.Key.left:
            self._cursor_pos = max(0, self._cursor_pos - 1)
        elif event.key == keyboard.Key.right:
            self._cursor_pos = min(len(self._buffer), self._cursor_pos + 1)
        # Home / End
        elif event.key == keyboard.Key.home:
            self._cursor_pos = 0
        elif event.key == keyboard.Key.end:
            self._cursor_pos = len(self._buffer)
        # Ctrl+A 标记
        self._select_all = False

    def _commit(self):
        """提交当前缓冲区内容"""
        text = "".join(self._buffer).strip()
        if text:
            self._on_commit(text)
        self._buffer.clear()
        self._cursor_pos = 0
        self._select_all = False
