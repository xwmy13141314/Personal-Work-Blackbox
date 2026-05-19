"""会话管理器 — 按应用切换将活动分组为会话"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from src.collector.window_tracker import WindowContext

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """应用会话：用户在一个应用窗口中的连续活动"""
    id: int | None = None
    process_name: str = ""
    window_title: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    text_segments: list[TextSegment] = field(default_factory=list)
    clipboard_items: list = field(default_factory=list)
    idle_seconds: float = 0.0
    is_filtered: bool = False

    @property
    def duration(self) -> float:
        """会话时长（秒）"""
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def active_seconds(self) -> float:
        """活跃时长（扣除空闲）"""
        return max(0, self.duration - self.idle_seconds)

    @property
    def has_content(self) -> bool:
        """是否有实质内容"""
        return bool(self.text_segments) or bool(self.clipboard_items)


@dataclass
class TextSegment:
    """输入文本片段"""
    timestamp: float = field(default_factory=time.time)
    text: str = ""
    source: str = "keyboard"     # 'keyboard' | 'clipboard' | 'ime'
    is_filtered: bool = False
    char_count: int = 0


class SessionManager:
    """会话管理器

    职责：
    1. 维护当前活跃会话
    2. 窗口切换时自动结束旧会话、创建新会话
    3. 收集会话内的文本片段和剪贴板记录
    4. 会话结束时通知存储层持久化
    """

    def __init__(self, on_session_end: Callable[[Session], None]):
        """
        Args:
            on_session_end: 会话结束回调（用于存储层持久化）
        """
        self._on_session_end = on_session_end
        self._current_session: Session | None = None
        self._is_paused = False

    @property
    def current_session(self) -> Session | None:
        return self._current_session

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def pause(self):
        """暂停采集"""
        self._is_paused = True
        self._end_current_session("pause")
        logger.info("会话采集已暂停")

    def resume(self, ctx: WindowContext):
        """恢复采集"""
        self._is_paused = False
        self._start_new_session(ctx)
        logger.info("会话采集已恢复")

    def on_window_switch(self, from_ctx: WindowContext, to_ctx: WindowContext, duration: float):
        """处理窗口切换事件"""
        if self._is_paused:
            return

        # 结束旧会话
        self._end_current_session("window_switch")

        # 创建新会话
        self._start_new_session(to_ctx)

    def on_text_committed(self, text: str, source: str = "keyboard", is_filtered: bool = False):
        """处理文本提交事件（来自 InputBuffer）"""
        if self._is_paused or not self._current_session:
            return

        segment = TextSegment(
            timestamp=time.time(),
            text=text,
            source=source,
            is_filtered=is_filtered,
            char_count=len(text),
        )
        self._current_session.text_segments.append(segment)

    def on_clipboard_change(self, content: str, is_filtered: bool = False):
        """处理剪贴板变化事件"""
        if self._is_paused or not self._current_session:
            return

        segment = TextSegment(
            timestamp=time.time(),
            text=content,
            source="clipboard",
            is_filtered=is_filtered,
            char_count=len(content),
        )
        self._current_session.clipboard_items.append(segment)

    def on_idle_start(self, idle_seconds: float):
        """进入空闲"""
        if self._current_session:
            self._current_session.idle_seconds += idle_seconds

    def on_idle_end(self, idle_duration: float):
        """空闲结束"""
        pass  # 空闲时长已在 on_idle_start 中累加

    def flush(self):
        """强制结束当前会话（程序退出时调用）"""
        self._end_current_session("flush")

    def _start_new_session(self, ctx: WindowContext):
        """创建新会话"""
        self._current_session = Session(
            process_name=ctx.process_name,
            window_title=ctx.window_title,
            start_time=time.time(),
        )
        logger.debug("新会话: %s - %s", ctx.process_name, ctx.window_title[:50])

    def _end_current_session(self, reason: str):
        """结束当前会话并回调持久化"""
        if not self._current_session:
            return

        self._current_session.end_time = time.time()

        # 只有有实质内容的会话才持久化
        if self._current_session.has_content or self._current_session.duration >= 5:
            try:
                self._on_session_end(self._current_session)
            except Exception:
                logger.exception("会话持久化异常")

        logger.debug(
            "会话结束 [%s]: %s, 时长 %.0f 秒, 文本片段 %d 条",
            reason,
            self._current_session.process_name,
            self._current_session.duration,
            len(self._current_session.text_segments),
        )
        self._current_session = None
