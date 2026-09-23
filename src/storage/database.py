"""SQLite 数据库操作封装

线程安全：内部通过 threading.Lock 保护所有读写操作，
确保多线程并发访问时 commit/rollback 不会互相干扰。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
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
    NoteRecord,
    ProjectRecord,
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
    completed_at  TEXT,
    sort_order    REAL NOT NULL DEFAULT 0,
    progress      INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT
);

-- 待办推进建议（AI 结合当日活动给的建议，P2 §4.6）
CREATE TABLE IF NOT EXISTS todo_advices (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    todo_id            INTEGER NOT NULL REFERENCES todos(id),
    suggestion_type    TEXT NOT NULL,
    reason             TEXT NOT NULL,
    suggested_status   TEXT,
    suggested_progress INTEGER,
    status             TEXT NOT NULL DEFAULT 'pending',
    source_date        TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todo_notify_log (
    todo_id      INTEGER NOT NULL,
    notify_date  TEXT NOT NULL,
    notify_type  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (todo_id, notify_date, notify_type)
);

-- 速记表（P1：单行速记 + 上下文关联；v5.4：+tags 标签，用于标签云/筛选与洞察收件箱落盘）
CREATE TABLE IF NOT EXISTS notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT NOT NULL,
    tags            TEXT DEFAULT '',
    source          TEXT DEFAULT 'manual',
    source_ref      TEXT DEFAULT '',
    linked_todo_id  INTEGER,
    pinned          INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);

-- 项目表（P1：待办/速记分类关联）
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    color       TEXT DEFAULT '#007AFF',
    icon        TEXT DEFAULT '📁',
    description TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived    INTEGER DEFAULT 0
);

-- 待办项目关联列（迁移添加）
-- projects 关联通过 todos.project_id 软关联

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
CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at);
CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(pinned);
CREATE INDEX IF NOT EXISTS idx_notes_deleted ON notes(deleted_at);
CREATE INDEX IF NOT EXISTS idx_notes_linked_todo ON notes(linked_todo_id);
CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(archived);
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

        # 清理可能残留的辅助文件
        for suffix in ("-wal", "-shm", "-journal"):
            p = self._db_path.with_name(self._db_path.name + suffix)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        # 尝试连接：WAL → DELETE → 新建
        connected = False
        for mode in [self._journal_mode, "DELETE"]:
            try:
                if self._encryption_key and HAS_SQLCIPHER:
                    self._conn = sqlcipher.connect(
                        str(self._db_path), check_same_thread=False
                    )
                    self._conn.execute(f"PRAGMA key='{self._encryption_key}'")
                else:
                    self._conn = sqlite3.connect(
                        str(self._db_path), check_same_thread=False
                    )
                self._conn.execute(f"PRAGMA journal_mode={mode}")
                self._journal_mode = mode
                connected = True
                break
            except Exception as e:
                logger.warning("数据库连接失败 (mode=%s): %s", mode, e)
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None

        if not connected:
            # 最后手段：备份旧库，创建新库
            bak = self._db_path.with_suffix(".db.corrupt")
            if self._db_path.exists():
                try:
                    self._db_path.rename(bak)
                    logger.warning("旧数据库已备份为 %s，将创建新数据库", bak)
                except Exception:
                    pass
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.execute("PRAGMA journal_mode=DELETE")
            self._journal_mode = "DELETE"
            logger.warning("已创建全新数据库: %s", self._db_path)

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
            ("todos", "sort_order", "REAL NOT NULL DEFAULT 0"),
            ("todos", "progress", "INTEGER NOT NULL DEFAULT 0"),
            ("todos", "deleted_at", "TEXT"),
            ("todos", "project_id", "INTEGER"),
            ("notes", "tags", "TEXT DEFAULT ''"),
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
        # 回填旧 todos 的 sort_order（按 id 升序赋 1..N；仅处理 sort_order=0 的旧行，幂等）
        try:
            rows = self._conn.execute(
                "SELECT id FROM todos WHERE sort_order = 0 ORDER BY id ASC"
            ).fetchall()
            if rows:
                for idx, (tid,) in enumerate(rows, start=1):
                    self._conn.execute(
                        "UPDATE todos SET sort_order = ? WHERE id = ?",
                        (float(idx), tid),
                    )
                logger.info("数据库迁移: 回填 %d 条 todos 的 sort_order", len(rows))
        except Exception as e:
            logger.debug("todos sort_order 回填跳过: %s", e)
        # 归档索引：列由上面的迁移补充后才能建（不能放 SCHEMA_SQL，
        # 否则旧库 executescript 时列还不存在会报错）
        try:
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_todos_deleted ON todos(deleted_at)"
            )
        except Exception as e:
            logger.debug("todos deleted_at 索引跳过: %s", e)
        # 旧版「洞察速记」表数据搬移（v5.4 合并并行开发线）：
        # v4.5 独立开发线的速记存在 `insights` 表，v5.x 官方速记在 `notes` 表。
        # 升级后若不搬移，旧记录在新速记页会「消失」。仅在 notes 为空时执行一次，
        # 原 insights 表保留原地不改（可随时回查）。
        try:
            exists = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='insights'"
            ).fetchone()
            if exists:
                notes_n = self._conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
                if not notes_n:
                    cols = {row[1] for row in self._conn.execute(
                        "PRAGMA table_info(insights)"
                    ).fetchall()}
                    if "content" in cols:
                        tags_expr = "COALESCE(tags, '')" if "tags" in cols else "''"
                        source_expr = ("COALESCE(source, 'manual')"
                                       if "source" in cols else "'manual'")
                        created_expr = ("COALESCE(created_at, '')"
                                        if "created_at" in cols else "''")
                        updated_expr = ("COALESCE(updated_at, '')"
                                        if "updated_at" in cols else "''")
                        cur = self._conn.execute(
                            "INSERT INTO notes (content, tags, source, source_ref, "
                            "linked_todo_id, pinned, created_at, updated_at, deleted_at) "
                            f"SELECT content, {tags_expr}, {source_expr}, '', NULL, 0, "
                            f"{created_expr}, {updated_expr}, NULL FROM insights"
                        )
                        if cur.rowcount:
                            logger.info(
                                "数据库迁移: insights → notes 搬移 %d 条旧速记", cur.rowcount
                            )
        except Exception as e:
            logger.debug("insights → notes 搬移跳过: %s", e)
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

    def find_recent_segment(self, within_seconds: float = 60.0,
                            source: str = "keyboard",
                            after_id: int = 0) -> dict | None:
        """查找最近 N 秒内、指定来源的下一条未消费文本片段

        用途：WPS 表格"提交回填"。
        WPS 编辑期间键盘钩子只能拿到拼音并提交入库；等用户离开单元格
        （内容真正写入单元格）后，COM 能读到汉字，此时需要找回刚才那条
        拼音片段并替换掉。

        Args:
            after_id: 只返回 id 大于该值的片段（回填水位线）。
                键盘片段是**延迟批量落库**的（InputBuffer 有超时），
                用递增水位线按顺序消费，可避免"回填到更早的记录"。
                取 `ORDER BY id ASC`（最老的一条未消费片段），
                保证多次提交与多条片段一一对应。

        Returns:
            {"id", "session_id", "timestamp", "raw_text", "char_count"} 或 None
        """
        if not self._conn:
            return None
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(seconds=within_seconds)).isoformat()
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, session_id, timestamp, raw_text, char_count
                   FROM text_segments
                   WHERE source = ? AND timestamp >= ? AND is_filtered = 0 AND id > ?
                   ORDER BY id ASC LIMIT 1""",
                (source, cutoff, int(after_id or 0)),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "session_id": row[1], "timestamp": row[2],
            "raw_text": row[3], "char_count": row[4],
        }

    def update_segment_text(self, segment_id: int, new_text: str) -> bool:
        """更新文本片段的原文（WPS 提交回填：拼音 → 汉字）

        Returns:
            True 表示确实更新了一行
        """
        if not self._conn:
            return False
        with self._cursor() as cur:
            cur.execute(
                "UPDATE text_segments SET raw_text = ?, char_count = ? WHERE id = ?",
                (new_text, len(new_text), segment_id),
            )
            return cur.rowcount > 0

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
        """插入一条待办，返回自增 ID

        sort_order 未指定（≤0）时自动放至当前末尾（MAX(sort_order)+1）。
        """
        with self._cursor() as cur:
            if todo.sort_order and todo.sort_order > 0:
                order = float(todo.sort_order)
            else:
                cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM todos")
                order = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO todos (title, status, priority, note, due_date,
                   source_type, source_ref, is_draft, created_at, updated_at,
                   completed_at, sort_order, progress)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    todo.title, todo.status, todo.priority, todo.note, todo.due_date,
                    todo.source_type, todo.source_ref, int(todo.is_draft),
                    todo.created_at, todo.updated_at, todo.completed_at, order,
                    int(getattr(todo, "progress", 0) or 0),
                ),
            )
            return cur.lastrowid

    def query_todo(self, todo_id: int) -> TodoRecord | None:
        """按主键查单个待办"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, title, status, priority, note, due_date, source_type,
                   source_ref, is_draft, created_at, updated_at, completed_at, sort_order, progress
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
        """查询待办列表（默认含草稿，按创建时间降序；不含软删除的归档待办）

        Args:
            status: 按状态过滤（None = 全部）
            include_drafts: 是否包含草稿区的待办
            source_ref: 按来源标识过滤
        """
        conditions = ["deleted_at IS NULL"]
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
                    source_ref, is_draft, created_at, updated_at, completed_at, sort_order, progress
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
            "updated_at", "completed_at", "source_type", "source_ref", "sort_order",
            "progress",
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

    def delete_todo(self, todo_id: int, deleted_at: str | None = None) -> bool:
        """软删除一条待办（写入 deleted_at，主界面不再显示，归档视图可查）

        Args:
            deleted_at: 删除时间 ISO8601（None = 由调用方传入；这里必须显式提供，
                        避免误调用产生无时间戳的归档记录）
        """
        if not deleted_at:
            return False
        with self._cursor() as cur:
            cur.execute(
                "UPDATE todos SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (deleted_at, todo_id),
            )
            return cur.rowcount > 0

    def query_archived_todos(
        self,
        keyword: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TodoRecord], int]:
        """查询已归档（软删除）的待办，返回 (记录列表, 匹配总数)

        Args:
            keyword: 标题/备注模糊匹配（空 = 全部）
            limit/offset: 分页
        按 deleted_at 降序（最近删除的在前）。
        """
        conditions = ["deleted_at IS NOT NULL"]
        params: list = []
        if keyword:
            conditions.append("(title LIKE ? OR note LIKE ?)")
            kw = f"%{keyword}%"
            params.extend([kw, kw])
        where = " WHERE " + " AND ".join(conditions)
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM todos{where}", params)
            total = cur.fetchone()[0] or 0
            cur.execute(
                f"""SELECT id, title, status, priority, note, due_date, source_type,
                    source_ref, is_draft, created_at, updated_at, completed_at,
                    sort_order, progress, deleted_at
                    FROM todos{where}
                    ORDER BY deleted_at DESC
                    LIMIT ? OFFSET ?""",
                [*params, int(limit), int(offset)],
            )
            rows = cur.fetchall()
        items = []
        for row in rows:
            t = self._row_to_todo(row)
            t.deleted_at = row[14] or ""
            items.append(t)
        return items, total

    def restore_todo(self, todo_id: int) -> bool:
        """恢复一条归档待办（清空 deleted_at，sort_order 保留 → 回到原看板位置）"""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE todos SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL",
                (todo_id,),
            )
            return cur.rowcount > 0

    def purge_todo(self, todo_id: int) -> bool:
        """彻底删除一条归档待办（真 DELETE，仅归档视图手动触发）"""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM todos WHERE id = ? AND deleted_at IS NOT NULL",
                (todo_id,),
            )
            return cur.rowcount > 0

    def reorder_todos(self, items: list[dict]) -> int:
        """批量更新待办排序（仅改 sort_order，纯展示序调整，不动 updated_at）

        Args:
            items: [{"id": int, "sort_order": float}, ...]（前端算好新序后传入，
                   通常用两值中间插值，避免整体重排）
        Returns:
            实际更新的行数
        """
        if not items:
            return 0
        updated = 0
        with self._cursor() as cur:
            for it in items:
                cur.execute(
                    "UPDATE todos SET sort_order = ? WHERE id = ?",
                    (float(it["sort_order"]), int(it["id"])),
                )
                updated += cur.rowcount
        return updated

    def get_todo_stats(self, today: str) -> dict:
        """待办统计（4 指标，PRD v4.3 §4.7 口径）

        Args:
            today: "YYYY-MM-DD"（用于判定逾期）
        Returns:
            {total, today_pending, overdue, done}
            - total: 全部已入库待办（is_draft=0，含 cancelled）
            - today_pending: 未完成（pending/in_progress）且未逾期（无截止 或 due_date >= today）
            - overdue: 未完成且逾期（due_date < today）
            - done: status=done
            cancelled 不计入 today_pending/overdue/done，但含在 total；
            today_pending 与 overdue 互斥，合起来 = 全部未完成。
        """
        with self._cursor() as cur:
            cur.execute(
                """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status IN ('pending','in_progress')
                             AND (due_date IS NULL OR due_date = '' OR due_date >= ?)
                        THEN 1 ELSE 0 END) AS today_pending,
                    SUM(CASE WHEN status IN ('pending','in_progress')
                             AND due_date IS NOT NULL AND due_date != '' AND due_date < ?
                        THEN 1 ELSE 0 END) AS overdue,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done_count
                    FROM todos WHERE is_draft = 0 AND deleted_at IS NULL""",
                (today, today),
            )
            row = cur.fetchone()
        return {
            "total": row[0] or 0,
            "today_pending": row[1] or 0,
            "overdue": row[2] or 0,
            "done": row[3] or 0,
        }

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
            sort_order=float(row[12] or 0),
            progress=int(row[13] or 0),
        )

    # ==================== 待办推进建议（P2 §4.6） ====================

    def insert_todo_advice(self, advice) -> int:
        """插入一条推进建议；同 todo_id 已有 pending 建议则去重跳过（返回 0）

        Returns:
            新建记录 id；去重跳过返回 0
        """
        with self._cursor() as cur:
            # 去重：同一待办已有未处理建议则不再重复生成
            cur.execute(
                "SELECT id FROM todo_advices WHERE todo_id = ? AND status = 'pending'",
                (advice.todo_id,),
            )
            if cur.fetchone():
                return 0
            cur.execute(
                """INSERT INTO todo_advices (todo_id, suggestion_type, reason,
                   suggested_status, suggested_progress, status, source_date,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    advice.todo_id, advice.suggestion_type, advice.reason,
                    advice.suggested_status, advice.suggested_progress,
                    advice.status, advice.source_date,
                    advice.created_at, advice.updated_at,
                ),
            )
            return cur.lastrowid

    def query_todo_advices(self, status: str = "pending") -> list[dict]:
        """查询推进建议（关联 todo 标题，前端展示用）

        Returns:
            [{id, todo_id, todo_title, suggestion_type, reason, suggested_status,
              suggested_progress, status, source_date, created_at}, ...]
            按 created_at 降序；关联 todo 已删除则标题显示「（待办已删除）」。
        """
        with self._cursor() as cur:
            cur.execute(
                """SELECT a.id, a.todo_id, t.title, a.suggestion_type, a.reason,
                   a.suggested_status, a.suggested_progress, a.status,
                   a.source_date, a.created_at
                   FROM todo_advices a
                   LEFT JOIN todos t ON t.id = a.todo_id
                   WHERE a.status = ?
                   ORDER BY a.created_at DESC""",
                (status,),
            )
            rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0], "todo_id": r[1], "todo_title": r[2] or "（待办已删除）",
                "suggestion_type": r[3], "reason": r[4] or "",
                "suggested_status": r[5] or "", "suggested_progress": r[6],
                "status": r[7], "source_date": r[8] or "",
                "created_at": r[9] or "",
            })
        return result

    def query_advice(self, advice_id: int) -> dict | None:
        """查单条建议（采纳时取 suggestion_type / suggested_* 用）"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT id, todo_id, suggestion_type, reason, suggested_status,
                   suggested_progress, status FROM todo_advices WHERE id = ?""",
                (advice_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "todo_id": row[1], "suggestion_type": row[2],
            "reason": row[3] or "", "suggested_status": row[4] or "",
            "suggested_progress": row[5], "status": row[6],
        }

    def update_advice_status(self, advice_id: int, status: str) -> bool:
        """更新建议状态（applied / dismissed）"""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE todo_advices SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.now().isoformat(), advice_id),
            )
            return cur.rowcount > 0

    def record_todo_notify(self, todo_id: int, notify_date: str, notify_type: str) -> bool:
        """记录待办通知；返回 True=本次首次可发（去重通过），False=今天已通知过（P3 §4.9）

        PRIMARY KEY (todo_id, notify_date, notify_type) + INSERT OR IGNORE 实现去重，
        每任务每日每类（overdue/upcoming）最多通知一次。
        """
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO todo_notify_log (todo_id, notify_date, notify_type, created_at) "
                "VALUES (?, ?, ?, ?)",
                (todo_id, notify_date, notify_type, datetime.now().isoformat()),
            )
            return cur.rowcount > 0

    # ==================== 速记 CRUD ====================

    def insert_note(self, content: str, source: str = "manual", source_ref: str = "",
                    linked_todo_id: int | None = None, pinned: bool = False,
                    tags: str = "") -> int:
        """插入速记，返回 id（tags：逗号分隔标签串，建议先用 normalize_tags 归一化）"""
        now = datetime.now().isoformat()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO notes (content, tags, source, source_ref, linked_todo_id, pinned, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (content, tags or "", source, source_ref, linked_todo_id, int(pinned), now, now),
            )
            return cur.lastrowid

    def query_notes(self, limit: int = 100, offset: int = 0,
                    include_deleted: bool = False, tag: str = "") -> list[dict]:
        """查询速记列表（按 pinned DESC, created_at DESC）

        Args:
            tag: 非空时只返回含该标签的速记（v5.4 标签云筛选）
        """
        tag = (tag or "").strip()
        where: list[str] = []
        params: list = []
        if not include_deleted:
            where.append("deleted_at IS NULL")
        if tag:
            # 用逗号包裹后 LIKE，避免 "报告" 误匹配 "周报告" 这类子串
            where.append("(',' || tags || ',') LIKE ?")
            params.append(f"%,{tag},%")
        sql = ("SELECT id, content, tags, source, source_ref, linked_todo_id, pinned, "
               "created_at, updated_at, deleted_at FROM notes ")
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY pinned DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._note_row_to_dict(r) for r in rows]

    def update_note(self, note_id: int, fields: dict) -> bool:
        """更新速记字段"""
        allowed = {"content", "tags", "source", "source_ref", "linked_todo_id", "pinned"}
        sets = []
        vals = []
        for k in allowed:
            if k in fields:
                v = fields[k]
                if k == "pinned":
                    v = int(bool(v)) if v is not None else 0
                if k == "linked_todo_id":
                    v = v if v else None
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return False
        sets.append("updated_at = ?")
        vals.append(datetime.now().isoformat())
        vals.append(note_id)
        with self._cursor() as cur:
            cur.execute(f"UPDATE notes SET {', '.join(sets)} WHERE id = ?", vals)
            return cur.rowcount > 0

    def delete_note(self, note_id: int) -> bool:
        """软删除速记"""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE notes SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), datetime.now().isoformat(), note_id),
            )
            return cur.rowcount > 0

    def search_notes(self, keyword: str, limit: int = 20) -> list[dict]:
        """全文搜索速记（内容 + 标签，v5.4）"""
        kw = f"%{keyword}%"
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, content, tags, source, source_ref, linked_todo_id, pinned, "
                "created_at, updated_at, deleted_at FROM notes "
                "WHERE deleted_at IS NULL AND (content LIKE ? OR tags LIKE ?) "
                "ORDER BY pinned DESC, created_at DESC LIMIT ?",
                (kw, kw, limit),
            )
            rows = cur.fetchall()
        return [self._note_row_to_dict(r) for r in rows]

    def list_note_tags(self) -> list[dict]:
        """统计全部标签及出现次数（标签云数据源，按次数降序、同次数按标签名升序）"""
        counts: dict[str, int] = {}
        with self._cursor() as cur:
            cur.execute("SELECT tags FROM notes WHERE deleted_at IS NULL AND tags != ''")
            rows = cur.fetchall()
        for (raw,) in rows:
            for t in str(raw or "").split(","):
                t = t.strip()
                if t:
                    counts[t] = counts.get(t, 0) + 1
        return [{"tag": k, "count": v}
                for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    def get_note_stats(self) -> dict:
        """速记统计：今日 / 本周（周一为始）/ 累计 / 置顶（v5.4 速记页指标）"""
        today = date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL")
            total = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL "
                "AND substr(created_at, 1, 10) = ?",
                (today.isoformat(),),
            )
            today_n = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL "
                "AND substr(created_at, 1, 10) >= ?",
                (week_start,),
            )
            week_n = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL AND pinned = 1")
            pinned_n = int(cur.fetchone()[0] or 0)
        return {"today": today_n, "week": week_n, "total": total, "pinned": pinned_n}

    def _note_row_to_dict(self, row) -> dict:
        return {
            "id": row[0], "content": row[1] or "", "tags": row[2] or "",
            "source": row[3] or "manual",
            "source_ref": row[4] or "", "linked_todo_id": row[5],
            "pinned": bool(row[6]), "created_at": row[7] or "",
            "updated_at": row[8] or "", "deleted_at": row[9] or "",
        }

    # ==================== 项目 CRUD ====================

    def insert_project(self, name: str, color: str = "#007AFF", icon: str = "📁",
                       description: str = "") -> int:
        """插入项目，返回 id"""
        now = datetime.now().isoformat()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO projects (name, color, icon, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, color, icon, description, now, now),
            )
            return cur.lastrowid

    def query_projects(self, include_archived: bool = False) -> list[dict]:
        """查询项目列表"""
        sql = ("SELECT id, name, color, icon, description, created_at, updated_at, archived "
               "FROM projects " + ("" if include_archived else "WHERE archived = 0 ") +
               "ORDER BY created_at ASC")
        with self._cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return [{
            "id": r[0], "name": r[1] or "", "color": r[2] or "#007AFF",
            "icon": r[3] or "📁", "description": r[4] or "",
            "created_at": r[5] or "", "updated_at": r[6] or "",
            "archived": bool(r[7]),
        } for r in rows]

    def update_project(self, project_id: int, fields: dict) -> bool:
        """更新项目字段"""
        allowed = {"name", "color", "icon", "description", "archived"}
        sets = []
        vals = []
        for k in allowed:
            if k in fields:
                v = fields[k]
                if k == "archived":
                    v = int(bool(v)) if v is not None else 0
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return False
        sets.append("updated_at = ?")
        vals.append(datetime.now().isoformat())
        vals.append(project_id)
        with self._cursor() as cur:
            cur.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", vals)
            return cur.rowcount > 0

    def delete_project(self, project_id: int) -> bool:
        """归档项目（软删除，不真正删除以保护关联数据）"""
        return self.update_project(project_id, {"archived": True})

    # ==================== 驾驶舱聚合 ====================

    def query_dashboard_summary(self, today: str) -> dict:
        """驾驶舱摘要数据：聚合各模块关键指标"""
        # 今日采集时长 + 片段数
        today_stats = self.query_app_usage_stats(today)
        today_seconds = sum(s.get("active_seconds", 0) for s in today_stats)
        today_segments = len(self.query_all_text_for_date(today))

        # 待办统计
        todo_stats = {"total": 0, "today_pending": 0, "overdue": 0, "done": 0}
        try:
            cur = self._conn.execute(
                "SELECT status, due_date, is_draft, deleted_at FROM todos"
            )
            for row in cur.fetchall():
                status, due, is_draft, deleted_at = row
                if deleted_at or is_draft:
                    continue
                todo_stats["total"] += 1
                if status == "done":
                    todo_stats["done"] += 1
                elif status in ("pending", "in_progress"):
                    if due and due < today:
                        todo_stats["overdue"] += 1
                    else:
                        todo_stats["today_pending"] += 1
        except Exception:
            pass

        # 速记统计
        note_count = 0
        pinned_count = 0
        try:
            cur = self._conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN pinned=1 THEN 1 ELSE 0 END) "
                "FROM notes WHERE deleted_at IS NULL"
            )
            row = cur.fetchone()
            if row:
                note_count = row[0] or 0
                pinned_count = row[1] or 0
        except Exception:
            pass

        # 最近报告
        recent_reports: list[dict] = []
        try:
            cur = self._conn.execute(
                "SELECT report_date, 'daily' FROM daily_reports "
                "ORDER BY generated_at DESC LIMIT 3"
            )
            for row in cur.fetchall():
                recent_reports.append({"type": "daily", "date": row[0]})
            cur = self._conn.execute(
                "SELECT report_type, period_start FROM period_reports "
                "ORDER BY generated_at DESC LIMIT 3"
            )
            for row in cur.fetchall():
                recent_reports.append({"type": row[0], "date": row[1]})
            recent_reports.sort(key=lambda x: x["date"], reverse=True)
            recent_reports = recent_reports[:5]
        except Exception:
            pass

        # 有数据的日期列表（最近7天）
        available_dates = self.query_available_dates(7)

        return {
            "today_seconds": round(today_seconds, 1),
            "today_segments": today_segments,
            "todo_total": todo_stats["total"],
            "todo_pending": todo_stats["today_pending"],
            "todo_overdue": todo_stats["overdue"],
            "todo_done": todo_stats["done"],
            "note_count": note_count,
            "note_pinned": pinned_count,
            "recent_reports": recent_reports,
            "available_dates": available_dates,
        }

    # ==================== 全局搜索 ====================

    def global_search(self, keyword: str, limit: int = 20) -> dict:
        """全局搜索：跨文本片段、速记、待办、报告"""
        results: dict[str, list] = {"text_segments": [], "notes": [], "todos": [], "reports": []}

        kw = f"%{keyword}%"

        # 搜索文本片段
        try:
            cur = self._conn.execute(
                "SELECT id, session_id, timestamp, raw_text, source, is_filtered, char_count "
                "FROM text_segments WHERE raw_text LIKE ? AND is_filtered = 0 "
                "ORDER BY timestamp DESC LIMIT ?",
                (kw, limit),
            )
            for row in cur.fetchall():
                results["text_segments"].append({
                    "id": row[0], "session_id": row[1], "timestamp": row[2],
                    "text": row[3], "source": row[4], "is_filtered": bool(row[5]),
                    "char_count": row[6],
                })
        except Exception:
            pass

        # 搜索速记
        results["notes"] = self.search_notes(keyword, limit)

        # 搜索待办
        try:
            cur = self._conn.execute(
                "SELECT id, title, status, priority, due_date, source_type, source_ref "
                "FROM todos WHERE deleted_at IS NULL AND title LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (kw, limit),
            )
            for row in cur.fetchall():
                results["todos"].append({
                    "id": row[0], "title": row[1], "status": row[2],
                    "priority": row[3], "due_date": row[4] or "",
                    "source_type": row[5] or "manual", "source_ref": row[6] or "",
                })
        except Exception:
            pass

        # 搜索报告（日报 + 周报/月报）
        try:
            cur = self._conn.execute(
                "SELECT report_date, structured_report FROM daily_reports "
                "WHERE report_date LIKE ? OR structured_report LIKE ? "
                "ORDER BY report_date DESC LIMIT ?",
                (kw, kw, limit),
            )
            for row in cur.fetchall():
                results["reports"].append({
                    "type": "daily", "date": row[0],
                    "excerpt": (row[1] or "")[:120],
                })
            cur = self._conn.execute(
                "SELECT report_type, period_start, report_label, structured_report "
                "FROM period_reports WHERE report_label LIKE ? OR structured_report LIKE ? "
                "ORDER BY period_start DESC LIMIT ?",
                (kw, kw, limit),
            )
            for row in cur.fetchall():
                results["reports"].append({
                    "type": row[0], "date": row[1], "label": row[2] or "",
                    "excerpt": (row[3] or "")[:120],
                })
        except Exception:
            pass

        return results

    # ==================== 周度洞察统计 ====================

    def query_hourly_stats_range(self, start_date: str, end_date: str) -> list[dict]:
        """按小时聚合活跃时长（用于最佳工作时段分析）"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT CAST(strftime('%H', start_time) AS INTEGER) as hour,
                    SUM(active_seconds)
                    FROM sessions
                    WHERE DATE(start_time) BETWEEN ? AND ? AND is_filtered = 0
                    GROUP BY hour ORDER BY hour""",
                (start_date, end_date),
            )
            rows = cur.fetchall()
        return [{"hour": r[0], "active_seconds": r[1] or 0} for r in rows]

    def query_daily_totals_range(self, start_date: str, end_date: str) -> dict[str, float]:
        """按天聚合活跃时长，返回 {date: active_seconds}"""
        with self._cursor() as cur:
            cur.execute(
                """SELECT DATE(start_time), SUM(active_seconds)
                    FROM sessions
                    WHERE DATE(start_time) BETWEEN ? AND ?
                    GROUP BY DATE(start_time)""",
                (start_date, end_date),
            )
            rows = cur.fetchall()
        return {r[0]: (r[1] or 0) for r in rows}

    def query_category_stats_range(self, start_date: str, end_date: str) -> list[dict]:
        """范围内按分类统计（含娱乐占比分析）"""
        return self.query_category_stats(start_date=start_date, end_date=end_date)

