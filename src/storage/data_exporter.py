"""数据导出器

支持将会话、文本片段、剪贴板记录导出为 CSV / JSON 格式。
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DataExporter:
    """数据导出器"""

    def __init__(self, db):
        self._db = db

    def export_sessions_csv(self, date: str | None = None, output_path: Path | None = None) -> Path:
        """导出会话记录为 CSV
        
        Args:
            date: 指定日期（YYYY-MM-DD），None 则导出全部
            output_path: 输出文件路径，None 则自动生成
            
        Returns: 导出文件路径
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = f"_{date}" if date else "_all"
            output_path = Path(f"export_sessions{suffix}_{timestamp}.csv")

        sessions = self._db.query_sessions(date=date, limit=100000)

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "开始时间", "结束时间", "进程名", "窗口标题",
                "活跃时长(秒)", "空闲时长(秒)", "已过滤", "分类", "文本片段数"
            ])
            for s in sessions:
                seg_count = self._db.count_text_segments(s.id)
                category = getattr(s, "category", "其他") or "其他"
                writer.writerow([
                    s.id, s.start_time, s.end_time or "",
                    s.process_name, s.window_title or "",
                    round(s.active_seconds, 1), round(s.idle_seconds, 1),
                    "是" if s.is_filtered else "否",
                    category, seg_count,
                ])

        logger.info("会话 CSV 导出完成: %s (%d 条)", output_path, len(sessions))
        return output_path

    def export_sessions_json(self, date: str | None = None, output_path: Path | None = None) -> Path:
        """导出会话记录为 JSON（含文本片段）"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = f"_{date}" if date else "_all"
            output_path = Path(f"export_sessions{suffix}_{timestamp}.json")

        sessions = self._db.query_sessions(date=date, limit=100000)
        data = []
        for s in sessions:
            segs = self._db.query_text_segments(s.id)
            category = getattr(s, "category", "其他") or "其他"
            data.append({
                "id": s.id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "process_name": s.process_name,
                "window_title": s.window_title,
                "active_seconds": round(s.active_seconds, 1),
                "idle_seconds": round(s.idle_seconds, 1),
                "is_filtered": s.is_filtered,
                "category": category,
                "text_segments": [
                    {
                        "timestamp": seg.timestamp,
                        "raw_text": seg.raw_text if not seg.is_filtered else "[已过滤]",
                        "source": seg.source,
                        "is_filtered": seg.is_filtered,
                        "char_count": seg.char_count,
                    }
                    for seg in segs
                ],
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"export_time": datetime.now().isoformat(), "sessions": data}, f, ensure_ascii=False, indent=2)

        logger.info("会话 JSON 导出完成: %s (%d 条)", output_path, len(sessions))
        return output_path

    def export_text_segments_csv(self, date: str | None = None, output_path: Path | None = None) -> Path:
        """导出文本片段为 CSV"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = f"_{date}" if date else "_all"
            output_path = Path(f"export_segments{suffix}_{timestamp}.csv")

        if date:
            rows = self._db.query_all_text_for_date(date)
        else:
            # 导出全部需要全表扫描
            with self._db._cursor() as cur:
                cur.execute(
                    """SELECT ts.timestamp, ts.raw_text, ts.source, ts.is_filtered,
                        s.process_name, s.window_title
                        FROM text_segments ts
                        LEFT JOIN sessions s ON ts.session_id = s.id
                        ORDER BY ts.timestamp"""
                )
                all_rows = cur.fetchall()
            rows = [
                {"timestamp": r[0], "text": r[1], "source": r[2],
                 "is_filtered": bool(r[3]), "process_name": r[4] or "",
                 "window_title": r[5] or ""}
                for r in all_rows
            ]

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["时间戳", "文本内容", "来源", "进程名", "窗口标题", "已过滤"])
            for r in rows:
                writer.writerow([
                    r["timestamp"],
                    r.get("text", ""),
                    r.get("source", ""),
                    r.get("process_name", ""),
                    r.get("window_title", ""),
                    "是" if r.get("is_filtered") else "否",
                ])

        logger.info("文本片段 CSV 导出完成: %s (%d 条)", output_path, len(rows))
        return output_path
