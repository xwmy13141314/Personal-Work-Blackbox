from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from personal_recorder.models.types import ActionItem, Event, ImportantItem
from personal_recorder.repositories.database import Database


class EventRepository:
    def __init__(self, database: Database):
        self.database = database

    def add_event(self, event: Event) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    id, source, timestamp, app_name, window_title, content,
                    content_redacted, content_summary, tags_json, sensitivity,
                    importance_score, project, storage_tier, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.source,
                    event.timestamp.isoformat(timespec="seconds"),
                    event.app_name,
                    event.window_title,
                    event.content,
                    event.content_redacted,
                    event.content_summary,
                    json.dumps(event.tags, ensure_ascii=False),
                    event.sensitivity,
                    event.importance_score,
                    event.project,
                    event.storage_tier,
                    json.dumps(event.metadata, ensure_ascii=False),
                ),
            )

    def add_important_items(self, items: Iterable[ImportantItem]) -> None:
        with self.database.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO important_items (
                    id, event_id, date, title, summary, category, priority, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.id,
                        item.event_id,
                        item.date,
                        item.title,
                        item.summary,
                        item.category,
                        item.priority,
                        item.confidence,
                    )
                    for item in items
                ],
            )

    def add_action_items(self, items: Iterable[ActionItem]) -> None:
        with self.database.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO action_items (
                    id, event_id, title, due_date, status, priority, confidence, source_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.id,
                        item.event_id,
                        item.title,
                        item.due_date,
                        item.status,
                        item.priority,
                        item.confidence,
                        item.source_text,
                    )
                    for item in items
                ],
            )

    def list_events_for_day(self, day: str) -> list[dict]:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59"
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
                """,
                (start, end),
            ).fetchall()
        return [self._row_to_event_dict(row) for row in rows]

    def list_events_between(self, start_day: str, end_day: str) -> list[dict]:
        start = f"{start_day}T00:00:00"
        end = f"{end_day}T23:59:59"
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
                """,
                (start, end),
            ).fetchall()
        return [self._row_to_event_dict(row) for row in rows]

    def list_important_items_for_day(self, day: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM important_items
                WHERE date = ?
                ORDER BY confidence DESC, priority ASC
                """,
                (day,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_action_items(self, start_day: str, end_day: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT ai.*, e.timestamp FROM action_items ai
                JOIN events e ON e.id = ai.event_id
                WHERE substr(e.timestamp, 1, 10) BETWEEN ? AND ?
                ORDER BY COALESCE(ai.due_date, ''), ai.priority
                """,
                (start_day, end_day),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_daily_report(self, report_date: str, content: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_reports (report_date, content, created_at)
                VALUES (?, ?, ?)
                """,
                (report_date, content, datetime.now().isoformat(timespec="seconds")),
            )

    def save_weekly_report(self, week_start: str, week_end: str, content: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO weekly_reports (week_start, week_end, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (week_start, week_end, content, datetime.now().isoformat(timespec="seconds")),
            )

    @staticmethod
    def _row_to_event_dict(row) -> dict:
        data = dict(row)
        data["tags"] = json.loads(data.pop("tags_json"))
        data["metadata"] = json.loads(data.pop("metadata_json"))
        return data
