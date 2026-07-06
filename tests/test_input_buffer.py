"""InputBuffer 单元测试"""

import time
from unittest.mock import MagicMock

import pytest

from src.processor.input_buffer import InputBuffer
from src.collector.keyboard_hook import KeyEvent, KeyEventType

from pynput import keyboard


def _make_char_event(char: str) -> KeyEvent:
    """创建一个字符按键事件"""
    return KeyEvent(KeyEventType.PRESS, key=keyboard.KeyCode.from_char(char), char=char)


def _make_key_event(key) -> KeyEvent:
    """创建一个特殊键事件"""
    return KeyEvent(KeyEventType.PRESS, key=key)


def _make_ime_event(text: str) -> KeyEvent:
    """创建一个 IME 组合文本事件"""
    return KeyEvent(
        KeyEventType.PRESS,
        key=None,
        char=text,
        is_ime_composition=True,
    )


class TestInputBuffer:
    """InputBuffer 状态机测试"""

    def test_basic_typing(self):
        """测试基本英文字符输入"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("h"))
        buf.process_event(_make_char_event("e"))
        buf.process_event(_make_char_event("l"))
        buf.process_event(_make_char_event("l"))
        buf.process_event(_make_char_event("o"))

        assert buf.current_text == "hello"

        # Enter 提交
        buf.process_event(_make_key_event(keyboard.Key.enter))
        assert committed == ["hello"]
        assert buf.is_empty

    def test_backspace(self):
        """测试退格键处理"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("a"))
        buf.process_event(_make_char_event("b"))
        buf.process_event(_make_char_event("c"))
        assert buf.current_text == "abc"

        # 退格一次
        buf.process_event(_make_key_event(keyboard.Key.backspace))
        assert buf.current_text == "ab"

        # 再输入
        buf.process_event(_make_char_event("d"))
        assert buf.current_text == "abd"

    def test_multiple_backspace(self):
        """测试连续退格"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("x"))
        buf.process_event(_make_char_event("y"))
        buf.process_event(_make_key_event(keyboard.Key.backspace))
        buf.process_event(_make_key_event(keyboard.Key.backspace))

        assert buf.current_text == ""

    def test_backspace_at_start(self):
        """测试在缓冲区开头按退格（不应报错）"""
        buf = InputBuffer(on_commit=lambda t: None)
        buf.process_event(_make_key_event(keyboard.Key.backspace))
        assert buf.current_text == ""

    def test_delete_key(self):
        """测试 Delete 键"""
        buf = InputBuffer(on_commit=lambda t: None)

        buf.process_event(_make_char_event("a"))
        buf.process_event(_make_char_event("b"))
        buf.process_event(_make_char_event("c"))
        # 光标在末尾，Delete 无效
        buf.process_event(_make_key_event(keyboard.Key.delete))
        assert buf.current_text == "abc"

    def test_enter_commits(self):
        """测试 Enter 提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("t"))
        buf.process_event(_make_char_event("e"))
        buf.process_event(_make_char_event("s"))
        buf.process_event(_make_char_event("t"))
        buf.process_event(_make_key_event(keyboard.Key.enter))

        assert committed == ["test"]
        assert buf.is_empty

    def test_enter_on_empty_no_commit(self):
        """测试空缓冲区 Enter 不触发提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_key_event(keyboard.Key.enter))
        assert committed == []

    def test_tab_commits(self):
        """测试 Tab 键提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("a"))
        buf.process_event(_make_key_event(keyboard.Key.tab))

        assert committed == ["a"]

    def test_escape_clears(self):
        """测试 Escape 清空缓冲区"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("d"))
        buf.process_event(_make_char_event("a"))
        buf.process_event(_make_char_event("t"))
        buf.process_event(_make_char_event("a"))
        buf.process_event(_make_key_event(keyboard.Key.esc))

        assert buf.is_empty
        assert committed == []

    def test_force_commit(self):
        """测试强制提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("f"))
        buf.process_event(_make_char_event("o"))
        buf.process_event(_make_char_event("o"))
        buf.force_commit()

        assert committed == ["foo"]
        assert buf.is_empty

    def test_force_commit_empty(self):
        """测试强制提交空缓冲区"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))
        buf.force_commit()
        assert committed == []

    def test_max_length_auto_commit(self):
        """测试超过最大长度自动提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t), max_length=5)

        for c in "abcde":
            buf.process_event(_make_char_event(c))
        assert buf.current_text == "abcde"

        # 第6个字符触发提交并开始新缓冲区
        buf.process_event(_make_char_event("f"))
        assert committed == ["abcde"]
        assert buf.current_text == "f"

    def test_multiple_commits(self):
        """测试多次提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        for c in "first":
            buf.process_event(_make_char_event(c))
        buf.process_event(_make_key_event(keyboard.Key.enter))

        for c in "second":
            buf.process_event(_make_char_event(c))
        buf.process_event(_make_key_event(keyboard.Key.enter))

        assert committed == ["first", "second"]

    def test_whitespace_only_no_commit(self):
        """测试纯空白不提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event(" "))
        buf.process_event(_make_char_event(" "))
        buf.force_commit()

        assert committed == []

    def test_timeout_check(self):
        """测试超时自动提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t), timeout=0.01)

        buf.process_event(_make_char_event("a"))
        buf.process_event(_make_char_event("b"))

        # 模拟超时
        buf._last_activity_time = time.time() - 1
        result = buf.check_timeout()

        assert result is True
        assert committed == ["ab"]

    def test_timeout_not_triggered(self):
        """测试未超时不提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t), timeout=30)

        buf.process_event(_make_char_event("a"))
        result = buf.check_timeout()

        assert result is False
        assert committed == []


