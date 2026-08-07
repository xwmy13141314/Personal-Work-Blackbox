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
    category: str = "其他"
    icon: str = "📦"


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


@dataclass
class PeriodReportRecord:
    """AI 周报/月报记录"""
    id: Optional[int] = None
    report_type: str = ""         # 'weekly' | 'monthly'
    period_start: str = ""        # YYYY-MM-DD（周一/月初）
    period_end: str = ""          # YYYY-MM-DD（周日/月末）
    report_label: str = ""        # 显示标签，如 "2026-W21" 或 "2026-05"
    structured_report: str = ""
    model_used: str = ""
    generated_at: str = ""
    format: str = "markdown"
    token_count: int = 0


@dataclass
class TodoRecord:
    """待办事项记录（从报告中提取或手动新建）"""
    id: Optional[int] = None
    title: str = ""                 # 待办内容（必填）
    status: str = "pending"         # pending | in_progress | done | cancelled
    priority: str = "normal"        # low | normal | high | urgent
    note: str = ""                  # 备注
    due_date: str = ""              # 截止日期 YYYY-MM-DD（可空）
    source_type: str = "manual"     # daily_report | weekly_report | monthly_report | manual
    source_ref: str = ""            # 来源标识，如日报日期 "2026-08-06"
    is_draft: bool = True           # 草稿区：AI 提取的待办先进草稿，用户采纳后才正式入库
    created_at: str = ""            # ISO8601
    updated_at: str = ""            # ISO8601
    completed_at: str = ""          # 完成时间 ISO8601（仅 status=done 时有值）
