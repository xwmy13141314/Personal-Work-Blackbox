from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from personal_recorder.repositories.event_repository import EventRepository


class ReportGenerator:
    def __init__(self, repository: EventRepository):
        self.repository = repository

    def build_daily_report(self, report_date: str) -> str:
        events = self.repository.list_events_for_day(report_date)
        important_items = self.repository.list_important_items_for_day(report_date)
        actions = self.repository.list_action_items(report_date, report_date)

        by_project = defaultdict(int)
        for event in events:
            by_project[event.get("project") or "未分类"] += 1

        completed = [item for item in important_items if item["category"] == "achievement"]
        risks = [item for item in important_items if item["category"] == "risk"]
        todos = [item for item in important_items if item["category"] == "todo"]

        lines = [f"# 日报 {report_date}", "", "## 今日重点"]
        lines.extend(self._bulletize([item["title"] for item in important_items[:8]], "今天没有提取到重点事项。"))
        lines.extend(["", "## 完成事项"])
        lines.extend(self._bulletize([item["title"] for item in completed], "暂无明显完成事项。"))
        lines.extend(["", "## 进行中与待办"])
        lines.extend(self._bulletize([item["title"] for item in actions[:10]], "暂无待办。"))
        lines.extend(["", "## 风险与提醒"])
        lines.extend(self._bulletize([item["title"] for item in risks + todos], "暂无明显风险。"))
        lines.extend(["", "## 项目分布"])
        lines.extend(
            self._bulletize(
                [f"{project}: {count} 条事件" for project, count in sorted(by_project.items(), key=lambda item: item[1], reverse=True)],
                "暂无项目数据。",
            )
        )
        return "\n".join(lines)

    def build_weekly_report(self, week_start: str) -> tuple[str, str]:
        start_date = date.fromisoformat(week_start)
        end_date = start_date + timedelta(days=6)
        events = self.repository.list_events_between(week_start, end_date.isoformat())
        actions = self.repository.list_action_items(week_start, end_date.isoformat())

        project_counter = Counter()
        source_counter = Counter()
        high_importance = []

        for event in events:
            project_counter[event.get("project") or "未分类"] += 1
            source_counter[event["source"]] += 1
            if event["importance_score"] >= 0.7:
                high_importance.append(event)

        lines = [f"# 周报 {week_start} ~ {end_date.isoformat()}", "", "## 本周主要成果与重点"]
        lines.extend(self._bulletize([event["content_summary"] for event in high_importance[:12]], "本周暂无高优先级记录。"))
        lines.extend(["", "## 按项目汇总"])
        lines.extend(self._bulletize([f"{project}: {count} 条事件" for project, count in project_counter.most_common()], "暂无项目数据。"))
        lines.extend(["", "## 本周待办与承诺"])
        lines.extend(self._bulletize([item["title"] for item in actions[:15]], "暂无待办。"))
        lines.extend(["", "## 行为分析"])
        lines.extend(self._bulletize([f"{source}: {count} 条事件" for source, count in source_counter.most_common()], "暂无行为数据。"))
        restricted_count = sum(1 for event in events if event.get("storage_tier") == "restricted")
        lines.extend(["", "## 隐私概览"])
        lines.extend(self._bulletize([f"受限事件: {restricted_count} 条"], "暂无隐私数据。"))
        return end_date.isoformat(), "\n".join(lines)

    @staticmethod
    def _bulletize(items: list[str], empty_text: str) -> list[str]:
        if not items:
            return [f"- {empty_text}"]
        return [f"- {item}" for item in items]
