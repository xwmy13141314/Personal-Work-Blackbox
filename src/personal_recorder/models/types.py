from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


@dataclass
class Event:
    source: str
    timestamp: datetime
    content: str
    content_redacted: str = ""
    app_name: str | None = None
    window_title: str | None = None
    tags: list[str] = field(default_factory=list)
    sensitivity: str = "medium"
    importance_score: float = 0.0
    content_summary: str | None = None
    project: str | None = None
    storage_tier: str = "private"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)

    @property
    def safe_content(self) -> str:
        return self.content_redacted or self.content


@dataclass
class ImportantItem:
    event_id: str
    date: str
    title: str
    summary: str
    category: str
    priority: str
    confidence: float
    id: str = field(default_factory=new_id)


@dataclass
class ActionItem:
    event_id: str
    title: str
    due_date: str | None
    status: str
    priority: str
    confidence: float
    source_text: str
    id: str = field(default_factory=new_id)
