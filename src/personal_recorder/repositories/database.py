from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    app_name TEXT,
    window_title TEXT,
    content TEXT NOT NULL,
    content_redacted TEXT,
    content_summary TEXT,
    tags_json TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    importance_score REAL NOT NULL,
    project TEXT,
    storage_tier TEXT NOT NULL DEFAULT 'private',
    metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);

CREATE TABLE IF NOT EXISTS important_items (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    confidence REAL NOT NULL,
    UNIQUE(event_id, category),
    FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_text TEXT NOT NULL,
    UNIQUE(event_id, title),
    FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS daily_reports (
    report_date TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    week_start TEXT PRIMARY KEY,
    week_end TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        columns = set()
        for row in conn.execute("PRAGMA table_info(events)").fetchall():
            try:
                columns.add(row["name"])
            except (TypeError, IndexError, KeyError):
                columns.add(row[1])
        if "content_redacted" not in columns:
            conn.execute("ALTER TABLE events ADD COLUMN content_redacted TEXT")
        if "storage_tier" not in columns:
            conn.execute("ALTER TABLE events ADD COLUMN storage_tier TEXT NOT NULL DEFAULT 'private'")
        conn.execute(
            """
            UPDATE events
            SET content_redacted = COALESCE(content_redacted, content),
                storage_tier = COALESCE(storage_tier, 'private')
            WHERE content_redacted IS NULL OR storage_tier IS NULL
            """
        )
