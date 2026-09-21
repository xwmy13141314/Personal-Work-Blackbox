"""报告生成器 — 从数据库读取数据、构建 Prompt、调用 LLM、持久化报告"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
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

    # ==================== 周度洞察（v5.1） ====================

    _INSIGHT_TYPE_TITLES = {
        "best_time": "最佳工作时段",
        "warning": "需要注意",
        "wow": "周环比",
        "goal": "目标达成",
    }

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h{m:02d}m" if h > 0 else f"{m}m"

    def _local_weekly_insights(self, stats: dict) -> list[dict]:
        """本地规则计算洞察（LLM 失败/不可用时的兜底）"""
        insights: list[dict] = []

        # 最佳工作时段：活跃时长最高的连续 2 小时窗口
        hourly = {h["hour"]: h["active_seconds"] for h in stats["week_hourly"]}
        if hourly:
            best_win, best_val = None, 0.0
            hours_sorted = sorted(hourly)
            for i in range(len(hours_sorted) - 1):
                h1, h2 = hours_sorted[i], hours_sorted[i + 1]
                if h2 == h1 + 1:
                    v = hourly[h1] + hourly[h2]
                    if v > best_val:
                        best_val, best_win = v, (h1, h2)
            if best_win and best_val >= 3600:
                h1, h2 = best_win
                if h1 < 11:
                    span = f"上午 {h1}-{h2 + 1} 点"
                elif h1 < 13:
                    span = f"中午 {h1}-{h2 + 1} 点"
                elif h1 < 18:
                    span = f"下午 {h1}-{h2 + 1} 点"
                else:
                    span = f"晚上 {h1}-{h2 + 1} 点"
                insights.append({
                    "type": "best_time", "title": "最佳工作时段",
                    "body": f"{span}效率最高（合计 {self._fmt_duration(best_val)}），建议把核心任务安排在这个时段。",
                })

        # 周环比（日均按有数据天数算，避免周中生成时误报）
        if stats["week_daily_avg"] > 0 and stats["last_week_daily_avg"] > 0:
            delta = (stats["week_daily_avg"] - stats["last_week_daily_avg"]) / stats["last_week_daily_avg"] * 100
            trend = "增长" if delta >= 0 else "下降"
            suffix = "（本周数据尚不完整）" if stats["week_days"] < 3 else ""
            insights.append({
                "type": "wow", "title": "周环比",
                "body": f"本周日均活跃 {self._fmt_duration(stats['week_daily_avg'])}，较上周{trend} {abs(delta):.0f}%。{suffix}",
            })

        # 娱乐占比预警
        if stats["entertainment_ratio"] >= 0.3:
            insights.append({
                "type": "warning", "title": "娱乐占比偏高",
                "body": f"本周娱乐类活动占比 {int(stats['entertainment_ratio'] * 100)}%，建议控制在 30% 以内以保障产出。",
            })

        # 连续工作天数
        if stats["streak_days"] >= 6:
            insights.append({
                "type": "warning", "title": "注意休息",
                "body": f"已连续 {stats['streak_days']} 天有工作记录，建议安排适当休息调整。",
            })

        # 目标达成
        if stats["week_days"] > 0:
            goal_h = stats["daily_goal_minutes"] // 60
            insights.append({
                "type": "goal", "title": "目标达成",
                "body": f"本周目标 {goal_h}h/天，实际达标 {stats['goal_hit_days']}/{stats['week_days']} 天有数据。",
            })

        return insights

    async def generate_weekly_insights(
        self, date: str | None = None, daily_goal_minutes: int = 480
    ) -> dict | None:
        """生成周度洞察：LLM 优先（基于两周统计），失败时本地规则兜底

        Returns:
            {"week_label", "week_start", "week_end", "insights": [{type,title,body}],
             "source": "llm"|"local", "generated_at", "stats": {...}}
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        week_start, week_end = _week_range(target_date)
        label = _week_label(week_start)
        last_start = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        last_end = (datetime.strptime(week_end, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

        week_daily = self._db.query_daily_totals_range(week_start, week_end)
        last_daily = self._db.query_daily_totals_range(last_start, last_end)
        if not week_daily and not last_daily:
            logger.warning("周期 %s 无活动数据，跳过洞察生成", label)
            return None

        week_hourly = self._db.query_hourly_stats_range(week_start, week_end)
        week_cats = self._db.query_category_stats_range(week_start, week_end)
        last_cats = self._db.query_category_stats_range(last_start, last_end)

        # ===== 本地统计指标 =====
        week_total = sum(week_daily.values())
        last_total = sum(last_daily.values())
        week_days = len(week_daily)
        last_days = len(last_daily)
        # 日均按有数据天数算（周中生成时 7 天摊薄会严重失真）
        week_avg = week_total / week_days if week_days else 0.0
        last_avg = last_total / last_days if last_days else 0.0

        week_cat_total = sum(c.get("active_seconds", 0) for c in week_cats)
        ent_sec = sum(
            c.get("active_seconds", 0)
            for c in week_cats if "娱乐" in (c.get("category") or "")
        )
        ent_ratio = ent_sec / week_cat_total if week_cat_total > 0 else 0.0

        # 连续工作天数（从今天/昨天往回数有数据的天数）
        avail_dates = set(self._db.query_available_dates(limit=60))
        d = datetime.now()
        if d.strftime("%Y-%m-%d") not in avail_dates:
            d -= timedelta(days=1)
        streak = 0
        while d.strftime("%Y-%m-%d") in avail_dates:
            streak += 1
            d -= timedelta(days=1)

        goal_sec = daily_goal_minutes * 60
        goal_hit = sum(1 for v in week_daily.values() if v >= goal_sec)

        stats = {
            "week_hourly": week_hourly,
            "week_daily_avg": week_avg,
            "last_week_daily_avg": last_avg,
            "entertainment_ratio": ent_ratio,
            "streak_days": streak,
            "goal_hit_days": goal_hit,
            "week_days": week_days,
            "daily_goal_minutes": daily_goal_minutes,
        }
        insights = self._local_weekly_insights(stats)
        source = "local"

        # ===== LLM 增强（失败不阻断，已有本地兜底） =====
        try:
            def _fmt_daily(dd: dict) -> str:
                if not dd:
                    return "（无数据）"
                return ", ".join(
                    f"{k[5:]}: {self._fmt_duration(v)}" for k, v in sorted(dd.items())
                )

            def _fmt_hourly(hh: list) -> str:
                if not hh:
                    return "（无数据）"
                return ", ".join(
                    f"{h['hour']:02d}:00 {self._fmt_duration(h['active_seconds'])}" for h in hh
                )

            def _fmt_cats(cc: list) -> str:
                total = sum(c.get("active_seconds", 0) for c in cc)
                if total <= 0:
                    return "（无数据）"
                parts = []
                for c in cc[:8]:
                    pct = int(c.get("active_seconds", 0) / total * 100)
                    parts.append(f"{c.get('category', '?')} {pct}%")
                return ", ".join(parts)

            prompt_data = {
                "week_label": label,
                "week_start": week_start, "week_end": week_end,
                "week_daily": _fmt_daily(week_daily),
                "week_hourly": _fmt_hourly(week_hourly),
                "week_categories": _fmt_cats(week_cats),
                "week_days": week_days,
                "daily_goal_minutes": daily_goal_minutes,
                "goal_hit_days": goal_hit,
                "last_week_start": last_start, "last_week_end": last_end,
                "last_week_daily": _fmt_daily(last_daily),
                "last_week_categories": _fmt_cats(last_cats),
                "last_week_days": last_days,
            }
            messages = self._prompt.build_weekly_insight_prompt(prompt_data)
            content, _model = await self._llm.complete(messages)

            import json as _json
            from src.ai.todo_extractor import _strip_code_fence, _extract_json_array
            arr_text = _extract_json_array(_strip_code_fence(content.strip()))
            if arr_text:
                data = _json.loads(arr_text)
                if isinstance(data, list) and data:
                    parsed = []
                    for item in data:
                        if (
                            isinstance(item, dict)
                            and item.get("type") in self._INSIGHT_TYPE_TITLES
                            and str(item.get("body") or "").strip()
                        ):
                            parsed.append({
                                "type": item["type"],
                                "title": str(item.get("title") or "").strip()[:20]
                                or self._INSIGHT_TYPE_TITLES[item["type"]],
                                "body": str(item["body"]).strip(),
                            })
                    if parsed:
                        insights = parsed
                        source = "llm"
        except Exception:
            logger.exception("LLM 周度洞察生成失败，使用本地统计洞察")

        result = {
            "week_label": label,
            "week_start": week_start,
            "week_end": week_end,
            "insights": insights,
            "source": source,
            "generated_at": datetime.now().isoformat(),
            "stats": {
                "week_daily_avg_seconds": round(week_avg, 1),
                "last_week_daily_avg_seconds": round(last_avg, 1),
                "entertainment_ratio": round(ent_ratio, 3),
                "streak_days": streak,
                "goal_hit_days": goal_hit,
                "week_days": week_days,
            },
        }
        self._save_insights_cache(label, result)
        return result

    def generate_weekly_insights_sync(
        self, date: str | None = None, daily_goal_minutes: int = 480
    ) -> dict | None:
        """同步版本的周度洞察生成（工作线程调用）"""
        return asyncio.run(self.generate_weekly_insights(date, daily_goal_minutes))

    # ===== 洞察缓存（data/insights/weekly_YYYY-Www.json） =====

    def _insights_cache_path(self, label: str) -> Path:
        cache_dir = self._db._db_path.parent / "insights"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"weekly_{label}.json"

    def _save_insights_cache(self, label: str, result: dict) -> None:
        try:
            import json
            self._insights_cache_path(label).write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            logger.exception("洞察缓存写入失败")

    def get_weekly_insights(self, date: str | None = None) -> dict | None:
        """读取本周洞察缓存（无缓存返回 None，由前端触发 generate）"""
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        week_start, _ = _week_range(target_date)
        label = _week_label(week_start)
        p = self._insights_cache_path(label)
        try:
            if p.exists():
                import json
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("洞察缓存读取失败")
        return None

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
