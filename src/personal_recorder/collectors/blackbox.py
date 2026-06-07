from __future__ import annotations

from datetime import datetime


class BlackboxAdapter:
    def session_to_event(self, row: dict) -> dict:
        process_name = row.get("process_name") or "unknown"
        window_title = row.get("window_title") or ""
        active_seconds = row.get("active_seconds") or 0
        idle_seconds = row.get("idle_seconds") or 0
        content = (
            f"会话记录：{process_name} / {window_title}。"
            f"活跃 {active_seconds:.0f} 秒，空闲 {idle_seconds:.0f} 秒。"
        )
        return {
            "id": f"blackbox-session-{row['id']}",
            "source": "blackbox_session",
            "timestamp": row["start_time"],
            "app_name": process_name,
            "window_title": window_title,
            "content": content,
            "project": self._infer_project(window_title, process_name),
            "tags": ["blackbox", "session"],
            "metadata": {
                "origin_table": "sessions",
                "origin_id": row["id"],
                "end_time": row.get("end_time"),
                "idle_seconds": idle_seconds,
                "active_seconds": active_seconds,
                "is_filtered": row.get("is_filtered", 0),
            },
        }

    def text_segment_to_event(self, row: dict, session_map: dict[int, dict]) -> dict:
        session = session_map.get(row["session_id"], {})
        process_name = session.get("process_name") or "unknown"
        window_title = session.get("window_title") or ""
        source = row.get("source") or "keyboard"
        return {
            "id": f"blackbox-text-{row['id']}",
            "source": f"blackbox_{source}",
            "timestamp": row["timestamp"],
            "app_name": process_name,
            "window_title": window_title,
            "content": row["raw_text"],
            "project": self._infer_project(window_title, process_name),
            "tags": ["blackbox", source],
            "sensitivity": "high" if source == "keyboard" else "medium",
            "metadata": {
                "origin_table": "text_segments",
                "origin_id": row["id"],
                "origin_session_id": row["session_id"],
                "char_count": row.get("char_count"),
                "is_filtered": row.get("is_filtered", 0),
            },
        }

    def clipboard_to_event(self, row: dict) -> dict:
        process_name = row.get("source_process") or "unknown"
        window_title = row.get("source_window") or ""
        return {
            "id": f"blackbox-clipboard-{row['id']}",
            "source": "blackbox_clipboard",
            "timestamp": row["timestamp"],
            "app_name": process_name,
            "window_title": window_title,
            "content": row["content"],
            "project": self._infer_project(window_title, process_name),
            "tags": ["blackbox", "clipboard"],
            "sensitivity": "high",
            "metadata": {
                "origin_table": "clipboard_records",
                "origin_id": row["id"],
                "content_length": row.get("content_length"),
                "is_filtered": row.get("is_filtered", 0),
            },
        }

    def window_event_to_event(self, row: dict) -> dict:
        process_name = row.get("process_name") or "unknown"
        window_title = row.get("window_title") or ""
        event_type = row.get("event_type") or "switch"
        duration = row.get("duration_seconds") or 0
        content = f"窗口事件：{event_type}，应用 {process_name}，窗口 {window_title}，持续 {duration:.0f} 秒。"
        return {
            "id": f"blackbox-window-{row['id']}",
            "source": "blackbox_window",
            "timestamp": row["timestamp"],
            "app_name": process_name,
            "window_title": window_title,
            "content": content,
            "project": self._infer_project(window_title, process_name),
            "tags": ["blackbox", "window", event_type],
            "metadata": {
                "origin_table": "window_events",
                "origin_id": row["id"],
                "origin_session_id": row.get("session_id"),
                "duration_seconds": duration,
            },
        }

    def runtime_window_switch(
        self,
        from_process: str,
        from_title: str,
        to_process: str,
        to_title: str,
        duration_seconds: float,
        timestamp: datetime | None = None,
    ) -> dict:
        when = timestamp or datetime.now()
        return {
            "source": "blackbox_window",
            "timestamp": when.isoformat(timespec="seconds"),
            "app_name": to_process,
            "window_title": to_title,
            "content": (
                f"窗口从 {from_process}/{from_title} 切换到 {to_process}/{to_title}，"
                f"上一个窗口停留 {duration_seconds:.0f} 秒。"
            ),
            "project": self._infer_project(to_title, to_process),
            "tags": ["blackbox", "window", "switch"],
            "metadata": {
                "from_process": from_process,
                "from_title": from_title,
                "to_process": to_process,
                "to_title": to_title,
                "duration_seconds": duration_seconds,
            },
        }

    def runtime_clipboard(
        self,
        content: str,
        source_process: str = "",
        source_window: str = "",
        timestamp: datetime | None = None,
    ) -> dict:
        when = timestamp or datetime.now()
        return {
            "source": "blackbox_clipboard",
            "timestamp": when.isoformat(timespec="seconds"),
            "app_name": source_process,
            "window_title": source_window,
            "content": content,
            "project": self._infer_project(source_window, source_process),
            "tags": ["blackbox", "clipboard"],
            "sensitivity": "high",
            "metadata": {
                "runtime_source": "clipboard",
            },
        }

    def runtime_text(
        self,
        text: str,
        source: str = "keyboard",
        process_name: str = "",
        window_title: str = "",
        timestamp: datetime | None = None,
    ) -> dict:
        when = timestamp or datetime.now()
        return {
            "source": f"blackbox_{source}",
            "timestamp": when.isoformat(timespec="seconds"),
            "app_name": process_name,
            "window_title": window_title,
            "content": text,
            "project": self._infer_project(window_title, process_name),
            "tags": ["blackbox", source],
            "sensitivity": "high" if source == "keyboard" else "medium",
            "metadata": {
                "runtime_source": source,
            },
        }

    @staticmethod
    def _infer_project(window_title: str, process_name: str) -> str | None:
        text = f"{window_title} {process_name}".lower()
        if "cursor" in text or ".py" in text or ".md" in text:
            return "Development"
        if "figma" in text or "design" in text:
            return "Design"
        if "meeting" in text or "zoom" in text or "teams" in text:
            return "Meetings"
        return None
