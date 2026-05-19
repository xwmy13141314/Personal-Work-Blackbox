"""Database 层单元测试"""

import pytest
from pathlib import Path
from datetime import datetime

from src.storage.database import Database
from src.storage.models import (
    SessionRecord,
    TextSegmentRecord,
    ClipboardRecordModel,
    DailyReportRecord,
    WindowEventRecord,
)


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
def sample_session():
    """示例会话记录"""
    return SessionRecord(
        start_time="2026-05-15T09:00:00",
        end_time="2026-05-15T10:30:00",
        process_name="code.exe",
        window_title="main.py - VS Code",
        idle_seconds=120.0,
        active_seconds=4680.0,
        is_filtered=False,
    )


@pytest.fixture
def sample_session_with_id(db, sample_session):
    """已插入数据库并带有 ID 的会话记录"""
    sid = db.insert_session(sample_session)
    sample_session.id = sid
    return sample_session


# ==================== 初始化与连接 ====================

class TestDatabaseInit:
    """数据库初始化测试"""

    def test_initialize_creates_file(self, tmp_path):
        """初始化后数据库文件应存在"""
        db_path = tmp_path / "new.db"
        database = Database(db_path)
        database.initialize()
        assert db_path.exists()
        database.close()

    def test_initialize_creates_parent_dirs(self, tmp_path):
        """初始化时应自动创建父目录"""
        db_path = tmp_path / "nested" / "dir" / "test.db"
        database = Database(db_path)
        database.initialize()
        assert db_path.exists()
        database.close()

    def test_initialize_idempotent(self, tmp_path):
        """重复初始化不应报错"""
        db_path = tmp_path / "test.db"
        database = Database(db_path)
        database.initialize()
        database.initialize()  # 第二次
        assert db_path.exists()
        database.close()

    def test_is_connected_before_init(self, tmp_path):
        """初始化前 is_connected 应为 False"""
        db_path = tmp_path / "test.db"
        database = Database(db_path)
        assert not database.is_connected

    def test_is_connected_after_init(self, tmp_path):
        """初始化后 is_connected 应为 True"""
        db_path = tmp_path / "test.db"
        database = Database(db_path)
        database.initialize()
        assert database.is_connected
        database.close()

    def test_is_connected_after_close(self, tmp_path):
        """关闭后 is_connected 应为 False"""
        db_path = tmp_path / "test.db"
        database = Database(db_path)
        database.initialize()
        database.close()
        assert not database.is_connected

    def test_cursor_without_init_raises(self, tmp_path):
        """未初始化时操作游标应抛出 RuntimeError"""
        db_path = tmp_path / "test.db"
        database = Database(db_path)
        with pytest.raises(RuntimeError, match="数据库未初始化"):
            with database._cursor() as cur:
                cur.execute("SELECT 1")


# ==================== 会话写入与查询 ====================

class TestSessionOperations:
    """会话 CRUD 测试"""

    def test_insert_session_returns_id(self, db, sample_session):
        """插入会话应返回自增 ID"""
        sid = db.insert_session(sample_session)
        assert isinstance(sid, int)
        assert sid > 0

    def test_insert_session_auto_increment(self, db, sample_session):
        """连续插入的 ID 应递增"""
        sid1 = db.insert_session(sample_session)
        sid2 = db.insert_session(sample_session)
        assert sid2 == sid1 + 1

    def test_query_sessions_by_date(self, db, sample_session):
        """按日期查询会话"""
        db.insert_session(sample_session)
        results = db.query_sessions(date="2026-05-15")
        assert len(results) == 1
        assert results[0].process_name == "code.exe"

    def test_query_sessions_by_date_no_match(self, db, sample_session):
        """查询无匹配日期应返回空列表"""
        db.insert_session(sample_session)
        results = db.query_sessions(date="2025-01-01")
        assert results == []

    def test_query_sessions_by_process(self, db, sample_session):
        """按进程名查询会话"""
        db.insert_session(sample_session)
        results = db.query_sessions(process_name="code.exe")
        assert len(results) == 1

    def test_query_sessions_limit(self, db, sample_session):
        """查询结果应受 limit 限制"""
        for _ in range(5):
            db.insert_session(sample_session)
        results = db.query_sessions(limit=3)
        assert len(results) == 3

    def test_query_sessions_ordered_by_start_time_desc(self, db):
        """查询结果应按开始时间倒序"""
        early = SessionRecord(
            start_time="2026-05-15T08:00:00", process_name="app1.exe",
        )
        late = SessionRecord(
            start_time="2026-05-15T16:00:00", process_name="app2.exe",
        )
        db.insert_session(early)
        db.insert_session(late)
        results = db.query_sessions(date="2026-05-15")
        assert results[0].process_name == "app2.exe"
        assert results[1].process_name == "app1.exe"


