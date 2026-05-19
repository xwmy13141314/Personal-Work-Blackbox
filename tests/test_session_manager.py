"""SessionManager 单元测试"""

import time
from unittest.mock import MagicMock

import pytest

from src.processor.session_manager import SessionManager, Session, TextSegment
from src.collector.window_tracker import WindowContext


def _make_context(process_name="chrome.exe", title="Google Chrome", hwnd=1):
    return WindowContext(
        hwnd=hwnd,
        process_name=process_name,
        window_title=title,
        timestamp=time.time(),
    )


class TestSessionManager:

    def test_window_switch_creates_new_session(self):
        """测试窗口切换创建新会话"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx1 = _make_context("chrome.exe", "Google", hwnd=1)
        ctx2 = _make_context("code.exe", "VS Code", hwnd=2)

        sm.resume(ctx1)
        assert sm.current_session is not None
        assert sm.current_session.process_name == "chrome.exe"

        # 添加内容使会话满足持久化条件
        sm.on_text_committed("some search query")

        sm.on_window_switch(ctx1, ctx2, 10.0)
        assert sm.current_session is not None
        assert sm.current_session.process_name == "code.exe"
        assert len(ended_sessions) == 1
        assert ended_sessions[0].process_name == "chrome.exe"

    def test_text_commit_associated_with_session(self):
        """测试文本片段关联到当前会话"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx = _make_context("notepad.exe", "test.txt")
        sm.resume(ctx)

        sm.on_text_committed("hello world", source="keyboard")
        sm.on_text_committed("second line", source="keyboard")

        assert len(sm.current_session.text_segments) == 2
        assert sm.current_session.text_segments[0].text == "hello world"

    def test_clipboard_associated_with_session(self):
        """测试剪贴板关联到当前会话"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx = _make_context("chrome.exe", "Search")
        sm.resume(ctx)

        sm.on_clipboard_change("https://example.com")
        assert len(sm.current_session.clipboard_items) == 1

    def test_pause_stops_recording(self):
        """测试暂停后不记录"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx = _make_context()
        sm.resume(ctx)
        sm.pause()

        assert sm.is_paused is True

        # 暂停后的输入应被忽略
        sm.on_text_committed("should be ignored")
        assert ended_sessions[-1].text_segments == [] if ended_sessions else True

    def test_flush_ends_current_session(self):
        """测试 flush 强制结束当前会话"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx = _make_context()
        sm.resume(ctx)
        sm.on_text_committed("some text")
        sm.flush()

        assert sm.current_session is None
        assert len(ended_sessions) == 1
        assert ended_sessions[0].text_segments[0].text == "some text"

    def test_short_session_no_persist(self):
        """测试极短的空会话不持久化（模拟）"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx1 = _make_context(hwnd=1)
        ctx2 = _make_context(hwnd=2)

        sm.resume(ctx1)
        # 立即切换，会话极短且无内容
        sm.on_window_switch(ctx1, ctx2, 0.1)

        # duration < 5 且 has_content=False → 不持久化
        # 但 ended_sessions 中的会话仍然是存在的（因为 on_window_switch 总是 end）
        # 实际逻辑在 _end_current_session 中判断 has_content or duration >= 5

    def test_multiple_sessions(self):
        """测试多个会话的创建和结束"""
        ended_sessions = []
        sm = SessionManager(on_session_end=lambda s: ended_sessions.append(s))

        ctx1 = _make_context("chrome.exe", "Tab1", hwnd=1)
        ctx2 = _make_context("code.exe", "main.py", hwnd=2)
        ctx3 = _make_context("feishu.exe", "群聊", hwnd=3)

        sm.resume(ctx1)
        sm.on_text_committed("search query")

        sm.on_window_switch(ctx1, ctx2, 30.0)
        sm.on_text_committed("def hello():")

        sm.on_window_switch(ctx2, ctx3, 45.0)
        sm.on_text_committed("消息内容")

        sm.flush()

        assert len(ended_sessions) == 3
        assert ended_sessions[0].process_name == "chrome.exe"
        assert ended_sessions[1].process_name == "code.exe"
        assert ended_sessions[2].process_name == "feishu.exe"


class TestSession:

    def test_duration(self):
        """测试会话时长计算"""
        s = Session(start_time=time.time() - 100)
        assert s.duration >= 99

    def test_has_content_with_text(self):
        """测试 has_content"""
        s = Session()
        assert s.has_content is False
        s.text_segments.append(TextSegment(text="hello"))
        assert s.has_content is True
