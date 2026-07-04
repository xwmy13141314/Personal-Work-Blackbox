from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_recorder.collectors.blackbox import BlackboxAdapter
from personal_recorder.services.pipeline import ProcessingPipeline


class BlackboxImporter:
    def __init__(self, pipeline: ProcessingPipeline):
        self.pipeline = pipeline
        self.adapter = BlackboxAdapter()

    def import_sqlite(self, db_path: Path, include_sessions: bool = True) -> dict[str, int]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            session_rows = [dict(row) for row in conn.execute("SELECT * FROM sessions ORDER BY start_time ASC")]
            session_map = {row["id"]: row for row in session_rows}

            imported = {
                "sessions": 0,
                "text_segments": 0,
                "clipboard_records": 0,
                "window_events": 0,
            }

            if include_sessions:
                for row in session_rows:
                    self.pipeline.ingest(self.adapter.session_to_event(row))
                    imported["sessions"] += 1

            for row in conn.execute("SELECT * FROM text_segments ORDER BY timestamp ASC"):
                self.pipeline.ingest(self.adapter.text_segment_to_event(dict(row), session_map))
                imported["text_segments"] += 1

            for row in conn.execute("SELECT * FROM clipboard_records ORDER BY timestamp ASC"):
                self.pipeline.ingest(self.adapter.clipboard_to_event(dict(row)))
                imported["clipboard_records"] += 1

            for row in conn.execute("SELECT * FROM window_events ORDER BY timestamp ASC"):
                self.pipeline.ingest(self.adapter.window_event_to_event(dict(row)))
                imported["window_events"] += 1

            return imported
        finally:
            conn.close()