# ==================== 文本片段 ====================

class TestTextSegmentOperations:
    """文本片段 CRUD 测试"""

    def test_insert_text_segment(self, db, sample_session_with_id):
        """插入文本片段不应报错"""
        seg = TextSegmentRecord(
            session_id=sample_session_with_id.id,
            timestamp="2026-05-15T09:05:00",
            raw_text="hello world",
            source="keyboard",
            is_filtered=False,
            char_count=11,
        )
        db.insert_text_segment(seg)  # 无异常即通过

    def test_query_text_segments_by_session(self, db, sample_session_with_id):
        """查询会话的文本片段"""
        sid = sample_session_with_id.id
        seg1 = TextSegmentRecord(
            session_id=sid, timestamp="2026-05-15T09:05:00",
            raw_text="hello", source="keyboard", char_count=5,
        )
        seg2 = TextSegmentRecord(
            session_id=sid, timestamp="2026-05-15T09:10:00",
            raw_text="world", source="keyboard", char_count=5,
        )
        db.insert_text_segment(seg1)
        db.insert_text_segment(seg2)
        results = db.query_text_segments(sid)
        assert len(results) == 2
        assert results[0].raw_text == "hello"
        assert results[1].raw_text == "world"

    def test_query_text_segments_empty(self, db, sample_session_with_id):
        """查询无片段的会话应返回空列表"""
        results = db.query_text_segments(sample_session_with_id.id)
        assert results == []


# ==================== 剪贴板记录 ====================

class TestClipboardOperations:
    """剪贴板记录 CRUD 测试"""

    def test_insert_clipboard_record(self, db):
        """插入剪贴板记录"""
        record = ClipboardRecordModel(
            timestamp="2026-05-15T10:00:00",
            content="some copied text",
            content_length=16,
            source_process="chrome.exe",
            source_window="GitHub",
            is_filtered=False,
        )
        db.insert_clipboard_record(record)

    def test_insert_filtered_clipboard(self, db):
        """插入已过滤的剪贴板记录"""
        record = ClipboardRecordModel(
            timestamp="2026-05-15T10:00:00",
            content="[FILTERED_PHONE]",
            content_length=16,
            is_filtered=True,
        )
        db.insert_clipboard_record(record)


# ==================== 窗口事件 ====================

class TestWindowEventOperations:
    """窗口事件 CRUD 测试"""

    def test_insert_window_event(self, db):
        """插入窗口切换事件"""
        event = WindowEventRecord(
            timestamp="2026-05-15T09:00:00",
            event_type="switch",
            process_name="code.exe",
            window_title="main.py - VS Code",
            duration_seconds=120.5,
        )
        db.insert_window_event(event)

    def test_insert_idle_event(self, db):
        """插入空闲事件"""
        event = WindowEventRecord(
            timestamp="2026-05-15T12:00:00",
            event_type="idle_start",
            duration_seconds=300.0,
        )
        db.insert_window_event(event)


# ==================== 日报 ====================

class TestDailyReportOperations:
    """日报 CRUD 测试"""

    def test_insert_and_query_daily_report(self, db):
        """插入并查询日报"""
        report = DailyReportRecord(
            report_date="2026-05-15",
            raw_data_summary="共 5 个会话，3 个应用",
            structured_report="# 日报内容\n今日工作...",
            model_used="glm-4-flash",
            generated_at="2026-05-15T18:00:00",
            format="markdown",
            token_count=500,
        )
        db.insert_daily_report(report)

        result = db.query_daily_report("2026-05-15")
        assert result is not None
        assert result.report_date == "2026-05-15"
        assert result.model_used == "glm-4-flash"
        assert result.structured_report.startswith("# 日报内容")

    def test_query_nonexistent_report(self, db):
        """查询不存在的日报应返回 None"""
        result = db.query_daily_report("2025-01-01")
        assert result is None

    def test_insert_or_replace_report(self, db):
        """同一日期的日报应被覆盖（INSERT OR REPLACE）"""
        report_v1 = DailyReportRecord(
            report_date="2026-05-15",
            structured_report="版本1",
            model_used="glm-4-flash",
            generated_at="2026-05-15T18:00:00",
        )
        db.insert_daily_report(report_v1)

        report_v2 = DailyReportRecord(
            report_date="2026-05-15",
            structured_report="版本2",
            model_used="glm-4-flash",
            generated_at="2026-05-15T20:00:00",
        )
        db.insert_daily_report(report_v2)

        result = db.query_daily_report("2026-05-15")
        assert result.structured_report == "版本2"