class TestInputBufferIME:
    """InputBuffer IME 组合文本测试"""

    def test_ime_basic_input(self):
        """测试基本 IME 中文输入"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_ime_event("继续"))
        assert buf.current_text == "继续"

        # Enter 提交
        buf.process_event(_make_key_event(keyboard.Key.enter))
        assert committed == ["继续"]
        assert buf.is_empty

    def test_ime_mixed_with_english(self):
        """测试中文和英文混合输入"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_char_event("h"))
        buf.process_event(_make_char_event("i"))
        buf.process_event(_make_ime_event("你好"))
        buf.process_event(_make_char_event("!"))

        assert buf.current_text == "hi你好!"

        buf.process_event(_make_key_event(keyboard.Key.enter))
        assert committed == ["hi你好!"]

    def test_ime_multiple_compositions(self):
        """测试多次 IME 组合输入"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_ime_event("继续"))
        buf.process_event(_make_ime_event("工作"))

        assert buf.current_text == "继续工作"

        buf.process_event(_make_key_event(keyboard.Key.enter))
        assert committed == ["继续工作"]

    def test_ime_after_ctrl_a(self):
        """测试 Ctrl+A 全选后 IME 输入替换全部"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        # 先输入英文
        for c in "hello":
            buf.process_event(_make_char_event(c))
        assert buf.current_text == "hello"

        # Ctrl+A 全选
        buf.process_event(KeyEvent(
            KeyEventType.PRESS,
            key=keyboard.KeyCode.from_char("a"),
            char="\x01",
            ctrl_pressed=True,
        ))

        # IME 输入应替换全部
        buf.process_event(_make_ime_event("替换"))

        assert buf.current_text == "替换"

    def test_ime_backspace(self):
        """测试 IME 文本后的退格"""
        buf = InputBuffer(on_commit=lambda t: None)

        buf.process_event(_make_ime_event("继续"))
        assert buf.current_text == "继续"

        # 退格删除整段 IME 文本（作为单个缓冲区元素）
        buf.process_event(_make_key_event(keyboard.Key.backspace))
        assert buf.current_text == ""

    def test_ime_then_english_backspace(self):
        """测试 IME 文本 + 英文混合后的退格"""
        buf = InputBuffer(on_commit=lambda t: None)

        buf.process_event(_make_ime_event("你好"))
        buf.process_event(_make_char_event("x"))
        assert buf.current_text == "你好x"

        # 退格删除英文 'x'
        buf.process_event(_make_key_event(keyboard.Key.backspace))
        assert buf.current_text == "你好"

        # 再退格删除整段 IME 文本
        buf.process_event(_make_key_event(keyboard.Key.backspace))
        assert buf.current_text == ""

    def test_ime_force_commit(self):
        """测试 IME 文本的强制提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_ime_event("测试"))
        buf.force_commit()

        assert committed == ["测试"]
        assert buf.is_empty

    def test_ime_tab_commits(self):
        """测试 IME 文本后 Tab 提交"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_ime_event("完成"))
        buf.process_event(_make_key_event(keyboard.Key.tab))

        assert committed == ["完成"]
        assert buf.is_empty

    def test_ime_escape_clears(self):
        """测试 IME 文本后 Escape 清空"""
        committed = []
        buf = InputBuffer(on_commit=lambda t: committed.append(t))

        buf.process_event(_make_ime_event("丢弃"))
        buf.process_event(_make_key_event(keyboard.Key.esc))

        assert buf.is_empty
        assert committed == []

    def test_ime_event_is_not_printable_char(self):
        """测试 IME 事件不会被当作普通可打印字符重复处理"""
        buf = InputBuffer(on_commit=lambda t: None)

        # IME 事件 char 长度 > 1，is_printable_char 应为 False
        event = _make_ime_event("继续")
        assert not event.is_printable_char
        assert event.is_ime_text
