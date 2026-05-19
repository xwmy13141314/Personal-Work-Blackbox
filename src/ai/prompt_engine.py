"""Prompt 模板引擎 — 管理和渲染 AI 摘要所需的提示词"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 内置的日报 Prompt（当外部模板文件不存在时使用）
BUILTIN_SYSTEM_PROMPT = """你是一个个人工作日志分析助手。你的任务是分析用户一天的电脑活动记录，生成结构化的工作日报。

规则：
1. 基于实际记录的窗口活动、输入内容和剪贴板数据生成报告
2. 不要编造未记录的信息
3. 对于无法确定的内容，标注"（信息不足）"
4. 敏感信息（标记为 [FILTERED_*]）不要尝试还原
5. 使用简洁的中文
6. 输出 Markdown 格式"""

BUILTIN_USER_TEMPLATE = """请分析以下今日活动记录，生成工作日报：

## 今日应用使用统计
{app_usage_stats}

## 活动时间线
{activity_timeline}

## 输入内容摘要
{text_segments_summary}

## 剪贴板记录
{clipboard_records}

请生成包含以下部分的日报：
1. **今日概览**（一段话总结今天做了什么，不超过 3 句话）
2. **已完成事项**（按重要程度排序，每项一句话说明）
3. **沟通结论**（从聊天和沟通工具中提取的关键决策和结论）
4. **待办跟进**（尚未完成的任务或需要后续跟进的事项）
5. **时间分布分析**（各类工作的时间占比和效率评估）"""

BUILTIN_WEEKLY_SYSTEM_PROMPT = """你是一个个人工作周报分析助手。你的任务是分析用户一周的活动记录汇总，生成结构化的周报。

规则：
1. 基于实际的每日活动汇总数据生成周报
2. 不要编造未记录的信息
3. 使用简洁的中文
4. 输出 Markdown 格式
5. 重点关注：本周完成的关键事项、跨日持续进展的任务、效率趋势"""

BUILTIN_WEEKLY_USER_TEMPLATE = """请分析以下本周活动汇总，生成工作周报：

## 本周每日概要
{daily_summaries}

## 本周应用使用统计
{weekly_app_stats}

