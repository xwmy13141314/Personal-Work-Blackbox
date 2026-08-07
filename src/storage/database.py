"""SQLite 数据库操作封装

线程安全：内部通过 threading.Lock 保护所有读写操作，
确保多线程并发访问时 commit/rollback 不会互相干扰。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

# 尝试导入 sqlcipher3（如果可用）
try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    HAS_SQLCIPHER = True
except ImportError:
    try:
        import sqlcipher3 as sqlcipher
        HAS_SQLCIPHER = True
    except ImportError:
        sqlcipher = None
        HAS_SQLCIPHER = False

from .models import (
    SessionRecord,
    TextSegmentRecord,
    ClipboardRecordModel,
    DailyReportRecord,
    PeriodReportRecord,
    WindowEventRecord,
    TodoRecord,
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
    is_filtered   INTEGER DEFAULT 0,
    category      TEXT DEFAULT '其他',
    icon          TEXT DEFAULT '📦'
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

-- 待办事项
CREATE TABLE IF NOT EXISTS todos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    priority      TEXT NOT NULL DEFAULT 'normal',
    note          TEXT DEFAULT '',
    due_date      TEXT,
    source_type   TEXT DEFAULT 'manual',
    source_ref    TEXT DEFAULT '',
    is_draft      INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    completed_at  TEXT
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
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_todos_draft ON todos(is_draft);
CREATE INDEX IF NOT EXISTS idx_todos_due ON todos(due_date);
CREATE INDEX IF NOT EXISTS idx_todos_source ON todos(source_type, source_ref);
"""


