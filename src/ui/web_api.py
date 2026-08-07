"""pywebview JS 桥接 API 适配层

把 BlackboxEngine 包装成 JSON-able 输入输出的扁平方法，
供前端经 window.pywebview.api.* 调用。

约束（pywebview 限制）：返回值必须是 dict/list/str/int/float/bool/None，
严禁返回 dataclass 实例或 Path 对象。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_VERSION = "4.1.0"


class BlackboxAPI:
    """JS 桥接 API：持有 engine，对外暴露扁平方法"""

    def __init__(self, engine):
        self._engine = engine
        # 异步任务表：task_id -> {status, result, error}
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._task_seq = 0
        # engine.pause/resume 无状态查询，API 层自行维护
        self._is_paused = False
        self._recording_started_at: str | None = None

    # ==================== 生命周期 ====================

    def ping(self) -> dict:
        """前端 pywebviewready 后首调，确认桥接就绪"""
        return {"ready": True, "version": _APP_VERSION}

    def get_status(self) -> dict:
        """采集状态快照"""
        engine = self._engine
        today = datetime.now().strftime("%Y-%m-%d")
        recording_seconds = 0.0
        segment_count = 0
        try:
            if engine._db.is_connected:
                # 今日累计活跃时长（聚合各应用 active_seconds）
                stats = engine._db.query_app_usage_stats(today)
                recording_seconds = sum(s.get("active_seconds", 0) for s in stats)
                # 今日文本片段数
                segment_count = len(engine._db.query_all_text_for_date(today))
        except Exception:
            logger.exception("读取状态失败")
        return {
            "is_running": engine._running,
            "is_paused": self._is_paused,
            "is_privacy": engine.is_privacy_mode,
            "started_at": self._recording_started_at,
            "recording_seconds": round(recording_seconds, 1),
            "segment_count": segment_count,
            "today": today,
        }

    # ==================== 录制控制（同步） ====================

    def start_recording(self) -> dict:
        try:
            engine = self._engine
            engine.start()
            self._is_paused = False
            self._recording_started_at = datetime.now().isoformat()
            return {"ok": True, "started_at": self._recording_started_at}
        except Exception as e:
            logger.exception("启动录制失败")
            return {"ok": False, "error": str(e)}

    def stop_recording(self) -> dict:
        try:
            self._engine.stop()
            self._is_paused = False
            self._recording_started_at = None
            return {"ok": True}
        except Exception as e:
            logger.exception("停止录制失败")
            return {"ok": False, "error": str(e)}

    def pause_recording(self) -> dict:
        try:
            if not self._engine._running:
                return {"ok": False, "error": "未在录制"}
            self._engine.pause()
            self._is_paused = True
            return {"ok": True, "is_paused": True}
        except Exception as e:
            logger.exception("暂停录制失败")
            return {"ok": False, "error": str(e)}

    def resume_recording(self) -> dict:
        try:
            if not self._is_paused:
                return {"ok": False, "error": "未暂停"}
            self._engine.resume()
            self._is_paused = False
            return {"ok": True, "is_paused": False}
        except Exception as e:
            logger.exception("恢复录制失败")
            return {"ok": False, "error": str(e)}

    def toggle_privacy(self) -> dict:
        try:
            self._engine.toggle_privacy_mode()
            return {"ok": True, "is_privacy": self._engine.is_privacy_mode}
        except Exception as e:
            logger.exception("切换隐私模式失败")
            return {"ok": False, "error": str(e)}

    # ==================== 报告查看（同步） ====================

    def get_available_dates(self, limit: int = 30) -> list:
        engine = self._engine
        if not engine._db.is_connected:
            return []
        try:
            dates = engine._db.query_available_dates(limit=limit)
        except Exception:
            logger.exception("查询日期列表失败")
            dates = []
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in dates:
            dates.insert(0, today)
        return dates

    def get_reported_dates(self, limit: int = 90) -> list:
        """已生成日报的日期列表（用于日历标记）"""
        engine = self._engine
        if not engine._db.is_connected:
            return []
        try:
            return engine._db.query_reported_dates(limit=limit)
        except Exception:
            logger.exception("查询已报告日期失败")
            return []

    def get_report(self, report_type: str, date: str) -> dict | None:
        """查询已生成的报告（daily/weekly/monthly）"""
        engine = self._engine
        if not engine._db.is_connected:
            return None
        record = None
        try:
            if report_type == "daily":
                record = engine.get_daily_report(date)
            elif report_type in ("weekly", "monthly"):
                record = engine.get_period_report(report_type, date)
        except Exception:
            logger.exception("查询报告失败")
            return None
        if not record:
            return None
        return {
            "report_type": report_type,
            "date": date,
            "markdown": record.structured_report or "",
            "model_used": record.model_used or "",
            "generated_at": record.generated_at or "",
            "token_count": getattr(record, "token_count", 0) or 0,
        }

    def has_data_for_date(self, date: str) -> bool:
        """日报预校验：该日期是否有采集数据"""
        engine = self._engine
        if not engine._db.is_connected:
            return False
        try:
            return bool(engine._db.query_sessions(date=date, limit=1))
        except Exception:
            return False

    # ==================== 报告生成（异步任务） ====================

    def generate_report(self, report_type: str, date: str) -> dict:
        """异步生成报告：立即返回 task_id，前端轮询 get_task_status"""
        with self._lock:
            self._task_seq += 1
            task_id = f"task-{self._task_seq}"
            self._tasks[task_id] = {"status": "pending", "result": None, "error": None}
        threading.Thread(
            target=self._gen_worker,
            args=(task_id, report_type, date),
            daemon=True,
            name=f"GenReport-{task_id}",
        ).start()
        return {"task_id": task_id}

    def get_task_status(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            result = dict(task)
            # 已完成/失败的任务，读取后自动清理（防止内存单调增长）
            if task["status"] in ("done", "failed"):
                del self._tasks[task_id]
            return result

    def _gen_worker(self, task_id: str, report_type: str, date: str):
        """报告生成工作线程（复刻 gui.py 的 _gen 逻辑）"""
        engine = self._engine
        try:
            self._set_task(task_id, status="running")

            if not engine._report_generator:
                self._set_task(task_id, status="failed",
                               error="AI 层未初始化，请检查 config.yaml 中的 api_key 配置")
                return

            if report_type == "daily" and not self.has_data_for_date(date):
                self._set_task(task_id, status="failed",
                               error=f"{date} 没有采集数据，无法生成日报")
                return

            if report_type == "daily":
                report = engine.generate_daily_report(date=date)
            elif report_type == "weekly":
                report = engine.generate_weekly_report(date=date)
            elif report_type == "monthly":
                report = engine.generate_monthly_report(date=date)
            else:
                self._set_task(task_id, status="failed", error=f"未知报告类型: {report_type}")
                return

            if not report:
                self._set_task(
                    task_id, status="failed",
                    error="生成失败 — 可能原因: 网络不通 / API Key 失效 / 周报月报需先有日报",
                )
                return

            saved_path = self._save_report(report_type, date, report)
            self._set_task(
                task_id, status="done",
                result={"markdown": report, "saved_path": str(saved_path) if saved_path else ""},
            )
        except Exception as e:
            logger.exception("报告生成工作线程异常")
            self._set_task(task_id, status="failed", error=str(e))

    def _set_task(self, task_id: str, status: str, result=None, error=None):
        with self._lock:
            self._tasks[task_id] = {"status": status, "result": result, "error": error}

    def _save_report(self, report_type: str, target_date: str, report: str) -> Path | None:
        """保存报告到文件（复刻 gui.py:440-465 命名规则）"""
        try:
            report_dir = Path(self._engine._settings.markdown_dir)
            report_dir.mkdir(parents=True, exist_ok=True)

            if report_type == "daily":
                now = datetime.now()
                filename = f"{target_date}_{now.strftime('%H%M%S')}_report.md"
                header = f"# AI 每日报告 - {target_date}"
            elif report_type == "weekly":
                from src.ai.report_generator import _week_range, _week_label
                start, end = _week_range(target_date)
                filename = f"{start}_weekly.md"
                header = f"# AI 周报 - {_week_label(start)} ({start} ~ {end})"
            elif report_type == "monthly":
                from src.ai.report_generator import _month_range, _month_label
                start, end = _month_range(target_date)
                filename = f"{_month_label(start)}_monthly.md"
                header = f"# AI 月报 - {_month_label(start)} ({start} ~ {end})"
            else:
                filename = f"{target_date}_report.md"
                header = f"# AI 报告 - {target_date}"

            report_path = report_dir / filename
            report_path.write_text(f"{header}\n\n{report}", encoding="utf-8")
            return report_path
        except Exception:
            logger.exception("保存报告失败")
            return None

    # ==================== 数据浏览（统计/活动/搜索） ====================

    def get_app_stats(self, range_type: str, date: str) -> dict:
        """应用使用时长统计：range_type = today/week/month"""
        engine = self._engine
        fallback = {"items": [], "total_active": 0,
                    "range": {"start": date, "end": date, "type": range_type}}
        if not engine._db.is_connected:
            return fallback
        try:
            from src.ai.report_generator import _week_range, _month_range
            if range_type == "week":
                start, end = _week_range(date)
            elif range_type == "month":
                start, end = _month_range(date)
            else:
                start = end = date
            items = engine._db.query_app_usage_stats_range(start, end)
            total = sum(it.get("active_seconds", 0) for it in items)
            return {
                "range": {"start": start, "end": end, "type": range_type},
                "items": items,
                "total_active": total,
            }
        except Exception:
            logger.exception("查询应用统计失败")
            return fallback

    def get_sessions(self, date: str) -> list:
        """某日会话列表（含片段计数，便于前端区分有无文本输入）"""
        engine = self._engine
        if not engine._db.is_connected:
            return []
        try:
            rows = engine._db.query_sessions(date=date, limit=500)
            result = []
            for r in rows:
                # 查询该会话的文本片段数
                seg_count = engine._db.count_text_segments(r.id)
                result.append({
                    "id": r.id, "start_time": r.start_time, "end_time": r.end_time,
                    "process_name": r.process_name, "window_title": r.window_title,
                    "active_seconds": r.active_seconds, "idle_seconds": r.idle_seconds,
                    "is_filtered": r.is_filtered,
                    "segment_count": seg_count,
                })
            return result
        except Exception:
            logger.exception("查询会话列表失败")
            return []

    def get_session_detail(self, session_id: int) -> dict | None:
        """会话详情（含文本片段）"""
        engine = self._engine
        if not engine._db.is_connected:
            return None
        try:
            sess = engine._db.query_session_by_id(session_id)
            if not sess:
                return None
            segs = engine._db.query_text_segments(session_id)
            return {
                "session": {
                    "id": sess.id, "start_time": sess.start_time, "end_time": sess.end_time,
                    "process_name": sess.process_name, "window_title": sess.window_title,
                    "active_seconds": sess.active_seconds, "idle_seconds": sess.idle_seconds,
                },
                "segments": [
                    {
                        "timestamp": s.timestamp, "raw_text": s.raw_text,
                        "source": s.source, "is_filtered": s.is_filtered,
                        "char_count": s.char_count,
                    }
                    for s in segs
                ],
            }
        except Exception:
            logger.exception("查询会话详情失败")
            return None

    def search_text(self, keyword: str, limit: int = 50) -> dict:
        """全文搜索历史输入文本"""
        engine = self._engine
        keyword = (keyword or "").strip()
        if not keyword or not engine._db.is_connected:
            return {"keyword": keyword, "results": []}
        try:
            rows = engine._db.search_text(keyword, limit=limit)
            return {"keyword": keyword, "results": rows}
        except Exception:
            logger.exception("全文搜索失败")
            return {"keyword": keyword, "results": []}

    # ==================== 分类统计 ====================

    def get_category_stats(self, range_type: str, date: str) -> dict:
        """按分类统计使用时长：range_type = today/week/month"""
        engine = self._engine
        fallback = {"items": [], "total_active": 0,
                    "range": {"start": date, "end": date, "type": range_type}}
        if not engine._db.is_connected:
            return fallback
        try:
            from src.ai.report_generator import _week_range, _month_range
            if range_type == "week":
                start, end = _week_range(date)
            elif range_type == "month":
                start, end = _month_range(date)
            else:
                start = end = date
            items = engine._db.query_category_stats(start_date=start, end_date=end)
            total = sum(it.get("active_seconds", 0) for it in items)
            return {
                "range": {"start": start, "end": end, "type": range_type},
                "items": items,
                "total_active": total,
            }
        except Exception:
            logger.exception("查询分类统计失败")
            return fallback

    def backfill_categories(self) -> dict:
        """回填历史会话的分类"""
        try:
            engine = self._engine
            if not engine._db.is_connected:
                return {"ok": False, "error": "数据库未连接"}
            updated = engine._db.backfill_categories()
            return {"ok": True, "updated": updated}
        except Exception as e:
            logger.exception("回填分类失败")
            return {"ok": False, "error": str(e)}

    def get_categories(self) -> list:
        """获取所有预置分类"""
        from src.processor.app_classifier import AppClassifier
        classifier = AppClassifier()
        return classifier.get_all_categories()

    def convert_pinyin(self, text: str) -> dict:
        """将文本中的拼音转换为汉字（仅展示用，不修改原始数据）"""
        try:
            from src.processor.pinyin_converter import convert_pinyin_to_hanzi, has_convertible_pinyin
            converted = convert_pinyin_to_hanzi(text)
            return {
                "original": text,
                "converted": converted,
                "has_pinyin": has_convertible_pinyin(text),
                "changed": converted != text,
            }
        except Exception as e:
            logger.exception("拼音转换失败")
            return {"original": text, "converted": text, "has_pinyin": False, "changed": False}

    # ==================== 待办事项（提取走异步任务，CRUD 同步） ====================

    def extract_todos(self, report_type: str, date: str) -> dict:
        """异步从报告提取待办：立即返回 task_id，前端轮询 get_task_status

        结果 result: {"extracted": int}
        """
        with self._lock:
            self._task_seq += 1
            task_id = f"task-{self._task_seq}"
            self._tasks[task_id] = {"status": "pending", "result": None, "error": None}
        threading.Thread(
            target=self._extract_todos_worker,
            args=(task_id, report_type, date),
            daemon=True,
            name=f"ExtractTodo-{task_id}",
        ).start()
        return {"task_id": task_id}

    def _extract_todos_worker(self, task_id: str, report_type: str, date: str):
        """待办提取工作线程"""
        engine = self._engine
        try:
            self._set_task(task_id, status="running")
            if not engine._todo_extractor:
                self._set_task(task_id, status="failed",
                               error="AI 层未初始化，请检查 config.yaml 中的 api_key 配置")
                return
            result = engine.extract_todos_from_report(report_type, date)
            if not result.get("ok"):
                self._set_task(task_id, status="failed", error=result.get("error", "提取失败"))
                return
            self._set_task(task_id, status="done",
                           result={"extracted": result.get("extracted", 0)})
        except Exception as e:
            logger.exception("待办提取工作线程异常")
            self._set_task(task_id, status="failed", error=str(e))

    def get_todos(self, status: str | None = None, include_drafts: bool = True,
                  source_ref: str | None = None) -> list:
        """查询待办列表"""
        engine = self._engine
        if not engine._db.is_connected:
            return []
        try:
            rows = engine._db.query_todos(status=status, include_drafts=include_drafts,
                                          source_ref=source_ref)
            return [self._todo_to_dict(t) for t in rows]
        except Exception:
            logger.exception("查询待办列表失败")
            return []

    def get_todo(self, todo_id: int) -> dict | None:
        """查询单个待办"""
        engine = self._engine
        if not engine._db.is_connected:
            return None
        try:
            t = engine._db.query_todo(int(todo_id))
            return self._todo_to_dict(t) if t else None
        except Exception:
            logger.exception("查询待办失败")
            return None

    def add_todo(self, title: str, priority: str = "normal", due_date: str = "",
                 note: str = "") -> dict:
        """手动新建待办（非草稿，直接正式入库）"""
        from src.storage.models import TodoRecord
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        title = (title or "").strip()
        if not title:
            return {"ok": False, "error": "待办内容不能为空"}
        try:
            now = datetime.now().isoformat()
            todo_id = engine._db.insert_todo(TodoRecord(
                title=title[:200],
                priority=priority if priority in ("low", "normal", "high", "urgent") else "normal",
                due_date=due_date or "",
                note=note or "",
                source_type="manual",
                is_draft=False,
                created_at=now,
                updated_at=now,
            ))
            return {"ok": True, "id": todo_id}
        except Exception as e:
            logger.exception("新建待办失败")
            return {"ok": False, "error": str(e)}

    def update_todo(self, todo_id: int, fields: dict) -> dict:
        """更新待办字段（status 变 done 自动记录 completed_at）

        Args:
            fields: {title/status/priority/note/due_date/is_draft/...}
        """
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            todo_id = int(todo_id)
            fields = dict(fields or {})
            status = fields.get("status")
            if status == "done":
                fields.setdefault("completed_at", datetime.now().isoformat())
            elif status in ("pending", "in_progress", "cancelled"):
                fields["completed_at"] = ""
            fields["updated_at"] = datetime.now().isoformat()
            ok = engine._db.update_todo(todo_id, fields)
            return {"ok": ok}
        except Exception as e:
            logger.exception("更新待办失败")
            return {"ok": False, "error": str(e)}

    def adopt_todos(self, todo_ids: list) -> dict:
        """批量采纳草稿待办（is_draft: 1 → 0，转为正式待办）"""
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            now = datetime.now().isoformat()
            adopted = 0
            for tid in (todo_ids or []):
                if engine._db.update_todo(int(tid), {"is_draft": False, "updated_at": now}):
                    adopted += 1
            return {"ok": True, "adopted": adopted}
        except Exception as e:
            logger.exception("采纳待办失败")
            return {"ok": False, "error": str(e)}

    def delete_todo(self, todo_id: int) -> dict:
        """删除待办"""
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            ok = engine._db.delete_todo(int(todo_id))
            return {"ok": ok}
        except Exception as e:
            logger.exception("删除待办失败")
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _todo_to_dict(t) -> dict:
        """TodoRecord → JSON-able dict（pywebview 不能返回 dataclass）"""
        return {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "note": t.note,
            "due_date": t.due_date,
            "source_type": t.source_type,
            "source_ref": t.source_ref,
            "is_draft": t.is_draft,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "completed_at": t.completed_at,
        }

    # ==================== API 配置（脱敏） ====================

    def get_api_config(self) -> dict:
        engine = self._engine
        ai = engine._settings.ai
        provider = ai.get("default_provider", "")
        prov_cfg = ai.get(provider, {}) if provider else {}
        api_key = prov_cfg.get("api_key", "")
        has_key = bool(api_key)
        # 脱敏：仅显示末 4 位
        if len(api_key) >= 4:
            key_masked = f"***{api_key[-4:]}"
        elif api_key:
            key_masked = "***"
        else:
            key_masked = ""
        return {
            "provider": provider,
            "base_url": prov_cfg.get("base_url", ""),
            "model": prov_cfg.get("model", ""),
            "has_key": has_key,
            "key_masked": key_masked,
            "ai_available": engine._report_generator is not None,
        }

    def save_api_config(self, provider: str, base_url: str, model: str, api_key: str) -> dict:
        """保存 AI 配置到 config.yaml（重启生效，不热重载）

        api_key 留空则保留原值，避免误清空已配置的 Key。
        """
        import shutil
        import yaml
        from src.main import get_app_root

        try:
            provider = (provider or "").strip()
            if not provider:
                return {"ok": False, "error": "提供商不能为空"}
            config_path = get_app_root() / "config" / "config.yaml"
            if not config_path.exists():
                return {"ok": False, "error": f"配置文件不存在: {config_path}"}

            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            # 备份原文件（保留原注释）
            bak = config_path.with_suffix(".yaml.bak")
            shutil.copy2(config_path, bak)

            ai = cfg.setdefault("ai", {})
            if not api_key:
                api_key = ai.get(provider, {}).get("api_key", "")
            ai["default_provider"] = provider
            ai[provider] = {
                "api_key": api_key or "",
                "model": model or "",
                "base_url": (base_url or "").rstrip("/"),
            }

            with open(config_path, "w", encoding="utf-8") as f:
                f.write("# Personal Work Blackbox 配置文件\n")
                f.write("# 由设置页编辑，原注释版本见 config.yaml.bak\n")
                f.write("# 修改后需重启应用生效\n\n")
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            return {"ok": True, "restart_needed": True, "backup": str(bak)}
        except Exception as e:
            logger.exception("保存 AI 配置失败")
            return {"ok": False, "error": str(e)}

    def test_api_config(self, provider: str, base_url: str, model: str, api_key: str) -> dict:
        """测试连接（不保存）：TCP 连通性 + 最小 chat 请求验证 Key/模型"""
        import asyncio
        from src.ai.llm_client import OpenAICompatibleProvider

        try:
            if not (base_url and model and api_key):
                return {"ok": False, "error": "Base URL / 模型 / API Key 不能为空"}
            p = OpenAICompatibleProvider(
                provider or "test",
                {"api_key": api_key, "model": model, "base_url": base_url},
            )
            ok, msg = p.test_connectivity()
            if not ok:
                return {"ok": False, "error": msg}

            asyncio.run(p.complete([{"role": "user", "content": "ping"}]))
            return {"ok": True, "detail": "连接成功，API Key 与模型有效"}
        except Exception as e:
            logger.exception("测试连接失败")
            return {"ok": False, "error": f"连接失败: {type(e).__name__}: {e}"}

    # ==================== 辅助 ====================

    def open_report_file(self, report_type: str, date: str) -> dict:
        import os
        report_dir = Path(self._engine._settings.markdown_dir)
        if report_type == "daily":
            files = sorted(report_dir.glob(f"{date}_*_report.md"), reverse=True)
        elif report_type == "weekly":
            from src.ai.report_generator import _week_range
            start, _ = _week_range(date)
            files = sorted(report_dir.glob(f"{start}_weekly.md"), reverse=True)
        elif report_type == "monthly":
            from src.ai.report_generator import _month_label
            label = _month_label(date)
            files = sorted(report_dir.glob(f"{label}_monthly.md"), reverse=True)
        else:
            files = []
        if files:
            os.startfile(str(files[0]))
            return {"ok": True, "path": files[0].name}
        return {"ok": False, "error": "报告文件不存在"}

    def open_data_dir(self) -> dict:
        import os
        data_dir = Path(self._engine._settings.markdown_dir).parent
        data_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(data_dir.resolve()))
        return {"ok": True}

    def export_data(self, format: str, data_type: str, date: str | None = None) -> dict:
        """导出数据
        
        Args:
            format: csv / json
            data_type: sessions / segments
            date: 指定日期（可选）
        """
        try:
            from src.storage.data_exporter import DataExporter
            from src.main import get_app_root
            
            exporter = DataExporter(self._engine._db)
            
            # 导出到 data/exports/ 目录
            export_dir = get_app_root() / "data" / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = f"_{date}" if date else "_all"
            filename = f"export_{data_type}{suffix}_{timestamp}.{format}"
            output_path = export_dir / filename
            
            if data_type == "sessions":
                if format == "csv":
                    path = exporter.export_sessions_csv(date=date, output_path=output_path)
                elif format == "json":
                    path = exporter.export_sessions_json(date=date, output_path=output_path)
                else:
                    return {"ok": False, "error": f"不支持的格式: {format}"}
            elif data_type == "segments":
                if format == "csv":
                    path = exporter.export_text_segments_csv(date=date, output_path=output_path)
                elif format == "json":
                    # segments JSON = sessions JSON 的简化版
                    path = exporter.export_sessions_json(date=date, output_path=output_path)
                else:
                    return {"ok": False, "error": f"不支持的格式: {format}"}
            else:
                return {"ok": False, "error": f"不支持的数据类型: {data_type}"}
            
            return {"ok": True, "path": str(path), "filename": filename}
        except Exception as e:
            logger.exception("导出数据失败")
            return {"ok": False, "error": str(e)}

    def export_report(self, format: str, report_type: str, date: str) -> dict:
        """导出报告为单文件 HTML（PDF 走前端 window.print，不经此接口）

        Args:
            format: html（其他值回退提示用前端打印）
            report_type: daily / weekly / monthly
            date: 报告日期
        """
        try:
            from src.storage.report_exporter import render_report_html
            from src.main import get_app_root

            rep = self.get_report(report_type, date)
            if not rep or not rep.get("markdown"):
                return {"ok": False, "error": "报告不存在或无内容，请先生成报告"}
            if format != "html":
                return {"ok": False, "error": "PDF 请点「导出 PDF」用打印另存"}

            type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(report_type, "报告")
            title = f"职迹{type_label} · {date}"
            parts = []
            if rep.get("model_used"):
                parts.append(f"模型 {rep['model_used']}")
            if rep.get("generated_at"):
                parts.append(f"生成于 {rep['generated_at'][:16].replace('T', ' ')}")
            subtitle = " · ".join(parts)

            export_dir = get_app_root() / "data" / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            filename = f"export_{report_type}_{date}_report.html"
            path = export_dir / filename
            path.write_text(
                render_report_html(rep["markdown"], title, subtitle),
                encoding="utf-8",
            )
            return {"ok": True, "path": str(path), "filename": filename}
        except Exception as e:
            logger.exception("导出报告失败")
            return {"ok": False, "error": str(e)}

    def export_todos(self, status: str | None = None, include_drafts: bool = True) -> dict:
        """导出待办列表为 CSV（utf-8-sig，Excel/飞书多维表格直接打开）

        Args:
            status: 按状态过滤（None = 全部），与待办视图当前筛选一致
            include_drafts: 是否包含草稿区
        """
        try:
            from src.storage.data_exporter import DataExporter
            from src.main import get_app_root

            rows = self._engine._db.query_todos(status=status, include_drafts=include_drafts)
            exporter = DataExporter(self._engine._db)

            export_dir = get_app_root() / "data" / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"export_todos_{timestamp}.csv"
            path = exporter.export_todos_csv(rows, output_path=export_dir / filename)
            return {"ok": True, "path": str(path), "filename": filename, "count": len(rows)}
        except Exception as e:
            logger.exception("导出待办失败")
            return {"ok": False, "error": str(e)}

    # ==================== 专注模式 ====================

    def start_focus_session(self, goal: str, duration_minutes: int) -> dict:
        """启动专注会话"""
        try:
            engine = self._engine
            if not engine._focus_mode:
                return {"ok": False, "error": "专注模式未初始化"}
            session = engine._focus_mode.start_focus_session(goal, duration_minutes)
            return {"ok": True, "session": session.to_dict()}
        except Exception as e:
            logger.exception("启动专注会话失败")
            return {"ok": False, "error": str(e)}

    def stop_focus_session(self) -> dict:
        """停止专注会话"""
        try:
            engine = self._engine
            if not engine._focus_mode:
                return {"ok": False, "error": "专注模式未初始化"}
            result = engine._focus_mode.stop_focus_session()
            return {"ok": True, "session": result}
        except Exception as e:
            logger.exception("停止专注会话失败")
            return {"ok": False, "error": str(e)}

    def get_focus_session(self) -> dict | None:
        """获取当前专注会话状态"""
        try:
            engine = self._engine
            if not engine._focus_mode:
                return None
            return engine._focus_mode.get_focus_session()
        except Exception:
            return None

    def get_daily_efficiency(self) -> dict:
        """获取今日效率统计"""
        try:
            engine = self._engine
            if not engine._focus_mode:
                return {"work_seconds": 0, "distraction_seconds": 0, "goal_progress": 0}
            return engine._focus_mode.get_daily_stats()
        except Exception:
            return {"work_seconds": 0, "distraction_seconds": 0, "goal_progress": 0}

    def set_daily_goal(self, minutes: int) -> dict:
        """设置每日工作目标"""
        try:
            engine = self._engine
            if not engine._focus_mode:
                return {"ok": False, "error": "专注模式未初始化"}
            engine._focus_mode.set_daily_goal(minutes)
            return {"ok": True, "daily_goal_minutes": minutes}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ==================== 隐私告知同意状态 ====================

    def get_consent_status(self) -> dict:
        """检查用户是否已同意隐私告知"""
        import os
        from src.main import get_app_root
        consent_file = get_app_root() / "data" / ".consent"
        if consent_file.exists():
            try:
                import json
                data = json.loads(consent_file.read_text(encoding="utf-8"))
                return {"consented": True, "window_only": data.get("window_only", False), "timestamp": data.get("timestamp", "")}
            except Exception:
                pass
        return {"consented": False, "window_only": False, "timestamp": ""}

    def set_consent(self, window_only: bool) -> dict:
        """记录用户同意隐私告知"""
        import json
        from datetime import datetime
        from src.main import get_app_root
        try:
            consent_file = get_app_root() / "data" / ".consent"
            consent_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "consented": True,
                "window_only": bool(window_only),
                "timestamp": datetime.now().isoformat(),
            }
            consent_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return {"ok": True}
        except Exception as e:
            logger.exception("保存同意状态失败")
            return {"ok": False, "error": str(e)}

    def shutdown(self) -> None:
        try:
            self._engine.shutdown()
        except Exception:
            logger.exception("shutdown 异常")
