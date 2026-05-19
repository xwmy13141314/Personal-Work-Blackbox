"""数据模型定义"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WindowEventRecord:
    """窗口切换事件记录"""
    id: Optional[int] = None
    timestamp: str = ""           # ISO8601
    event_type: str = "switch"    # switch | idle_start | idle_end | lock | unlock
    process_name: str = ""
    window_title: str = ""
    duration_seconds: float = 0.0
    session_id: Optional[int] = None


@dataclass
class TextSegmentRecord:
    """文本片段记录"""
    id: Optional[int] = None
    session_id: int = 0
    timestamp: str = ""
    raw_text: str = ""
    source: str = "keyboard"     # keyboard | clipboard | ime
    is_filtered: bool = False
    char_count: int = 0


@dataclass
class SessionRecord:
    """应用会话记录"""
    id: Optional[int] = None
    start_time: str = ""
    end_time: str = ""
    process_name: str = ""
    window_title: str = ""
    idle_seconds: float = 0.0
    active_seconds: float = 0.0
    is_filtered: bool = False


@dataclass
class ClipboardRecordModel:
    """剪贴板记录"""
    id: Optional[int] = None
    timestamp: str = ""
    content: str = ""
    content_length: int = 0
    source_process: str = ""
    source_window: str = ""
    is_filtered: bool = False


@dataclass
class DailyReportRecord:
    """AI 日报记录"""
    id: Optional[int] = None
    report_date: str = ""         # YYYY-MM-DD
    raw_data_summary: str = ""
    structured_report: str = ""
    model_used: str = ""
    generated_at: str = ""
    format: str = "markdown"
    token_count: int = 0
