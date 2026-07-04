"""Markdown 日志导出器"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .database import Database

logger = logging.getLogger(__name__)


def _format_duration(seconds: float) -> str:
    """将秒数格式化为 Xh Ym 格式"""
    if seconds < 60:
        return f"{int(seconds)}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


class MarkdownExporter:
    """每日 Markdown 日志导出器"""

    def __init__(self, db: Database, export_dir: str | Path):
        self._db = db
        self._export_dir = Path(export_dir)

    def export_daily(self, date: str | None = None) -> Path:
        """导出指定日期的日志为 Markdown 文件

        Args:
            date: 日期字符串 YYYY-MM-DD，默认为今天

        Returns:
            导出的文件路径
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        self._export_dir.mkdir(parents=True, exist_ok=True)

        # 查询数据
        sessions = self._db.query_sessions(date=target_date)
        app_stats = self._db.query_app_usage_stats(date=target_date)

        if not sessions:
            logger.info("日期 %s 无数据，跳过导出", target_date)
            return self._export_dir / f"{target_date}.md"

        # 生成 Markdown
        md = self._build_markdown(target_date, sessions, app_stats)

        # 写入文件
        output_path = self._export_dir / f"{target_date}.md"
        output_path.write_text(md, encoding="utf-8")
        logger.info("日志已导出: %s", output_path)
        return output_path

    def _build_markdown(self, date: str, sessions: list, app_stats: list) -> str:
        """构建 Markdown 内容"""
        lines: list[str] = []

        # 标题
        dt = datetime.strptime(date, "%Y-%m-%d")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[dt.weekday()]
        lines.append(f"# 工作日志 - {date}（{weekday}）\n")

        # 今日概览
        lines.append("## 今日概览\n")
        total_active = sum(s["active_seconds"] for s in app_stats)
        total_idle = sum(s["idle_seconds"] for s in app_stats)

        lines.append("| 应用 | 活跃时长 | 会话数 |")
        lines.append("|------|---------|--------|")
        for stat in app_stats[:10]:  # 只显示前 10 个
            process = stat["process_name"] or "unknown"
            duration = _format_duration(stat["active_seconds"])
            count = stat["session_count"]
            lines.append(f"| {process} | {duration} | {count} |")

        lines.append(f"\n**总活跃时间：** {_format_duration(total_active)}  ")
        lines.append(f"**空闲/休息：** {_format_duration(total_idle)}\n")
        lines.append("---\n")

        # 活动时间线
        lines.append("## 活动时间线\n")

        for session in sessions:
            start = session.start_time
            if isinstance(start, str) and len(start) >= 16:
                start_short = start[11:16]
            else:
                start_short = "?"

            end = session.end_time
            if isinstance(end, str) and len(end) >= 16:
                end_short = end[11:16]
            else:
                end_short = "?"

            process = session.process_name or "unknown"
            title = session.window_title or ""
            duration = _format_duration(session.active_seconds)

            lines.append(f"### {start_short} - {end_short} | {process} | {duration}")
            if title:
                lines.append(f"**{title}**\n")

            # 文本片段
            segments = self._db.query_text_segments(session.id)
            for seg in segments:
                if seg.source == "clipboard":
                    lines.append(f"> [剪贴板] {seg.raw_text[:200]}")
                else:
                    lines.append(f"> {seg.raw_text[:200]}")

            lines.append("")

        return "\n".join(lines)
