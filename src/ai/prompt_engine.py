"""Prompt 模板引擎 — 管理和渲染 AI 摘要所需的提示词"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ==================== 日报 Prompt ====================

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

# ==================== 周报 Prompt ====================

BUILTIN_WEEKLY_SYSTEM_PROMPT = """你是一个个人工作周报分析助手。你的任务是分析用户一周的活动记录汇总，生成结构化的周报。

规则：
1. 基于实际的每日活动汇总数据生成周报
2. 不要编造未记录的信息
3. 使用简洁的中文
4. 输出 Markdown 格式
5. 重点关注：本周完成的关键事项、跨日持续进展的任务、效率趋势"""

BUILTIN_WEEKLY_USER_TEMPLATE = """请分析以下本周活动汇总，生成工作周报：

## 报告周期
{period_range}

## 出勤情况
共有 {total_days} 天有数据，本报告覆盖 {report_days} 天。
{missing_days_info}

## 本周每日概要
{daily_summaries}

## 本周应用使用统计
{weekly_app_stats}

请生成包含以下部分的周报：
1. **本周概览**（一段话总结本周工作重心，不超过 3 句话）
2. **关键成果**（本周完成的重要事项，按重要度排序）
3. **进行中事项**（跨周持续进行的任务）
4. **下周计划建议**（基于本周待办和进展建议下周重点）
5. **效率分析**（时间利用情况和改进建议）"""

# ==================== 月报 Prompt ====================

BUILTIN_MONTHLY_SYSTEM_PROMPT = """你是一个个人工作月报分析助手。你的任务是分析用户一个月的活动记录汇总，生成结构化的月报。

规则：
1. 基于实际的每日活动汇总数据生成月报
2. 不要编造未记录的信息
3. 使用简洁的中文
4. 输出 Markdown 格式
5. 重点关注：月度目标完成度、长期趋势、按周工作分布"""

BUILTIN_MONTHLY_USER_TEMPLATE = """请分析以下本月活动汇总，生成工作月报：

## 报告周期
{period_range}

## 出勤情况
本月共有 {total_days} 天有数据，本报告覆盖 {report_days} 天。
{missing_days_info}

## 本月每日概要
{daily_summaries}

## 本月应用使用统计
{monthly_app_stats}

请生成包含以下部分的月报：
1. **本月概览**（一段话总结本月工作重心和整体表现，不超过 3 句话）
2. **关键成果与里程碑**（本月完成的重要事项和阶段性成果）
3. **按周工作分布**（将本月按自然周划分，概括每周的工作重点）
4. **效率趋势分析**（本月时间投入变化、各类工作占比趋势）
5. **下月计划建议**（基于本月待办和进展建议下月重点）"""


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
        self._monthly_system = BUILTIN_MONTHLY_SYSTEM_PROMPT
        self._monthly_user = BUILTIN_MONTHLY_USER_TEMPLATE
        self._load_templates()

    def _load_templates(self):
        """尝试从文件加载自定义模板"""
        if not self._template_dir or not self._template_dir.exists():
            return

        for name, sys_attr, user_attr in [
            ("daily_report.yaml", "_daily_system", "_daily_user"),
            ("weekly_report.yaml", "_weekly_system", "_weekly_user"),
            ("monthly_report.yaml", "_monthly_system", "_monthly_user"),
        ]:
            filepath = self._template_dir / name
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if data.get("system_prompt"):
                        setattr(self, sys_attr, data["system_prompt"])
                    if data.get("user_prompt_template"):
                        setattr(self, user_attr, data["user_prompt_template"])
                    logger.info("已加载自定义模板: %s", filepath)
                except Exception:
                    logger.exception("加载模板 %s 失败，使用内置模板", name)

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

    def build_weekly_prompt(self, data: dict[str, Any]) -> list[dict[str, str]]:
        """构建周报 Prompt

        Args:
            data: 包含以下键的字典:
                - daily_reports: 已有日报列表 [{"date": str, "structured_report": str}]
                - app_usage_stats: 跨日应用使用统计
                - period_start: 周一日期
                - period_end: 周日日期
                - total_days: 该周总天数 (7)
                - report_days: 有日报的天数
                - missing_dates: 缺日报的日期列表

        Returns:
            消息列表 [{"role": "system"|"user", "content": "..."}]
        """
        summaries = []
        for report in data.get("daily_reports", []):
            date = report.get("date", "unknown")
            content = report.get("structured_report", "")
            summaries.append(f"### {date}\n{content}\n")

        missing_dates = data.get("missing_dates", [])
        missing_info = ""
        if missing_dates:
            missing_info = f"缺少日报的日期: {', '.join(missing_dates)}"

        user_content = self._weekly_user.format(
            period_range=f"{data.get('period_start', '')} ~ {data.get('period_end', '')}",
            total_days=data.get("total_days", 7),
            report_days=data.get("report_days", 0),
            missing_days_info=missing_info,
            daily_summaries="\n".join(summaries) if summaries else "（无日报数据）",
            weekly_app_stats=self._format_app_stats(data.get("app_usage_stats", [])),
        )

        return [
            {"role": "system", "content": self._weekly_system},
            {"role": "user", "content": user_content},
        ]

    def build_monthly_prompt(self, data: dict[str, Any]) -> list[dict[str, str]]:
        """构建月报 Prompt

        Args:
            data: 包含以下键的字典:
                - daily_reports: 已有日报列表
                - app_usage_stats: 跨日应用使用统计
                - period_start: 月初日期
                - period_end: 月末日期
                - total_days: 该月总天数
                - report_days: 有日报的天数
                - missing_dates: 缺日报的日期列表

        Returns:
            消息列表 [{"role": "system"|"user", "content": "..."}]
        """
        summaries = []
        for report in data.get("daily_reports", []):
            date = report.get("date", "unknown")
            content = report.get("structured_report", "")
            summaries.append(f"### {date}\n{content}\n")

        missing_dates = data.get("missing_dates", [])
        missing_info = ""
        if missing_dates:
            missing_info = f"缺少日报的日期: {', '.join(missing_dates[:10])}"
            if len(missing_dates) > 10:
                missing_info += f" 等 {len(missing_dates)} 天"

        user_content = self._monthly_user.format(
            period_range=f"{data.get('period_start', '')} ~ {data.get('period_end', '')}",
            total_days=data.get("total_days", 30),
            report_days=data.get("report_days", 0),
            missing_days_info=missing_info,
            daily_summaries="\n".join(summaries) if summaries else "（无日报数据）",
            monthly_app_stats=self._format_app_stats(data.get("app_usage_stats", [])),
        )

        return [
            {"role": "system", "content": self._monthly_system},
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
