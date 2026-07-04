"""快照采集导入器 — 把 personal_recorder 的快照事件按 F1 融合写入 BlackboxEngine 主库

personal_recorder 的 SystemSnapshotCollector 采集 Git / Shell / 浏览器 / 文件 / 日历
等"快照式"活动（无时长），本导入器把它们映射进主库：

  文本主体类 → text_segments（日报 query_all_text_for_date 会纳入）
    shell_history → source='shell'
    git / git_branch / git_status / git_diff → source='git'
    browser_history / safari_history → source='browser'
  状态点类 → window_events（event_type 区分）
    filesystem_recent → event_type='file'
    macos_foreground  → event_type='foreground'
    calendar_event    → event_type='calendar'
  剪贴板快照 → clipboard_records

去重：当天同表内容相同的记录跳过（git_status 每次采集内容不变 → 当天只存一条；
shell 同名命令当天合并，轻微损失，可接受）。session_id=0 表示快照不属于任何实时会话。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from src.storage.models import ClipboardRecordModel, TextSegmentRecord, WindowEventRecord

# personal_recorder 子模块内部用 `personal_recorder.xxx` 绝对导入（原设计 PYTHONPATH=src，
# 即 personal_recorder 为顶层包）。worktrace-mac 以 `python -m src.main` 运行时它位于
# src/personal_recorder，故把 src 目录注入 sys.path 使其成为顶层包。
# 不影响 `from src.xxx`：cwd（worktrace-mac）同样在 sys.path，src 仍可经由 cwd 解析。
import sys as _sys
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in _sys.path:
    _sys.path.insert(0, _SRC_DIR)

logger = logging.getLogger(__name__)

# 文本类 source → text_segment.source 粗分类
_TEXT_SOURCE_MAP = {
    "shell_history": "shell",
    "git": "git",
    "git_branch": "git",
    "git_status": "git",
    "git_diff": "git",
    "browser_history": "browser",
    "safari_history": "browser",
}

# 状态点 source → window_event.event_type
_EVENT_TYPE_MAP = {
    "filesystem_recent": "file",
    "macos_foreground": "foreground",
    "calendar_event": "calendar",
}


class SnapshotImporter:
    """一轮快照采集 → 主库写入"""

    def __init__(self, db, db_path: str, roots: list[Path], since_hours: int = 24):
        self._db = db
        self._db_path = str(db_path)
        self._roots = roots
        self._since_hours = since_hours

    def run_once(self) -> dict:
        """采集一轮并写入主库，返回 {text,event,clipboard,skip_dup} 计数"""
        stats = {"text": 0, "event": 0, "clipboard": 0, "skip_dup": 0}
        try:
            from personal_recorder.collectors.system_snapshot import (
                SnapshotOptions,
                SystemSnapshotCollector,
            )
            options = SnapshotOptions(roots=self._roots, since_hours=self._since_hours)
            events = SystemSnapshotCollector().collect(options)
        except Exception:
            logger.exception("快照采集失败")
            return stats

        today = datetime.now().strftime("%Y-%m-%d")
        like = today + "%"
        conn = sqlite3.connect(self._db_path)
        try:
            snap_session_id = self._get_or_create_snapshot_session(conn, today)
            seen_text = {r[0] for r in conn.execute(
                "SELECT raw_text FROM text_segments WHERE timestamp LIKE ?", (like,))}
            seen_event = {(r[0], r[1]) for r in conn.execute(
                "SELECT event_type, window_title FROM window_events WHERE timestamp LIKE ?", (like,))}
            seen_clip = {r[0] for r in conn.execute(
                "SELECT content FROM clipboard_records WHERE timestamp LIKE ?", (like,))}
        finally:
            conn.close()

        for ev in events:
            source = ev.get("source", "")
            content = ev.get("content", "")
            if not content:
                continue
            ts = self._norm_ts(ev.get("timestamp", ""))

            if source in _TEXT_SOURCE_MAP:
                if content in seen_text:
                    stats["skip_dup"] += 1
                    continue
                self._db.insert_text_segment(TextSegmentRecord(
                    session_id=snap_session_id,
                    timestamp=ts,
                    raw_text=content,
                    source=_TEXT_SOURCE_MAP[source],
                    is_filtered=False,
                    char_count=len(content),
                ))
                seen_text.add(content)
                stats["text"] += 1

            elif source == "macos_clipboard":
                if content in seen_clip:
                    stats["skip_dup"] += 1
                    continue
                self._db.insert_clipboard_record(ClipboardRecordModel(
                    timestamp=ts,
                    content=content,
                    content_length=len(content),
                    source_process=ev.get("app_name", ""),
                    is_filtered=False,
                ))
                seen_clip.add(content)
                stats["clipboard"] += 1

            elif source in _EVENT_TYPE_MAP:
                event_type = _EVENT_TYPE_MAP[source]
                window_title = ev.get("window_title", "") or ev.get("project", "") or ""
                key = (event_type, window_title)
                if key in seen_event:
                    stats["skip_dup"] += 1
                    continue
                self._db.insert_window_event(WindowEventRecord(
                    timestamp=ts,
                    event_type=event_type,
                    process_name=ev.get("app_name", ""),
                    window_title=window_title,
                    duration_seconds=0.0,
                ))
                seen_event.add(key)
                stats["event"] += 1

        logger.info("快照导入完成: %s", stats)
        return stats

    @staticmethod
    def _get_or_create_snapshot_session(conn, today: str) -> int:
        """获取或创建当天的快照虚拟会话（process_name='__snapshot__'），返回 session_id。
        query_all_text_for_date 通过 JOIN sessions 取文本，快照 text_segments 必须挂在
        一个真实 session 上才能进入日报数据源（否则 session_id=0 被 JOIN 过滤）。"""
        row = conn.execute(
            "SELECT id FROM sessions WHERE process_name='__snapshot__' AND DATE(start_time)=?",
            (today,),
        ).fetchone()
        if row:
            return row[0]
        cur = conn.execute(
            "INSERT INTO sessions (start_time, end_time, process_name, window_title, "
            "idle_seconds, active_seconds, is_filtered) VALUES (?,?,?,?,?,?,0)",
            (today + "T00:00:00", today + "T23:59:59",
             "__snapshot__", "快照采集（Git/Shell/浏览器）", 0, 0),
        )
        conn.commit()
        return cur.lastrowid

    @staticmethod
    def _norm_ts(ts: str) -> str:
        """规整为 naive ISO（主库习惯：YYYY-MM-DDTHH:MM:SS）"""
        if not ts:
            return datetime.now().isoformat(timespec="seconds")
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return d.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
        except Exception:
            return ts
