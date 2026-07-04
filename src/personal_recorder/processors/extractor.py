from __future__ import annotations

import re
from datetime import datetime, timedelta

from personal_recorder.models.types import ActionItem, Event, ImportantItem
from personal_recorder.processors.ranker import ImportanceRanker


TODO_PATTERNS = [
    r"(?:需要|待|TODO|todo|跟进|补充|整理|安排|确认|提交|修复|完成)([^，。；\n]{2,40})",
]

DATE_PATTERNS = [
    (r"明天", 1),
    (r"后天", 2),
]

WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


class InsightExtractor:
    def __init__(self) -> None:
        self.ranker = ImportanceRanker()

    def extract_important_items(self, event: Event) -> list[ImportantItem]:
        score = event.importance_score
        if score < 0.45:
            return []

        text = event.safe_content

        return [
            ImportantItem(
                event_id=event.id,
                date=event.timestamp.date().isoformat(),
                title=self._build_title(event),
                summary=event.content_summary or text[:120],
                category=self._detect_category(text),
                priority=self.ranker.to_priority(score),
                confidence=min(0.95, score + 0.05),
            )
        ]

    def extract_action_items(self, event: Event) -> list[ActionItem]:
        items: list[ActionItem] = []
        text = event.safe_content
        due_date = self._extract_due_date(text, event.timestamp)
        priority = self.ranker.to_priority(event.importance_score)

        matched = False
        for pattern in TODO_PATTERNS:
            for match in re.finditer(pattern, text):
                title = self._clean_title(match.group(0))
                if len(title) < 4:
                    continue
                matched = True
                items.append(
                    ActionItem(
                        event_id=event.id,
                        title=title,
                        due_date=due_date,
                        status="open",
                        priority=priority,
                        confidence=min(0.93, event.importance_score + 0.08),
                        source_text=text[:200],
                    )
                )

        if not matched and due_date and event.importance_score >= 0.55:
            items.append(
                ActionItem(
                    event_id=event.id,
                    title=self._build_title(event),
                    due_date=due_date,
                    status="open",
                    priority=priority,
                    confidence=min(0.88, event.importance_score + 0.04),
                    source_text=text[:200],
                )
            )
        return items

    @staticmethod
    def _build_title(event: Event) -> str:
        if event.project:
            return f"[{event.project}] {event.content_summary}"
        return event.content_summary or event.safe_content[:40]

    @staticmethod
    def _detect_category(text: str) -> str:
        if any(word in text for word in ("风险", "阻塞", "问题")):
            return "risk"
        if any(word in text for word in ("明天", "待", "TODO", "跟进", "安排")):
            return "todo"
        if any(word in text for word in ("完成", "上线", "修复", "发布", "提交")):
            return "achievement"
        return "decision"

    @staticmethod
    def _clean_title(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip("，。；:： ")

    def _extract_due_date(self, text: str, base_time: datetime) -> str | None:
        for pattern, offset in DATE_PATTERNS:
            if re.search(pattern, text):
                return (base_time.date() + timedelta(days=offset)).isoformat()

        weekday_match = re.search(r"周([一二三四五六日天])", text)
        if weekday_match:
            weekday = WEEKDAY_MAP[weekday_match.group(1)]
            delta = (weekday - base_time.weekday()) % 7
            delta = 7 if delta == 0 else delta
            return (base_time.date() + timedelta(days=delta)).isoformat()

        explicit = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
        if explicit:
            return explicit.group(1)
        return None