# ==================== 应用统计 ====================

class TestAppUsageStats:
    """应用使用统计查询测试"""

    def test_query_app_usage_stats(self, db):
        """查询应用使用统计"""
        db.insert_session(SessionRecord(
            start_time="2026-05-15T09:00:00", end_time="2026-05-15T10:00:00",
            process_name="code.exe", active_seconds=3600.0,
        ))
        db.insert_session(SessionRecord(
            start_time="2026-05-15T10:00:00", end_time="2026-05-15T10:30:00",
            process_name="chrome.exe", active_seconds=1800.0,
        ))
        db.insert_session(SessionRecord(
            start_time="2026-05-15T11:00:00", end_time="2026-05-15T12:00:00",
            process_name="code.exe", active_seconds=3600.0,
        ))

        stats = db.query_app_usage_stats("2026-05-15")
        assert len(stats) == 2
        # code.exe 应排第一（总活跃时间更长）
        assert stats[0]["process_name"] == "code.exe"
        assert stats[0]["session_count"] == 2
        assert stats[0]["active_seconds"] == 7200.0

    def test_query_app_usage_stats_empty(self, db):
        """无数据时查询统计应返回空列表"""
        stats = db.query_app_usage_stats("2025-01-01")
        assert stats == []


# ==================== 日期全文查询 ====================

class TestQueryAllTextForDate:
    """日期全文查询测试"""

    def test_query_all_text_for_date(self, db):
        """查询某天的所有文本片段（跨会话关联）"""
        sid = db.insert_session(SessionRecord(
            start_time="2026-05-15T09:00:00",
            process_name="code.exe",
            window_title="main.py",
        ))
        db.insert_text_segment(TextSegmentRecord(
            session_id=sid, timestamp="2026-05-15T09:05:00",
            raw_text="def hello():", source="keyboard",
        ))
        db.insert_text_segment(TextSegmentRecord(
            session_id=sid, timestamp="2026-05-15T09:10:00",
            raw_text="print('hi')", source="keyboard",
        ))

        results = db.query_all_text_for_date("2026-05-15")
        assert len(results) == 2
        assert results[0]["text"] == "def hello():"
        assert results[0]["process_name"] == "code.exe"
        assert results[1]["text"] == "print('hi')"

    def test_query_all_text_no_match(self, db):
        """查询无数据的日期应返回空列表"""
        results = db.query_all_text_for_date("2025-01-01")
        assert results == []


# ==================== 可用日期查询 ====================

class TestQueryAvailableDates:
    """query_available_dates 测试"""

    def test_returns_dates_with_sessions(self, db):
        """应返回有会话数据的日期列表"""
        db.insert_session(SessionRecord(
            start_time="2026-05-15T09:00:00", process_name="code.exe",
        ))
        db.insert_session(SessionRecord(
            start_time="2026-05-16T10:00:00", process_name="chrome.exe",
        ))
        db.insert_session(SessionRecord(
            start_time="2026-05-16T14:00:00", process_name="code.exe",
        ))

        dates = db.query_available_dates()
        assert "2026-05-15" in dates
        assert "2026-05-16" in dates
        # 同一天只出现一次
        assert dates.count("2026-05-16") == 1

    def test_returns_dates_ordered_desc(self, db):
        """日期应按降序排列（最近的在前）"""
        db.insert_session(SessionRecord(
            start_time="2026-05-14T09:00:00", process_name="a.exe",
        ))
        db.insert_session(SessionRecord(
            start_time="2026-05-16T09:00:00", process_name="b.exe",
        ))
        db.insert_session(SessionRecord(
            start_time="2026-05-15T09:00:00", process_name="c.exe",
        ))

        dates = db.query_available_dates()
        assert dates[0] == "2026-05-16"
        assert dates[1] == "2026-05-15"
        assert dates[2] == "2026-05-14"

    def test_returns_empty_when_no_sessions(self, db):
        """无数据时应返回空列表"""
        dates = db.query_available_dates()
        assert dates == []

    def test_respects_limit(self, db):
        """应受 limit 参数限制"""
        for i in range(10):
            db.insert_session(SessionRecord(
                start_time=f"2026-05-{10+i:02d}T09:00:00", process_name="a.exe",
            ))

        dates = db.query_available_dates(limit=3)
        assert len(dates) == 3
