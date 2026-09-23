"""速记 → 洞察收件箱落盘（v5.4，源自本地 v4.5「洞察速记」能力）

速记保存时双写：
1. 职迹数据库 notes 表（可搜索/统计/标签云，见 database.py）
2. 收件箱 Markdown 文件（本模块）：写入用户配置的「每日洞察」收件箱目录，
   供 AI 蒸馏工作流增量处理；文件只增不改（与「日常记录」档案契约一致）。

文件名：YYYY-MM-DD_HHMM.md（同分钟冲突自动加序号）
落盘失败仅记日志，不影响速记入库（优雅降级）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_tags(tags) -> str:
    """标签输入归一化：None / 列表 / 逗号（中英文）分隔字符串 → 去重逗号串"""
    if tags is None:
        return ""
    if isinstance(tags, (list, tuple)):
        parts = [str(t).strip() for t in tags]
    else:
        parts = [t.strip() for t in re.split(r"[,，]", str(tags))]
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return ",".join(seen)


def split_tags(tags) -> list[str]:
    """标签串 → 标签列表（供标签云/筛选用）"""
    return [t for t in normalize_tags(tags).split(",") if t]


def save_to_inbox(content: str, tags, created_at: str, inbox_dir: str | Path) -> str:
    """把一条速记写成收件箱 Markdown 文件，返回文件路径字符串（失败返回 ""）

    Args:
        content: 速记内容
        tags: 标签（字符串/列表，逗号分隔）
        created_at: ISO8601 时间戳（文件名与 frontmatter 依据）
        inbox_dir: 收件箱目录（不存在则创建）；空值直接返回 ""
    """
    if not inbox_dir:
        return ""
    try:
        inbox = Path(inbox_dir)
        inbox.mkdir(parents=True, exist_ok=True)

        try:
            dt = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            dt = datetime.now()

        base = dt.strftime("%Y-%m-%d_%H%M")
        path = inbox / f"{base}.md"
        seq = 1
        while path.exists():
            path = inbox / f"{base}_{seq}.md"
            seq += 1

        tag_list = split_tags(tags)
        time_label = dt.strftime("%Y-%m-%d %H:%M")
        lines = [
            "---",
            "type: 洞察",
            f"created: {created_at}",
            f"tags: [{', '.join(tag_list)}]",
            "source: 职迹速记",
            "---",
            "",
            f"# {time_label} 洞察",
            "",
            content.strip(),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("速记已落盘洞察收件箱: %s", path)
        return str(path)
    except Exception:
        logger.exception("速记落盘洞察收件箱失败")
        return ""


def count_inbox_files(inbox_dir: str | Path) -> int:
    """统计收件箱目录下待处理 Markdown 文件数（配置页连接状态用）"""
    if not inbox_dir:
        return 0
    try:
        p = Path(inbox_dir)
        if not p.is_dir():
            return 0
        return sum(1 for f in p.glob("*.md"))
    except Exception:
        return 0


def inbox_status(inbox_dir: str | Path) -> dict:
    """收件箱连接状态：{configured, exists, writable, count, dir}"""
    dir_str = str(inbox_dir or "")
    if not dir_str:
        return {"configured": False, "exists": False, "writable": False,
                "count": 0, "dir": ""}
    try:
        p = Path(dir_str)
        exists = p.is_dir()
        writable = exists and _probe_writable(p)
        return {
            "configured": True,
            "exists": exists,
            "writable": writable,
            "count": count_inbox_files(p) if exists else 0,
            "dir": dir_str,
        }
    except Exception:
        return {"configured": True, "exists": False, "writable": False,
                "count": 0, "dir": dir_str}


def _probe_writable(directory: Path) -> bool:
    """实际探测目录可写（比 os.access 可靠，兼容只读挂载/权限受限）"""
    probe = directory / ".wt_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False
