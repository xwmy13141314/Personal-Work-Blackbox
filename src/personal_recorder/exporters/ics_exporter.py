from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from personal_recorder.repositories.event_repository import EventRepository


class ICSExporter:
    def __init__(self, repository: EventRepository):
        self.repository = repository

    def export_day(self, day: str, output_path: Path) -> Path:
        action_items = self.repository.list_action_items(day, day)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self._build_ics(action_items, day)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def _build_ics(self, action_items: list[dict], day: str) -> str:
        generated = datetime.now().strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Personal Recorder//EN",
        ]
        default_day = datetime.fromisoformat(f"{day}T09:00:00")

        for index, item in enumerate(action_items, start=1):
            due = item["due_date"] or day
            start_at = datetime.fromisoformat(f"{due}T09:00:00") + timedelta(hours=index - 1)
            end_at = start_at + timedelta(minutes=30)
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{item['id']}",
                    f"DTSTAMP:{generated}",
                    f"DTSTART:{start_at.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{end_at.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{item['title']}",
                    f"DESCRIPTION:{item['source_text']}",
                    "END:VEVENT",
                ]
            )

        if not action_items:
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    "UID:placeholder-no-actions",
                    f"DTSTAMP:{generated}",
                    f"DTSTART:{default_day.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{(default_day + timedelta(minutes=15)).strftime('%Y%m%dT%H%M%S')}",
                    "SUMMARY:No action items extracted",
                    "DESCRIPTION:Personal Recorder did not extract any calendar candidates for this day.",
                    "END:VEVENT",
                ]
            )

        lines.append("END:VCALENDAR")
        return "\n".join(lines)