class Database:
    """SQLite 数据库管理器（线程安全）

    内部使用 threading.Lock 保护所有数据库操作，
    确保多线程并发访问时事务不会互相干扰。
    """

    def __init__(self, db_path: str | Path, journal_mode: str = "WAL", encryption_key: str | None = None):
        self._db_path = Path(db_path)
        self._journal_mode = journal_mode
        self._encryption_key = encryption_key
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def initialize(self):
        """初始化数据库（建表）

        若提供了 encryption_key 且 sqlcipher3 可用，则使用加密连接；
        否则回退到普通 sqlite3。
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if self._encryption_key and HAS_SQLCIPHER:
            # 使用 SQLCipher 加密连接
            self._conn = sqlcipher.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.execute(f"PRAGMA key='{self._encryption_key}'")
        else:
            # 回退到普通 sqlite3
            if self._encryption_key and not HAS_SQLCIPHER:
                logger.warning("已配置加密密钥但 sqlcipher3 未安装，回退到明文 sqlite3")
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
        self._conn.execute(f"PRAGMA journal_mode={self._journal_mode}")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA_SQL)
        self._migrate_schema()
        self._conn.commit()
        logger.info("数据库已初始化: %s", self._db_path)

    def _migrate_schema(self):
        """数据库 schema 迁移（向后兼容）

        为旧版数据库补充新增列，已存在则跳过。
        """
        migrations = [
            ("sessions", "category", "TEXT DEFAULT '其他'"),
            ("sessions", "icon", "TEXT DEFAULT '📦'"),
        ]
        for table, column, col_type in migrations:
            try:
                cursor = self._conn.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                if column not in columns:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    logger.info("数据库迁移: %s.%s 已添加", table, column)
            except Exception as e:
                logger.debug("迁移检查跳过 %s.%s: %s", table, column, e)
        self._conn.commit()

    def migrate_to_encrypted(self, encryption_key: str) -> bool:
        """将现有明文数据库迁移到加密数据库

        迁移流程：备份原文件 → 使用 sqlcipher_export 导出到加密副本 → 替换原文件。
        若数据库已加密或不存在，则直接以加密模式初始化。

        Returns: True 如果迁移成功或已加密，False 如果迁移失败
        """
        if not HAS_SQLCIPHER:
            logger.warning("sqlcipher3 未安装，无法加密数据库")
            return False

        if not self._db_path.exists():
            logger.info("数据库文件不存在，无需迁移，将直接创建加密数据库")
            self._encryption_key = encryption_key
            self.initialize()
            return True

        # 先关闭现有连接
        if self._conn:
            self._conn.close()
            self._conn = None

        # 检查是否已经加密（尝试用 key 打开并读取）
        try:
            test_conn = sqlcipher.connect(str(self._db_path), check_same_thread=False)
            test_conn.execute(f"PRAGMA key='{encryption_key}'")
            test_conn.execute("SELECT count(*) FROM sqlite_master")
            test_conn.close()
            logger.info("数据库已加密，无需迁移")
            self._encryption_key = encryption_key
            self.initialize()
            return True
        except Exception:
            pass  # 数据库未加密或 key 错误，继续迁移

        # 执行迁移：明文 → 加密
        backup_path = self._db_path.with_suffix('.db.plain_backup')
        try:
            # 1. 备份原文件
            import shutil
            shutil.copy2(self._db_path, backup_path)

            # 2. 打开明文数据库（使用 sqlcipher 以支持 ATTACH KEY 和 sqlcipher_export）
            plain_conn = sqlcipher.connect(str(self._db_path), check_same_thread=False)

            # 3. 创建加密副本路径，清理可能残留的临时文件
            enc_path = self._db_path.with_suffix('.db.enc')
            if enc_path.exists():
                enc_path.unlink()

            # 4. 使用 ATTACH + sqlcipher_export 迁移数据
            plain_conn.execute(f"ATTACH DATABASE '{enc_path}' AS encrypted KEY '{encryption_key}'")
            plain_conn.execute("SELECT sqlcipher_export('encrypted')")
            plain_conn.execute("DETACH DATABASE encrypted")
            plain_conn.close()

            # 5. 替换原文件
            self._db_path.unlink()
            enc_path.rename(self._db_path)

            self._encryption_key = encryption_key
            self.initialize()
            logger.info("数据库加密迁移成功，明文备份: %s", backup_path)
            return True
        except Exception as e:
            logger.error("数据库加密迁移失败: %s", e)
            # 恢复备份
            if backup_path.exists() and not self._db_path.exists():
                import shutil
                shutil.copy2(backup_path, self._db_path)
            return False

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
        """获取游标的上下文管理器（线程安全，加锁保护）"""
        if not self._conn:
            raise RuntimeError("数据库未初始化")
        with self._lock:
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
                   idle_seconds, active_seconds, is_filtered, category, icon)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.start_time, session.end_time,
                    session.process_name, session.window_title,
                    session.idle_seconds, session.active_seconds,
                    int(session.is_filtered),
                    session.category, session.icon,
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

    def insert_session_with_segments(
        self, session: SessionRecord, segments: list[TextSegmentRecord]
    ) -> int:
        """原子性插入会话及其所有文本片段（单事务）

        解决旧版逐条 insert 导致的"有会话无片段"不一致问题。
        若中途异常，整个事务回滚，不会产生半写入数据。
        """
        if not self._conn:
            raise RuntimeError("数据库未初始化")
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(
                    """INSERT INTO sessions (start_time, end_time, process_name, window_title,
                       idle_seconds, active_seconds, is_filtered, category, icon)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session.start_time, session.end_time,
                        session.process_name, session.window_title,
                        session.idle_seconds, session.active_seconds,
                        int(session.is_filtered),
                        session.category, session.icon,
                    ),
                )
                session_id = cursor.lastrowid
                for seg in segments:
                    cursor.execute(
                        """INSERT INTO text_segments (session_id, timestamp, raw_text, source,
                           is_filtered, char_count)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            session_id, seg.timestamp,
                            seg.raw_text, seg.source,
                            int(seg.is_filtered), seg.char_count,
                        ),
                    )
                self._conn.commit()
                return session_id
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cursor.close()

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
                    idle_seconds, active_seconds, is_filtered, category, icon
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
                category=row[8] if row[8] else "其他",
                icon=row[9] if row[9] else "📦",
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

    def count_text_segments(self, session_id: int) -> int:
        """查询某个会话的文本片段数量（轻量查询，用于列表展示）"""
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM text_segments WHERE session_id = ?",
                (session_id,),
            )
            return cur.fetchone()[0]

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

    def query_reported_dates(self, limit: int = 90) -> list[str]:
        """查询已生成日报的日期列表（最近的优先，用于日历标记）"""
        with self._cursor() as cur:
            cur.execute(
                "SELECT report_date FROM daily_reports "
                "ORDER BY report_date DESC LIMIT ?",
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

    def query_session_by_id(self, session_id: int) -> SessionRecord | None:
        """按主键查单个会话"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, start_time, end_time, process_name, window_title,
                          idle_seconds, active_seconds, is_filtered, category, icon
                   FROM sessions WHERE id = ?""",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return SessionRecord(
            id=row[0], start_time=row[1], end_time=row[2], process_name=row[3],
            window_title=row[4], idle_seconds=row[5], active_seconds=row[6],
            is_filtered=bool(row[7]),
            category=row[8] if row[8] else "其他",
            icon=row[9] if row[9] else "📦",
        )

    def search_text(self, keyword: str, limit: int = 50) -> list[dict]:
        """全文搜索文本片段（LIKE 匹配，返回截断片段用于预览）"""
        kw = f"%{keyword}%"
        with self._cursor() as cur:
            cur.execute(
                """SELECT ts.id, ts.session_id, ts.timestamp, ts.raw_text, ts.source,
                          ts.is_filtered, s.process_name, s.window_title,
                          DATE(ts.timestamp) as date
                   FROM text_segments ts
                   LEFT JOIN sessions s ON ts.session_id = s.id
                   WHERE ts.raw_text LIKE ?
                   ORDER BY ts.timestamp DESC
                   LIMIT ?""",
                (kw, limit),
            )
            rows = cur.fetchall()
        return [
            {
                "id": row[0], "session_id": row[1], "timestamp": row[2],
                "text": (row[3] or "")[:120], "source": row[4],
                "is_filtered": bool(row[5]), "process_name": row[6] or "",
                "window_title": row[7] or "", "date": row[8],
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

    def query_category_stats(
        self,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """按分类统计使用时长

        Args:
            date: 单日查询（YYYY-MM-DD）
            start_date: 范围起始日（与 end_date 配合使用）
            end_date: 范围结束日

        Returns:
            分类统计列表，按活跃时长降序排列
        """
        conditions = []
        params: list = []
        if date:
            conditions.append("DATE(start_time) = ?")
            params.append(date)
        elif start_date and end_date:
            conditions.append("DATE(start_time) BETWEEN ? AND ?")
            params.extend([start_date, end_date])

        where = " WHERE " + " AND ".join(conditions) if conditions else ""

        with self._cursor() as cur:
            cur.execute(
                f"""SELECT COALESCE(category, '其他') as category,
                    COALESCE(icon, '📦') as icon,
                    COUNT(*) as session_count,
                    SUM(active_seconds) as total_active,
                    SUM(idle_seconds) as total_idle
                    FROM sessions{where}
                    GROUP BY category
                    ORDER BY total_active DESC""",
                params,
            )
            rows = cur.fetchall()

        return [
            {
                "category": row[0],
                "icon": row[1],
                "session_count": row[2],
                "active_seconds": row[3] or 0,
                "idle_seconds": row[4] or 0,
            }
            for row in rows
        ]

    def backfill_categories(self) -> int:
        """为已有的历史会话记录回填分类（批量更新）

        仅更新 category 为 NULL 或 '其他' 的记录。

        Returns: 更新的行数
        """
        from src.processor.app_classifier import AppClassifier
        classifier = AppClassifier()

        with self._cursor() as cur:
            cur.execute(
                "SELECT id, process_name, window_title FROM sessions "
                "WHERE category IS NULL OR category = '其他'"
            )
            rows = cur.fetchall()

            updated = 0
            for row in rows:
                session_id, process_name, window_title = row
                category, icon = classifier.classify(process_name, window_title)
                if category != "其他":
                    cur.execute(
                        "UPDATE sessions SET category = ?, icon = ? WHERE id = ?",
                        (category, icon, session_id),
                    )
                    updated += 1

            return updated

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

    # ==================== 待办事项 CRUD ====================

    def insert_todo(self, todo: TodoRecord) -> int:
        """插入一条待办，返回自增 ID"""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO todos (title, status, priority, note, due_date,
                   source_type, source_ref, is_draft, created_at, updated_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    todo.title, todo.status, todo.priority, todo.note, todo.due_date,
                    todo.source_type, todo.source_ref, int(todo.is_draft),
                    todo.created_at, todo.updated_at, todo.completed_at,
                ),
            )
            return cur.lastrowid

    def query_todo(self, todo_id: int) -> TodoRecord | None:
        """按主键查单个待办"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, title, status, priority, note, due_date, source_type,
                   source_ref, is_draft, created_at, updated_at, completed_at
                   FROM todos WHERE id = ?""",
                (todo_id,),
            )
            row = cur.fetchone()
        return self._row_to_todo(row) if row else None

    def query_todos(
        self,
        status: str | None = None,
        include_drafts: bool = True,
        source_ref: str | None = None,
    ) -> list[TodoRecord]:
        """查询待办列表（默认含草稿，按创建时间降序）

        Args:
            status: 按状态过滤（None = 全部）
            include_drafts: 是否包含草稿区的待办
            source_ref: 按来源标识过滤
        """
        conditions = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if not include_drafts:
            conditions.append("is_draft = 0")
        if source_ref:
            conditions.append("source_ref = ?")
            params.append(source_ref)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT id, title, status, priority, note, due_date, source_type,
                    source_ref, is_draft, created_at, updated_at, completed_at
                    FROM todos{where}
                    ORDER BY created_at DESC""",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_todo(row) for row in rows]

    def update_todo(self, todo_id: int, fields: dict) -> bool:
        """更新待办字段（白名单校验，防注入）

        Args:
            fields: 允许更新的列子集 {title/status/priority/note/due_date/
                    is_draft/updated_at/completed_at/source_type/source_ref}
        Returns:
            True 如果有行被更新
        """
        allowed = {
            "title", "status", "priority", "note", "due_date", "is_draft",
            "updated_at", "completed_at", "source_type", "source_ref",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params: list = []
        for k in updates:
            v = updates[k]
            params.append(int(v) if k == "is_draft" else v)
        params.append(todo_id)
        with self._cursor() as cur:
            cur.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", params)
            return cur.rowcount > 0

    def delete_todo(self, todo_id: int) -> bool:
        """删除一条待办"""
        with self._cursor() as cur:
            cur.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            return cur.rowcount > 0

    @staticmethod
    def _row_to_todo(row) -> TodoRecord:
        """行记录转 TodoRecord"""
        return TodoRecord(
            id=row[0], title=row[1], status=row[2], priority=row[3],
            note=row[4] or "", due_date=row[5] or "",
            source_type=row[6] or "manual", source_ref=row[7] or "",
            is_draft=bool(row[8]),
            created_at=row[9], updated_at=row[10],
            completed_at=row[11] or "",
        )
