from __future__ import annotations

import re

from personal_recorder.models.types import Event


IMPORTANT_PATTERNS = [
    r"上线",
    r"发布",
    r"客户",
    r"交付",
    r"汇报",
    r"会议",
    r"复盘",
    r"截止",
    r"修复",
    r"方案",
    r"风险",
    r"阻塞",
    r"明天",
    r"周[一二三四五六日天]",
    r"\d{1,2}:\d{2}",
]


class ImportanceRanker:
    def score(self, event: Event) -> float:
        score = 0.15
        text = f"{event.window_title or ''} {event.safe_content}"

        for pattern in IMPORTANT_PATTERNS:
            if re.search(pattern, text):
                score += 0.08

        if event.source == "manual":
            score += 0.25
        if event.source == "calendar":
            score += 0.2
        if event.source == "git":
            score += 0.18
        if event.project:
            score += 0.08
        if len(event.safe_content) >= 25:
            score += 0.08
        if any(tag in {"important", "todo", "meeting"} for tag in event.tags):
            score += 0.12
        if event.sensitivity == "high":
            score -= 0.05

        return max(0.0, min(score, 0.99))

    @staticmethod
    def to_priority(score: float) -> str:
        if score >= 0.8:
            return "high"
        if score >= 0.55:
            return "medium"
        return "low"
