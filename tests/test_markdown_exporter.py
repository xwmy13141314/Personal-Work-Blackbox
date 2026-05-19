"""MarkdownExporter 单元测试"""

import pytest
from pathlib import Path

from src.storage.database import Database
from src.storage.markdown_exporter import MarkdownExporter, _format_duration
from src.storage.models import SessionRecord, TextSegmentRecord


# ==================== Fixtures ====================

@pytest.fixture
def db(tmp_path):
    """创建临时数据库"""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def exporter(db, tmp_path):
    """创建 MarkdownExporter 实例"""
    export_dir = tmp_path / "logs"
    return MarkdownExporter(db=db, export_dir=export_dir)


def _insert_session_with_segments(db, process_name, start_time, end_time, segments_text=None):
    """辅助函数：插入会话及其文本片段"""
    session = SessionRecord(
        start_time=start_time,
        end_time=end_time,
        process_name=process_name,
        window_title=f"{process_name} - Window",
        active_seconds=3600.0,
    )
    sid = db.insert_session(session)
    session.id = sid

    if segments_text:
        for i, text in enumerate(segments_text):
            seg = TextSegmentRecord(
                session_id=sid,
                timestamp=f"{start_time[:11]}09:0{i+1}:00",
                raw_text=text,
                source="keyboard",
                char_count=len(text),
            )
            db.insert_text_segment(seg)

    return session


# ==================== _format_duration 辅助函数 ====================

class TestFormatDuration:
    """时长格式化测试"""

    def test_seconds(self):
        assert _format_duration(30) == "30s"

    def test_minutes_only(self):
        assert _format_duration(120) == "2m"

    def test_hours_and_minutes(self):
        assert _format_duration(3660) == "1h 01m"

    def test_zero(self):
        assert _format_duration(0) == "0s"

    def test_large_hours(self):
        assert _format_duration(14400) == "4h 00m"


# ==================== 导出功能 ====================

class TestExportDaily:
    """每日导出测试"""

    def test_export_creates_file(self, exporter, db, tmp_path):
        """导出应创建 Markdown 文件"""
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["def hello():", "print('world')"],
        )

        result = exporter.export_daily("2026-05-15")
        assert result.exists()
        assert result.name == "2026-05-15.md"

    def test_export_contains_header(self, exporter, db):
        """导出文件应包含日期标题"""
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["some text"],
        )

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "# 工作日志 - 2026-05-15" in content

    def test_export_contains_weekday(self, exporter, db):
        """导出文件应包含星期信息"""
        # 2026-05-15 是周五
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["text"],
        )

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "周五" in content

    def test_export_contains_process_name(self, exporter, db):
        """导出文件应包含进程名"""
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["typing code"],
        )

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "code.exe" in content

    def test_export_contains_text_segments(self, exporter, db):
        """导出文件应包含文本片段内容"""
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["def hello():", "return 42"],
        )

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "def hello():" in content
        assert "return 42" in content

    def test_export_contains_app_stats_table(self, exporter, db):
        """导出文件应包含应用使用统计表格"""
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["text"],
        )

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "今日概览" in content
        assert "| 应用 |" in content

    def test_export_empty_data(self, exporter, tmp_path):
        """无数据导出应返回路径但不崩溃"""
        result = exporter.export_daily("2025-01-01")
        assert result.name == "2025-01-01.md"
        # 无数据时不创建文件（仅返回预期路径）

    def test_export_creates_directory(self, db, tmp_path):
        """导出目录不存在时应自动创建"""
        export_dir = tmp_path / "deep" / "nested" / "logs"
        exp = MarkdownExporter(db=db, export_dir=export_dir)
        result = exp.export_daily("2025-01-01")
        assert export_dir.exists()

    def test_export_multiple_sessions(self, exporter, db):
        """导出多个会话"""
        _insert_session_with_segments(
            db, "code.exe",
            "2026-05-15T09:00:00", "2026-05-15T10:00:00",
            ["code text"],
        )
        _insert_session_with_segments(
            db, "chrome.exe",
            "2026-05-15T10:00:00", "2026-05-15T11:00:00",
            ["search query"],
        )

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "code.exe" in content
        assert "chrome.exe" in content

    def test_export_clipboard_segment(self, exporter, db):
        """导出应区分剪贴板片段"""
        sid = db.insert_session(SessionRecord(
            start_time="2026-05-15T09:00:00",
            end_time="2026-05-15T10:00:00",
            process_name="code.exe",
            active_seconds=3600.0,
        ))
        db.insert_text_segment(TextSegmentRecord(
            session_id=sid, timestamp="2026-05-15T09:05:00",
            raw_text="pasted content", source="clipboard", char_count=14,
        ))

        result = exporter.export_daily("2026-05-15")
        content = result.read_text(encoding="utf-8")
        assert "[剪贴板]" in content
