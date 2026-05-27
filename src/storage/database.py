"""SQLite 数据库操作封装"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from .models import (
    SessionRecord,
    TextSegmentRecord,
    ClipboardRecordModel,
    DailyReportRecord,
    PeriodReportRecord,
    WindowEventRecord,
)

logger = logging.getLogger(__name__)

# SQL 建表语句
SCHEMA_SQL = """
-- 应用会话表
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time    TEXT NOT NULL,
    end_time      TEXT,
    process_name  TEXT NOT NULL,
    window_title  TEXT,
    idle_seconds  REAL DEFAULT 0,
    active_seconds REAL DEFAULT 0,
    is_filtered   INTEGER DEFAULT 0
);

-- 窗口切换事件
CREATE TABLE IF NOT EXISTS window_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    process_name  TEXT,
    window_title  TEXT,
    duration_seconds REAL,
    session_id    INTEGER REFERENCES sessions(id)
);

-- 输入文本片段
CREATE TABLE IF NOT EXISTS text_segments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    timestamp     TEXT NOT NULL,
    raw_text      TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'keyboard',
    is_filtered   INTEGER DEFAULT 0,
    char_count    INTEGER DEFAULT 0
);

-- 剪贴板记录
CREATE TABLE IF NOT EXISTS clipboard_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    content        TEXT NOT NULL,
    content_length INTEGER NOT NULL,
    source_process TEXT,
    source_window  TEXT,
    is_filtered    INTEGER DEFAULT 0
);

-- AI 日报
CREATE TABLE IF NOT EXISTS daily_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date       TEXT NOT NULL UNIQUE,
    raw_data_summary  TEXT,
    structured_report TEXT NOT NULL,
    model_used        TEXT NOT NULL,
    generated_at      TEXT NOT NULL,
    format            TEXT DEFAULT 'markdown',
    token_count       INTEGER DEFAULT 0
);

-- AI 周报/月报
CREATE TABLE IF NOT EXISTS period_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type       TEXT NOT NULL,
    period_start      TEXT NOT NULL,
    period_end        TEXT NOT NULL,
    report_label      TEXT NOT NULL,
    structured_report TEXT NOT NULL,
    model_used        TEXT NOT NULL,
    generated_at      TEXT NOT NULL,
    format            TEXT DEFAULT 'markdown',
    token_count       INTEGER DEFAULT 0,
    UNIQUE(report_type, period_start)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_process ON sessions(process_name);