请生成包含以下部分的周报：
1. **本周概览**（一段话总结本周工作重心）
2. **关键成果**（本周完成的重要事项）
3. **进行中事项**（跨周持续进行的任务）
4. **下周计划建议**（基于本周待办和进展建议下周重点）
5. **效率分析**（时间利用情况和改进建议）"""


class PromptEngine:
    """Prompt 模板引擎

    职责：
    1. 加载和管理 Prompt 模板（YAML 文件或内置模板）
    2. 将活动数据渲染为最终的 Prompt 文本
    """

    def __init__(self, template_dir: str | Path | None = None):
        self._template_dir = Path(template_dir) if template_dir else None
        self._daily_system = BUILTIN_SYSTEM_PROMPT
        self._daily_user = BUILTIN_USER_TEMPLATE
        self._weekly_system = BUILTIN_WEEKLY_SYSTEM_PROMPT
        self._weekly_user = BUILTIN_WEEKLY_USER_TEMPLATE
        self._load_templates()

    def _load_templates(self):
        """尝试从文件加载自定义模板"""
        if not self._template_dir or not self._template_dir.exists():
            return

        daily_file = self._template_dir / "daily_report.yaml"
        if daily_file.exists():
            try:
                with open(daily_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data.get("system_prompt"):
                    self._daily_system = data["system_prompt"]
                if data.get("user_prompt_template"):
                    self._daily_user = data["user_prompt_template"]
                logger.info("已加载自定义日报模板: %s", daily_file)
            except Exception:
                logger.exception("加载日报模板失败，使用内置模板")

        weekly_file = self._template_dir / "weekly_report.yaml"
        if weekly_file.exists():
            try:
                with open(weekly_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data.get("system_prompt"):
                    self._weekly_system = data["system_prompt"]
                if data.get("user_prompt_template"):
                    self._weekly_user = data["user_prompt_template"]
                logger.info("已加载自定义周报模板: %s", weekly_file)
            except Exception:
                logger.exception("加载周报模板失败，使用内置模板")

    def build_daily_prompt(self, data: dict[str, Any]) -> list[dict[str, str]]:
        """构建日报 Prompt

        Args:
            data: 包含以下键的字典:
                - app_usage_stats: 应用使用统计列表
                - sessions: 会话列表（含文本片段和剪贴板）
                - date: 日期字符串

        Returns:
            消息列表 [{"role": "system"|"user", "content": "..."}]
        """
        app_stats_text = self._format_app_stats(data.get("app_usage_stats", []))
        timeline_text = self._format_timeline(data.get("sessions", []))
        text_summary = self._format_text_summary(data.get("sessions", []))
        clipboard_text = self._format_clipboard(data.get("sessions", []))

        user_content = self._daily_user.format(
            app_usage_stats=app_stats_text,
            activity_timeline=timeline_text,
            text_segments_summary=text_summary,
            clipboard_records=clipboard_text,
        )

        return [
            {"role": "system", "content": self._daily_system},
            {"role": "user", "content": user_content},
        ]

    def build_weekly_prompt(self, daily_reports: list[dict]) -> list[dict[str, str]]:
        """构建周报 Prompt"""
        summaries = []
        for report in daily_reports:
            date = report.get("date", "unknown")
            content = report.get("structured_report", "")
            summaries.append(f"### {date}\n{content}\n")

        user_content = self._weekly_user.format(
            daily_summaries="\n".join(summaries),
            weekly_app_stats="（见各日报中的统计数据）",
        )

        return [
            {"role": "system", "content": self._weekly_system},
            {"role": "user", "content": user_content},
        ]

    # ==================== 格式化方法 ====================

    @staticmethod
    def _format_app_stats(stats: list[dict]) -> str:
        """格式化应用使用统计"""
        if not stats:
            return "（无数据）"

        lines = ["| 应用 | 活跃时长 | 会话数 |", "|------|---------|--------|"]
        for s in stats[:15]:
            process = s.get("process_name", "unknown")
            active = s.get("active_seconds", 0)
            hours = int(active // 3600)
            minutes = int((active % 3600) // 60)
            duration = f"{hours}h {minutes:02d}m" if hours > 0 else f"{minutes}m"
            count = s.get("session_count", 0)
            lines.append(f"| {process} | {duration} | {count} |")

        total = sum(s.get("active_seconds", 0) for s in stats)
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        lines.append(f"\n**总活跃时间：** {hours}h {minutes:02d}m")

        return "\n".join(lines)

    @staticmethod
    def _format_timeline(sessions: list[dict]) -> str:
        """格式化活动时间线"""
        if not sessions:
            return "（无数据）"

        lines = []
        for s in sessions[:50]:  # 最多 50 条
            start = s.get("start_time", "")
            end = s.get("end_time", "")
            start_short = start[11:16] if len(start) >= 16 else "?"
            end_short = end[11:16] if len(end) >= 16 else "?"

            process = s.get("process_name", "")
            title = s.get("window_title", "")
            lines.append(f"- **{start_short}-{end_short}** | {process} | {title}")

        return "\n".join(lines)

    @staticmethod
    def _format_text_summary(sessions: list[dict]) -> str:
        """格式化输入内容摘要"""
        segments = []
        for s in sessions:
            for seg in s.get("text_segments", []):
                text = seg.get("text", "")
                if text and len(text) > 2:
                    source = seg.get("source", "keyboard")
                    segments.append(f"[{source}] {text[:200]}")

        if not segments:
            return "（无文本输入记录）"

        return "\n".join(segments[:100])

    @staticmethod
    def _format_clipboard(sessions: list[dict]) -> str:
        """格式化剪贴板记录"""
        items = []
        for s in sessions:
            for item in s.get("clipboard_items", []):
                text = item.get("text", "")
                if text:
                    items.append(f"- {text[:200]}")

        if not items:
            return "（无剪贴板记录）"

        return "\n".join(items[:50])
