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

        # 调用 LLM
        logger.info("正在调用 LLM 生成日报（%s）...", target_date)
        try:
            report_content, model_used = await self._llm.complete(messages)
            logger.info("日报生成完成，使用模型: %s", model_used)
        except Exception:
            logger.exception("LLM 调用失败")
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

    async def generate_weekly_report(self, end_date: str | None = None) -> str | None:
        """生成周报（汇总过去 7 天的日报）"""
        end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        start = end - timedelta(days=6)

        daily_reports = []
        for i in range(7):
            d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            report = self._db.query_daily_report(d)
            if report:
                daily_reports.append({
                    "date": d,
                    "structured_report": report.structured_report,
                })

        if not daily_reports:
            logger.warning("过去 7 天无日报数据，跳过周报生成")
            return None

        messages = self._prompt.build_weekly_prompt(daily_reports)

        try:
            report_content, model_used = await self._llm.complete(messages)
            logger.info("周报生成完成，使用模型: %s", model_used)
            return report_content
        except Exception:
            logger.exception("周报生成失败")
            return None

    def generate_sync(self, date: str | None = None) -> str | None:
        """同步版本的日报生成（便于在非异步上下文中调用）"""
        return asyncio.run(self.generate_daily_report(date))

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