CREATE INDEX IF NOT EXISTS idx_window_events_timestamp ON window_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_text_segments_session ON text_segments(session_id);
CREATE INDEX IF NOT EXISTS idx_text_segments_timestamp ON text_segments(timestamp);
CREATE INDEX IF NOT EXISTS idx_clipboard_timestamp ON clipboard_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_reports_date ON daily_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_period_reports_type ON period_reports(report_type, period_start);
"""


class Database:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: str | Path, journal_mode: str = "WAL"):
        self._db_path = Path(db_path)
        self._journal_mode = journal_mode
        self._conn: sqlite3.Connection | None = None

    def initialize(self):
        """初始化数据库（建表）"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute(f"PRAGMA journal_mode={self._journal_mode}")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        logger.info("数据库已初始化: %s", self._db_path)

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭")

    @property
    def is_connected(self) -> bool:
        """数据库是否已连接"""
        return self._conn is not None

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """获取游标的上下文管理器"""
        if not self._conn:
            raise RuntimeError("数据库未初始化")
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()

    # ==================== 写入操作 ====================

    def insert_session(self, session: SessionRecord) -> int:
        """插入一条会话记录，返回自增 ID"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO sessions (start_time, end_time, process_name, window_title,
                   idle_seconds, active_seconds, is_filtered)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.start_time, session.end_time,
                    session.process_name, session.window_title,
                    session.idle_seconds, session.active_seconds,
                    int(session.is_filtered),
                ),
            )
            return cur.lastrowid

    def insert_text_segment(self, segment: TextSegmentRecord):
        """插入一条文本片段"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO text_segments (session_id, timestamp, raw_text, source,
                   is_filtered, char_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    segment.session_id, segment.timestamp,
                    segment.raw_text, segment.source,
                    int(segment.is_filtered), segment.char_count,
                ),
            )

    def insert_clipboard_record(self, record: ClipboardRecordModel):
        """插入一条剪贴板记录"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO clipboard_records (timestamp, content, content_length,
                   source_process, source_window, is_filtered)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp, record.content, record.content_length,
                    record.source_process, record.source_window,
                    int(record.is_filtered),
                ),
            )

    def insert_window_event(self, event: WindowEventRecord):
        """插入一条窗口事件"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO window_events (timestamp, event_type, process_name,
                   window_title, duration_seconds, session_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.timestamp, event.event_type,
                    event.process_name, event.window_title,
                    event.duration_seconds, event.session_id,
                ),
            )

    def insert_daily_report(self, report: DailyReportRecord):
        """插入或替换一条日报"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO daily_reports
                   (report_date, raw_data_summary, structured_report, model_used,
                    generated_at, format, token_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.report_date, report.raw_data_summary,
                    report.structured_report, report.model_used,
                    report.generated_at, report.format, report.token_count,
                ),
            )

    # ==================== 查询操作 ====================

    def query_sessions(
        self, date: str | None = None, process_name: str | None = None, limit: int = 100
    ) -> list[SessionRecord]:
        """查询会话记录"""
        conditions = []
        params: list = []

        if date:
            conditions.append("DATE(start_time) = ?")
            params.append(date)
        if process_name:
            conditions.append("process_name = ?")
            params.append(process_name)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT id, start_time, end_time, process_name, window_title,
                    idle_seconds, active_seconds, is_filtered
                    FROM sessions{where}
                    ORDER BY start_time DESC LIMIT ?""",
                params,
            )
            rows = cur.fetchall()

        return [
            SessionRecord(
                id=row[0], start_time=row[1], end_time=row[2],
                process_name=row[3], window_title=row[4],
                idle_seconds=row[5], active_seconds=row[6],
                is_filtered=bool(row[7]),
            )
            for row in rows
        ]

    def query_text_segments(self, session_id: int) -> list[TextSegmentRecord]:
        """查询某个会话的所有文本片段"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, session_id, timestamp, raw_text, source, is_filtered, char_count
                   FROM text_segments WHERE session_id = ? ORDER BY timestamp""",
                (session_id,),
            )
            rows = cur.fetchall()

        return [
            TextSegmentRecord(
                id=row[0], session_id=row[1], timestamp=row[2],
                raw_text=row[3], source=row[4],
                is_filtered=bool(row[5]), char_count=row[6],
            )
            for row in rows
        ]

    def query_daily_report(self, date: str) -> DailyReportRecord | None:
        """查询某天的日报"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, report_date, raw_data_summary, structured_report,
                   model_used, generated_at, format, token_count
                   FROM daily_reports WHERE report_date = ?""",
                (date,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return DailyReportRecord(
            id=row[0], report_date=row[1], raw_data_summary=row[2],
            structured_report=row[3], model_used=row[4],
            generated_at=row[5], format=row[6], token_count=row[7],
        )

    def query_app_usage_stats(self, date: str) -> list[dict]:
        """查询某天的应用使用统计"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT process_name,
                    COUNT(*) as session_count,
                    SUM(active_seconds) as total_active,
                    SUM(idle_seconds) as total_idle
                    FROM sessions WHERE DATE(start_time) = ?
                    GROUP BY process_name
                    ORDER BY total_active DESC""",
                (date,),
            )
            rows = cur.fetchall()

        return [
            {
                "process_name": row[0],
                "session_count": row[1],
                "active_seconds": row[2] or 0,
                "idle_seconds": row[3] or 0,
            }
            for row in rows
        ]

    def query_available_dates(self, limit: int = 30) -> list[str]:
        """查询有采集数据的日期列表（最近的优先）"""
        with self._cursor() as cur:
            cur.execute(
                "SELECT DISTINCT DATE(start_time) FROM sessions "
                "ORDER BY DATE(start_time) DESC LIMIT ?",
                (limit,),
            )
            return [row[0] for row in cur.fetchall()]

    def query_all_text_for_date(self, date: str) -> list[dict]:
        """查询某天所有文本片段（用于 AI 摘要生成）"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT ts.timestamp, ts.raw_text, ts.source, ts.is_filtered,
                    s.process_name, s.window_title
                    FROM text_segments ts
                    JOIN sessions s ON ts.session_id = s.id
                    WHERE DATE(ts.timestamp) = ?
                    ORDER BY ts.timestamp""",
                (date,),
            )
            rows = cur.fetchall()

        return [
            {
                "timestamp": row[0], "text": row[1], "source": row[2],
                "is_filtered": bool(row[3]), "process_name": row[4],
                "window_title": row[5],
            }
            for row in rows
        ]

    # ==================== 跨日统计 ====================

    def query_app_usage_stats_range(self, start_date: str, end_date: str) -> list[dict]:
        """查询日期范围内的应用使用统计"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT process_name,
                    COUNT(*) as session_count,
                    SUM(active_seconds) as total_active,
                    SUM(idle_seconds) as total_idle
                    FROM sessions
                    WHERE DATE(start_time) BETWEEN ? AND ?
                    GROUP BY process_name
                    ORDER BY total_active DESC""",
                (start_date, end_date),
            )
            rows = cur.fetchall()

        return [
            {
                "process_name": row[0],
                "session_count": row[1],
                "active_seconds": row[2] or 0,
                "idle_seconds": row[3] or 0,
            }
            for row in rows
        ]

    # ==================== 周报/月报 CRUD ====================

    def insert_period_report(self, report: PeriodReportRecord):
        """插入或替换一条周报/月报"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO period_reports
                   (report_type, period_start, period_end, report_label,
                    structured_report, model_used, generated_at, format, token_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.report_type, report.period_start,
                    report.period_end, report.report_label,
                    report.structured_report, report.model_used,
                    report.generated_at, report.format, report.token_count,
                ),
            )

    def query_period_report(
        self, report_type: str, period_start: str
    ) -> PeriodReportRecord | None:
        """查询指定类型的周期报告"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, report_type, period_start, period_end, report_label,
                    structured_report, model_used, generated_at, format, token_count
                    FROM period_reports
                    WHERE report_type = ? AND period_start = ?""",
                (report_type, period_start),
            )
            row = cur.fetchone()

        if not row:
            return None

        return PeriodReportRecord(
            id=row[0], report_type=row[1], period_start=row[2],
            period_end=row[3], report_label=row[4],
            structured_report=row[5], model_used=row[6],
            generated_at=row[7], format=row[8], token_count=row[9],
        )
