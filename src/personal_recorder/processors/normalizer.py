from __future__ import annotations

from datetime import datetime

from personal_recorder.models.types import Event
from personal_recorder.processors.privacy_filter import PrivacyFilter


class EventNormalizer:
    def __init__(self) -> None:
        self.privacy_filter = PrivacyFilter()

    def normalize(self, raw: dict) -> Event:
        timestamp = raw.get("timestamp")
        if isinstance(timestamp, str):
            parsed_timestamp = datetime.fromisoformat(timestamp)
        elif isinstance(timestamp, datetime):
            parsed_timestamp = timestamp
        else:
            raise ValueError("raw event must provide ISO timestamp")

        content = (raw.get("content") or "").strip()
        if not content:
            raise ValueError("raw event content cannot be empty")

        redacted_content = self.privacy_filter.redact(content)

        event = Event(
            source=raw.get("source", "manual"),
            timestamp=parsed_timestamp,
            app_name=raw.get("app_name"),
            window_title=raw.get("window_title"),
            content=content,
            content_redacted=redacted_content,
            content_summary=self._build_summary(redacted_content),
            tags=self._normalize_tags(raw.get("tags", [])),
            sensitivity=raw.get("sensitivity", "medium"),
            project=raw.get("project"),
            storage_tier=raw.get("storage_tier") or self.privacy_filter.detect_storage_tier(content, raw.get("sensitivity", "medium")),
            metadata=raw.get("metadata", {}),
        )
        if raw.get("id"):
            event.id = raw["id"]
        return event

    @staticmethod
    def _build_summary(content: str) -> str:
        return content.replace("\n", " ").strip()[:120]

    @staticmethod
    def _normalize_tags(tags: list[str] | str) -> list[str]:
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",")]
        return [tag for tag in tags if tag]
