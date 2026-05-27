"""ReportGenerator 单元测试

通过 mock Database 和 LLMClient 测试报告生成流程。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.ai.report_generator import (
    ReportGenerator,
    _week_range,
    _month_range,
    _week_label,
    _month_label,
)
from src.ai.prompt_engine import PromptEngine
from src.storage.models import (
    SessionRecord,
    TextSegmentRecord,
    DailyReportRecord,
    PeriodReportRecord,
)


# ==================== Fixtures ====================

@pytest.fixture
def mock_db():
    """Mock Database"""
    db = MagicMock()
    db.query_sessions.return_value = []
    db.query_app_usage_stats.return_value = []
    db.query_daily_report.return_value = None
    db.query_text_segments.return_value = []
    db.insert_daily_report = MagicMock()
    db.query_period_report.return_value = None
    db.query_app_usage_stats_range.return_value = []
    db.insert_period_report = MagicMock()
    return db


@pytest.fixture
def mock_llm():
    """Mock LLMClient"""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=("# 日报\n今日工作内容...", "glm"))
    return llm


@pytest.fixture
def prompt_engine():
    """PromptEngine 实例（使用内置模板）"""
    return PromptEngine(template_dir=None)


@pytest.fixture
def generator(mock_db, mock_llm, prompt_engine):
    """ReportGenerator 实例"""
    return ReportGenerator(
        db=mock_db,
        llm_client=mock_llm,
        prompt_engine=prompt_engine,
    )


def _make_session(session_id=1, process_name="code.exe", start="2026-05-15T09:00:00"):
    """创建模拟会话记录"""
    return SessionRecord(
        id=session_id,
        start_time=start,
        end_time="2026-05-15T10:00:00",
        process_name=process_name,
        window_title="main.py - VS Code",
        idle_seconds=60.0,
        active_seconds=3540.0,
    )


def _make_segment(session_id=1, text="hello world"):
    """创建模拟文本片段"""
    return TextSegmentRecord(
        id=1,
        session_id=session_id,
        timestamp="2026-05-15T09:05:00",
        raw_text=text,
        source="keyboard",
        is_filtered=False,
        char_count=len(text),
    )


# ==================== 日报生成 ====================

class TestDailyReport:
    """日报生成测试"""

    @pytest.mark.asyncio
    async def test_generate_with_data(self, generator, mock_db, mock_llm):
        """有数据时应成功生成日报"""
        session = _make_session()
        segment = _make_segment()
        mock_db.query_sessions.return_value = [session]
        mock_db.query_app_usage_stats.return_value = [
            {"process_name": "code.exe", "session_count": 1, "active_seconds": 3540, "idle_seconds": 60},
        ]
        mock_db.query_text_segments.return_value = [segment]

        result = await generator.generate_daily_report("2026-05-15")

        assert result is not None
        assert "# 日报" in result
        mock_llm.complete.assert_called_once()
        mock_db.insert_daily_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_no_data(self, generator, mock_db, mock_llm):
        """无数据时应返回 None"""
        mock_db.query_sessions.return_value = []

        result = await generator.generate_daily_report("2026-05-15")

        assert result is None
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_persists_report(self, generator, mock_db, mock_llm):
        """生成后应将报告持久化到数据库"""
        session = _make_session()
        mock_db.query_sessions.return_value = [session]
        mock_db.query_text_segments.return_value = []

        await generator.generate_daily_report("2026-05-15")

        mock_db.insert_daily_report.assert_called_once()
        record = mock_db.insert_daily_report.call_args[0][0]
        assert isinstance(record, DailyReportRecord)
        assert record.report_date == "2026-05-15"
        assert record.model_used == "glm"

    @pytest.mark.asyncio
    async def test_generate_llm_failure(self, generator, mock_db, mock_llm):
        """LLM 调用失败时应返回 None"""
        session = _make_session()
        mock_db.query_sessions.return_value = [session]
        mock_db.query_text_segments.return_value = []
        mock_llm.complete = AsyncMock(side_effect=Exception("API Error"))

        result = await generator.generate_daily_report("2026-05-15")

        assert result is None
        mock_db.insert_daily_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_overwrites_existing(self, generator, mock_db, mock_llm):
        """已有日报时应覆盖"""
        existing_report = DailyReportRecord(
            id=1, report_date="2026-05-15", structured_report="旧报告",
        )
        mock_db.query_daily_report.return_value = existing_report
        mock_db.query_sessions.return_value = [_make_session()]
        mock_db.query_text_segments.return_value = []

        result = await generator.generate_daily_report("2026-05-15")

        assert result is not None

    @pytest.mark.asyncio
    async def test_generate_default_date(self, generator, mock_db, mock_llm):
        """不传日期时应使用今天"""
        mock_db.query_sessions.return_value = [_make_session()]
        mock_db.query_text_segments.return_value = []

        await generator.generate_daily_report()

        today = datetime.now().strftime("%Y-%m-%d")
        mock_db.query_sessions.assert_called_with(date=today)


# ==================== 周报生成 ====================

class TestWeeklyReport:
    """周报生成测试"""

    @pytest.mark.asyncio
    async def test_generate_with_daily_reports(self, generator, mock_db, mock_llm):
        """有日报数据时应生成周报"""
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d in ["2026-05-11", "2026-05-12"] else None
        )
        mock_db.query_app_usage_stats_range.return_value = [
            {"process_name": "code.exe", "active_seconds": 7200, "session_count": 10},
        ]

        # 2026-05-15 是周五，所在自然周是 05-11(周一) ~ 05-17(周日)
        result = await generator.generate_weekly_report("2026-05-15")

        assert result is not None
        mock_llm.complete.assert_called_once()
        mock_db.insert_period_report.assert_called_once()

        # 验证持久化记录
        record = mock_db.insert_period_report.call_args[0][0]
        assert isinstance(record, PeriodReportRecord)
        assert record.report_type == "weekly"
        assert record.period_start == "2026-05-11"
        assert record.period_end == "2026-05-17"

    @pytest.mark.asyncio
    async def test_generate_no_daily_reports(self, generator, mock_db, mock_llm):
        """无日报数据时应返回 None"""
        mock_db.query_daily_report.return_value = None

        result = await generator.generate_weekly_report("2026-05-15")

        assert result is None
        mock_llm.complete.assert_not_called()
        mock_db.insert_period_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_overwrites_existing(self, generator, mock_db, mock_llm):
        """已有周报时应覆盖"""
        mock_db.query_period_report.return_value = PeriodReportRecord(
            report_type="weekly", period_start="2026-05-11",
            structured_report="旧周报",
        )
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d == "2026-05-11" else None
        )
        mock_db.query_app_usage_stats_range.return_value = []

        result = await generator.generate_weekly_report("2026-05-15")

        assert result is not None
        mock_db.insert_period_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_llm_failure(self, generator, mock_db, mock_llm):
        """LLM 调用失败时应返回 None 且不持久化"""
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d == "2026-05-11" else None
        )
        mock_db.query_app_usage_stats_range.return_value = []
        mock_llm.complete = AsyncMock(side_effect=Exception("API Error"))

        result = await generator.generate_weekly_report("2026-05-15")

        assert result is None
        mock_db.insert_period_report.assert_not_called()


# ==================== 月报生成 ====================

class TestMonthlyReport:
    """月报生成测试"""

    @pytest.mark.asyncio
    async def test_generate_with_daily_reports(self, generator, mock_db, mock_llm):
        """有日报数据时应生成月报"""
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d in ["2026-05-01", "2026-05-02", "2026-05-15"] else None
        )
        mock_db.query_app_usage_stats_range.return_value = [
            {"process_name": "code.exe", "active_seconds": 14400, "session_count": 30},
        ]

        result = await generator.generate_monthly_report("2026-05-15")

        assert result is not None
        mock_llm.complete.assert_called_once()
        mock_db.insert_period_report.assert_called_once()

        record = mock_db.insert_period_report.call_args[0][0]
        assert isinstance(record, PeriodReportRecord)
        assert record.report_type == "monthly"
        assert record.period_start == "2026-05-01"
        assert record.period_end == "2026-05-31"
        assert record.report_label == "2026-05"

    @pytest.mark.asyncio
    async def test_generate_no_daily_reports(self, generator, mock_db, mock_llm):
        """无日报数据时应返回 None"""
        mock_db.query_daily_report.return_value = None

        result = await generator.generate_monthly_report("2026-05-15")

        assert result is None
        mock_llm.complete.assert_not_called()
        mock_db.insert_period_report.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_december_boundary(self, generator, mock_db, mock_llm):
        """12月月报日期范围应正确处理跨年"""
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d == "2026-12-01" else None
        )
        mock_db.query_app_usage_stats_range.return_value = []

        result = await generator.generate_monthly_report("2026-12-25")

        assert result is not None
        record = mock_db.insert_period_report.call_args[0][0]
        assert record.period_start == "2026-12-01"
        assert record.period_end == "2026-12-31"


# ==================== 同步包装 ====================

class TestGenerateSync:
    """同步包装方法测试"""

    def test_generate_sync_daily(self, generator, mock_db, mock_llm):
        """generate_sync 应调用日报异步版本"""
        mock_db.query_sessions.return_value = [_make_session()]
        mock_db.query_text_segments.return_value = []

        result = generator.generate_sync("2026-05-15")

        assert result is not None

    def test_generate_sync_no_data(self, generator, mock_db, mock_llm):
        """无数据时同步版本也应返回 None"""
        mock_db.query_sessions.return_value = []

        result = generator.generate_sync("2026-05-15")

        assert result is None

    def test_generate_period_sync_weekly(self, generator, mock_db, mock_llm):
        """generate_period_sync 应调用周报异步版本"""
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d == "2026-05-11" else None
        )
        mock_db.query_app_usage_stats_range.return_value = []

        result = generator.generate_period_sync("weekly", "2026-05-15")

        assert result is not None

    def test_generate_period_sync_monthly(self, generator, mock_db, mock_llm):
        """generate_period_sync 应调用月报异步版本"""
        mock_db.query_daily_report.side_effect = lambda d: (
            DailyReportRecord(
                report_date=d, structured_report=f"日报 {d}",
                model_used="glm", generated_at=f"{d}T18:00:00",
            ) if d == "2026-05-01" else None
        )
        mock_db.query_app_usage_stats_range.return_value = []

        result = generator.generate_period_sync("monthly", "2026-05-15")

        assert result is not None

    def test_generate_period_sync_invalid_type(self, generator):
        """不支持的报告类型应抛出 ValueError"""
        with pytest.raises(ValueError, match="不支持的报告类型"):
            generator.generate_period_sync("quarterly", "2026-05-15")


# ==================== 日期范围工具函数 ====================

class TestDateRangeUtils:
    """日期范围计算工具函数测试"""

    def test_week_range_monday(self):
        """周一的日期，自然周就是当天到周日"""
        start, end = _week_range("2026-05-11")  # 周一
        assert start == "2026-05-11"
        assert end == "2026-05-17"

    def test_week_range_sunday(self):
        """周日的日期，自然周应为前一个周一到当天"""
        start, end = _week_range("2026-05-17")  # 周日
        assert start == "2026-05-11"
        assert end == "2026-05-17"

    def test_week_range_wednesday(self):
        """周三的日期，自然周应为前一个周一到后一个周日"""
        start, end = _week_range("2026-05-13")  # 周三
        assert start == "2026-05-11"
        assert end == "2026-05-17"

    def test_month_range_first_day(self):
        """月初第一天"""
        start, end = _month_range("2026-05-01")
        assert start == "2026-05-01"
        assert end == "2026-05-31"

    def test_month_range_last_day(self):
        """月末最后一天"""
        start, end = _month_range("2026-05-31")
        assert start == "2026-05-01"
        assert end == "2026-05-31"

    def test_month_range_february_leap(self):
        """闰年2月"""
        start, end = _month_range("2028-02-15")
        assert start == "2028-02-01"
        assert end == "2028-02-29"

    def test_month_range_february_non_leap(self):
        """非闰年2月"""
        start, end = _month_range("2026-02-15")
        assert start == "2026-02-01"
        assert end == "2026-02-28"

    def test_month_range_december(self):
        """12月跨年"""
        start, end = _month_range("2026-12-25")
        assert start == "2026-12-01"
        assert end == "2026-12-31"

    def test_week_label(self):
        """周标签格式"""
        label = _week_label("2026-05-11")
        assert label.startswith("2026-W")

    def test_month_label(self):
        """月标签格式"""
        label = _month_label("2026-05-01")
        assert label == "2026-05"


# ==================== 辅助方法 ====================

class TestHelperMethods:
    """辅助方法测试"""

    def test_sessions_to_context(self, generator, mock_db):
        """会话记录应正确转换为上下文格式"""
        session = _make_session()
        segment = _make_segment()
        mock_db.query_text_segments.return_value = [segment]

        result = generator._sessions_to_context([session])

        assert len(result) == 1
        assert result[0]["process_name"] == "code.exe"
        assert result[0]["window_title"] == "main.py - VS Code"
        assert len(result[0]["text_segments"]) == 1
        assert result[0]["text_segments"][0]["text"] == "hello world"

    def test_sessions_to_context_empty(self, generator, mock_db):
        """空会话列表应返回空列表"""
        result = generator._sessions_to_context([])
        assert result == []

    def test_summarize_raw_data(self):
        """原始数据摘要格式"""
        data = {
            "sessions": [{"id": 1}, {"id": 2}, {"id": 3}],
            "app_usage_stats": [{"name": "a"}, {"name": "b"}],
        }
        result = ReportGenerator._summarize_raw_data(data)
        assert "3 个会话" in result
        assert "2 个应用" in result
