"""报告生成器 — 从数据库读取数据、构建 Prompt、调用 LLM、持久化报告"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .llm_client import LLMClient
from .prompt_engine import PromptEngine
from . import __init__  # 确保 src.ai 可导入

if TYPE_CHECKING:
    from src.storage.database import Database

logger = logging.getLogger(__name__)


def _week_range(date_str: str) -> tuple[str, str]:
    """计算指定日期所在自然周（周一~周日）"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # weekday(): Monday=0, Sunday=6
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def _month_range(date_str: str) -> tuple[str, str]:
    """计算指定日期所在自然月（月初~月末）"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    first_day = dt.replace(day=1)
    # 下个月1号减1天 = 本月最后一天
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    last_day = next_month - timedelta(days=1)
    return first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")


def _week_label(start: str) -> str:
    """生成周标签，如 "2026-W21" """
    dt = datetime.strptime(start, "%Y-%m-%d")
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_label(start: str) -> str:
    """生成月标签，如 "2026-05" """
    return start[:7]


class ReportGenerator:
    """报告生成器

    职责：
    1. 从数据库读取指定日期的活动数据
    2. 通过 PromptEngine 构建提示词
    3. 调用 LLMClient 生成报告
    4. 将报告持久化到数据库
    5. 可选：导出 Markdown 文件
    """

    def __init__(
        self,
        db: Database,
        llm_client: LLMClient,
        prompt_engine: PromptEngine,
    ):
        self._db = db
        self._llm = llm_client
        self._prompt = prompt_engine

    # ==================== 日报 ====================

    async def generate_daily_report(self, date: str | None = None) -> str | None:
        """生成指定日期的日报

        Args:
            date: YYYY-MM-DD 格式，默认今天

        Returns:
            生成的报告内容（Markdown），失败返回 None
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")

        # 检查是否已有报告
        existing = self._db.query_daily_report(target_date)
        if existing:
            logger.info("日期 %s 已有日报，将覆盖", target_date)

        # 收集数据
        logger.info("正在收集 %s 的活动数据...", target_date)
        sessions = self._db.query_sessions(date=target_date)
        app_stats = self._db.query_app_usage_stats(date=target_date)

        if not sessions:
            logger.warning("日期 %s 无活动数据，跳过日报生成", target_date)
            return None

        # 构建数据上下文
        sessions_data = self._sessions_to_context(sessions)
        data = {
            "date": target_date,
            "app_usage_stats": app_stats,
            "sessions": sessions_data,
        }

        # 构建 Prompt
        messages = self._prompt.build_daily_prompt(data)

        # 调用 LLM（LLMClient 内部已有重试和降级逻辑）
        logger.info("正在调用 LLM 生成日报（%s）...", target_date)
        try:
            report_content, model_used = await self._llm.complete(messages)
            logger.info("日报生成完成，使用模型: %s", model_used)
        except Exception as exc:
            logger.exception("LLM 调用失败（已耗尽重试和降级）: %s", exc)
            return None

        # 持久化
        from src.storage.models import DailyReportRecord
        record = DailyReportRecord(
            report_date=target_date,
            raw_data_summary=self._summarize_raw_data(data),
            structured_report=report_content,
            model_used=model_used,
            generated_at=datetime.now().isoformat(),
            format="markdown",
            token_count=len(report_content),  # 近似值
        )
        self._db.insert_daily_report(record)

        return report_content

    def generate_sync(self, date: str | None = None) -> str | None:
        """同步版本的日报生成（便于在非异步上下文中调用）"""
        return asyncio.run(self.generate_daily_report(date))

    # ==================== 周报 ====================

    async def generate_weekly_report(self, date: str | None = None) -> str | None:
        """生成指定日期所在自然周的周报

        Args:
            date: YYYY-MM-DD 格式（该周中任意一天），默认今天

        Returns:
            生成的周报内容（Markdown），失败返回 None
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        period_start, period_end = _week_range(target_date)
        label = _week_label(period_start)

        # 检查是否已有周报
        existing = self._db.query_period_report("weekly", period_start)
        if existing:
            logger.info("周期 %s 已有周报，将覆盖", label)

        # 逐日收集日报
        logger.info("正在收集 %s 的日报数据...", label)
        daily_reports = []
        missing_dates = []
        all_dates = []

        current = datetime.strptime(period_start, "%Y-%m-%d")
        end_dt = datetime.strptime(period_end, "%Y-%m-%d")
        while current <= end_dt:
            d = current.strftime("%Y-%m-%d")
            all_dates.append(d)
            report = self._db.query_daily_report(d)
            if report:
                daily_reports.append({
                    "date": d,
                    "structured_report": report.structured_report,
                })
            else:
                missing_dates.append(d)
            current += timedelta(days=1)

        if not daily_reports:
            logger.warning("周期 %s 无任何日报数据，跳过周报生成", label)
            return None

        # 跨日应用统计
        app_stats = self._db.query_app_usage_stats_range(period_start, period_end)

        data = {
            "daily_reports": daily_reports,
            "app_usage_stats": app_stats,
            "period_start": period_start,
            "period_end": period_end,
            "total_days": len(all_dates),
            "report_days": len(daily_reports),
            "missing_dates": missing_dates,
        }

        # 构建 Prompt 并调用 LLM
        messages = self._prompt.build_weekly_prompt(data)
        logger.info("正在调用 LLM 生成周报（%s）...", label)
        try:
            report_content, model_used = await self._llm.complete(messages)
            logger.info("周报生成完成，使用模型: %s", model_used)
        except Exception as exc:
            logger.exception("周报生成失败: %s", exc)
            return None

        # 持久化
        from src.storage.models import PeriodReportRecord
        record = PeriodReportRecord(
            report_type="weekly",
            period_start=period_start,
            period_end=period_end,
            report_label=label,
            structured_report=report_content,
            model_used=model_used,
            generated_at=datetime.now().isoformat(),
            format="markdown",
            token_count=len(report_content),
        )
        self._db.insert_period_report(record)

        return report_content

    # ==================== 月报 ====================

    async def generate_monthly_report(self, date: str | None = None) -> str | None:
        """生成指定日期所在自然月的月报

        Args:
            date: YYYY-MM-DD 格式（该月中任意一天），默认今天

        Returns:
            生成的月报内容（Markdown），失败返回 None
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        period_start, period_end = _month_range(target_date)
        label = _month_label(period_start)

        # 检查是否已有月报
        existing = self._db.query_period_report("monthly", period_start)
        if existing:
            logger.info("周期 %s 已有月报，将覆盖", label)

        # 逐日收集日报
        logger.info("正在收集 %s 的日报数据...", label)
        daily_reports = []
        missing_dates = []
        all_dates = []

        current = datetime.strptime(period_start, "%Y-%m-%d")
        end_dt = datetime.strptime(period_end, "%Y-%m-%d")
        while current <= end_dt:
            d = current.strftime("%Y-%m-%d")
            all_dates.append(d)
            report = self._db.query_daily_report(d)
            if report:
                daily_reports.append({
                    "date": d,
                    "structured_report": report.structured_report,
                })
            else:
                missing_dates.append(d)
            current += timedelta(days=1)

        if not daily_reports:
            logger.warning("周期 %s 无任何日报数据，跳过月报生成", label)
            return None

        # 跨日应用统计
        app_stats = self._db.query_app_usage_stats_range(period_start, period_end)

        data = {
            "daily_reports": daily_reports,
            "app_usage_stats": app_stats,
            "period_start": period_start,
            "period_end": period_end,
            "total_days": len(all_dates),
            "report_days": len(daily_reports),
            "missing_dates": missing_dates,
        }

        # 构建 Prompt 并调用 LLM
        messages = self._prompt.build_monthly_prompt(data)
        logger.info("正在调用 LLM 生成月报（%s）...", label)
        try:
            report_content, model_used = await self._llm.complete(messages)
            logger.info("月报生成完成，使用模型: %s", model_used)
        except Exception as exc:
            logger.exception("月报生成失败: %s", exc)
            return None

        # 持久化
        from src.storage.models import PeriodReportRecord
        record = PeriodReportRecord(
            report_type="monthly",
            period_start=period_start,
            period_end=period_end,
            report_label=label,
            structured_report=report_content,
            model_used=model_used,
            generated_at=datetime.now().isoformat(),
            format="markdown",
            token_count=len(report_content),
        )
        self._db.insert_period_report(record)

        return report_content

    # ==================== 统一入口 ====================

    def generate_period_sync(
        self, report_type: str, date: str | None = None
    ) -> str | None:
        """同步版本的周报/月报生成

        Args:
            report_type: 'weekly' | 'monthly'
            date: YYYY-MM-DD 格式，默认今天

        Returns:
            生成的报告内容（Markdown），失败返回 None
        """
        if report_type == "weekly":
            return asyncio.run(self.generate_weekly_report(date))
        elif report_type == "monthly":
            return asyncio.run(self.generate_monthly_report(date))
        else:
            raise ValueError(f"不支持的报告类型: {report_type}")

    # ==================== 自动补生成 ====================

    def find_missing_report_dates(self, days: int = 7) -> list[str]:
        """查找有采集数据但缺少日报的日期

        Args:
            days: 回溯天数

        Returns:
            缺少报告的日期列表（升序，最早的在前）
        """
        missing = []
        today = datetime.now()

        for i in range(days):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")

            # 跳过今天（可能还在采集中）
            if d == today.strftime("%Y-%m-%d"):
                continue

            # 检查是否有采集数据
            sessions = self._db.query_sessions(date=d, limit=1)
            if not sessions:
                continue

            # 检查是否已有报告
            report = self._db.query_daily_report(d)
            if not report:
                missing.append(d)

        missing.reverse()  # 升序，先补最早的
        return missing

    def auto_generate_missing(self, days: int = 7) -> list[str]:
        """自动补生成缺失的日报

        Returns:
            成功生成的日期列表
        """
        missing_dates = self.find_missing_report_dates(days)

        if not missing_dates:
            logger.info("无需补生成日报")
            return []

        logger.info("发现 %d 天缺少日报，开始补生成: %s", len(missing_dates), missing_dates)
        generated = []

        for d in missing_dates:
            try:
                report = self.generate_sync(d)
                if report:
                    generated.append(d)
                    logger.info("已补生成日报: %s", d)
                else:
                    logger.warning("补生成日报失败（无数据或 LLM 不可用）: %s", d)
            except Exception:
                logger.exception("补生成日报异常: %s", d)

        return generated

    # ==================== 辅助方法 ====================

    def _sessions_to_context(self, sessions) -> list[dict]:
        """将会话记录转换为 Prompt 上下文格式"""
        result = []
        for s in sessions:
            session_dict = {
                "start_time": s.start_time,
                "end_time": s.end_time or "",
                "process_name": s.process_name,
                "window_title": s.window_title or "",
                "text_segments": [],
                "clipboard_items": [],
            }

            # 查询文本片段
            segments = self._db.query_text_segments(s.id)
            for seg in segments:
                session_dict["text_segments"].append({
                    "text": seg.raw_text,
                    "source": seg.source,
                    "is_filtered": seg.is_filtered,
                })

            result.append(session_dict)
        return result

    @staticmethod
    def _summarize_raw_data(data: dict) -> str:
        """生成原始数据摘要（用于数据库存储）"""
        sessions = data.get("sessions", [])
        stats = data.get("app_usage_stats", [])
        total_sessions = len(sessions)
        total_apps = len(stats)
        return f"共 {total_sessions} 个会话，{total_apps} 个应用"
