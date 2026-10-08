"""pywebview JS 桥接 API 适配层

把 BlackboxEngine 包装成 JSON-able 输入输出的扁平方法，
供前端经 window.pywebview.api.* 调用。

约束（pywebview 限制）：返回值必须是 dict/list/str/int/float/bool/None，
严禁返回 dataclass 实例或 Path 对象。
"""

from __future__ import annotations

import logging
import json
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_APP_VERSION = "V5.79.0914"


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
        # pywebview 窗口引用（由 web_ui 在创建窗口后注入，用于文件保存对话框等）
        self._window = None
        # 定时任务只保留一个正在执行的文档提取，避免 20 秒轮询重复发起网络请求。
        self._tencent_scheduled_task: dict | None = None
        self._tencent_next_retry_at = 0.0
        self._tencent_scheduler = threading.Thread(target=self._tencent_schedule_loop, daemon=True, name="TencentDocSchedule")
        self._tencent_scheduler.start()

    def _tencent_schedule_path(self) -> Path:
        return Path(self._engine._settings._app_root) / "config" / "tencent_doc_schedule.json"

    def _read_tencent_schedule(self) -> dict:
        try:
            value = json.loads(self._tencent_schedule_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}

        # 兼容 V5.49-V5.53 的单链接配置，并在首次读取时以链接库形式返回。
        documents = value.get("documents")
        if not isinstance(documents, list):
            old_url = str(value.get("url") or "").strip()
            documents = []
            if old_url:
                documents.append({
                    "id": "legacy-" + uuid.uuid5(uuid.NAMESPACE_URL, old_url).hex[:12],
                    "name": "已保存的腾讯文档",
                    "url": old_url,
                    "enabled": bool(value.get("enabled")),
                    "last_run_date": str(value.get("last_run_date") or ""),
                    "last_run_at": str(value.get("last_run_at") or ""),
                    "last_run_status": str(value.get("last_run_status") or ""),
                    "last_run_message": str(value.get("last_run_message") or "")[:200],
                    "created_at": "",
                    "updated_at": "",
                })
            value = {"documents": documents, "selected_id": documents[0]["id"] if documents else ""}

        clean_documents = []
        for item in documents:
            if not isinstance(item, dict) or not str(item.get("url") or "").strip():
                continue
            clean_documents.append({
                "id": str(item.get("id") or uuid.uuid4().hex[:12]),
                "name": str(item.get("name") or "未命名腾讯文档").strip()[:80],
                "url": str(item.get("url") or "").strip(),
                "enabled": bool(item.get("enabled")),
                "last_run_date": str(item.get("last_run_date") or ""),
                "last_run_at": str(item.get("last_run_at") or ""),
                "last_run_status": str(item.get("last_run_status") or ""),
                "last_run_message": str(item.get("last_run_message") or "")[:200],
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
            })
        selected_id = str(value.get("selected_id") or "")
        if selected_id not in {item["id"] for item in clean_documents}:
            selected_id = clean_documents[0]["id"] if clean_documents else ""
        return {"documents": clean_documents, "selected_id": selected_id}

    @staticmethod
    def _selected_tencent_document(schedule: dict) -> dict | None:
        selected_id = schedule.get("selected_id")
        return next((item for item in schedule.get("documents", []) if item.get("id") == selected_id), None)

    def _write_tencent_schedule(self, value: dict) -> None:
        path = self._tencent_schedule_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def _tencent_schedule_loop(self) -> None:
        """应用运行期间每天 09:00 后同步一次，仅写入待确认草稿。"""
        while True:
            try:
                self._tencent_schedule_tick()
            except Exception:
                logger.exception("腾讯文档定时识别检查失败")
            time.sleep(20)

    def _tencent_schedule_tick(self, now: datetime | None = None) -> None:
        """执行一次定时任务检查。09:00 后首次运行会补跑，成功后才记为已运行。"""
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")
        schedule = self._read_tencent_schedule()
        selected = self._selected_tencent_document(schedule)
        if not selected or not selected.get("enabled") or (now.hour, now.minute) < (9, 0):
            return

        active = self._tencent_scheduled_task
        if active and active["date"] == today and active["document_id"] == selected["id"]:
            task = self.get_task_status(active["task_id"])
            if task and task["status"] in ("pending", "running"):
                return
            self._tencent_scheduled_task = None
            selected["last_run_at"] = now.isoformat(timespec="seconds")
            if task and task["status"] == "done":
                result = task.get("result") or {}
                selected["last_run_date"] = today
                selected["last_run_status"] = "done"
                selected["last_run_message"] = (
                    f"已识别 {result.get('recognized', 0)} 条，新增 {result.get('extracted', 0)} 条，"
                    f"重复 {result.get('skipped_duplicates', 0)} 条"
                )
                logger.info("腾讯文档定时识别完成：%s", selected["last_run_message"])
            else:
                selected["last_run_status"] = "failed"
                selected["last_run_message"] = str((task or {}).get("error") or "任务状态丢失")[:200]
                self._tencent_next_retry_at = time.monotonic() + 300
                logger.warning("腾讯文档定时识别失败，5 分钟后重试：%s", selected["last_run_message"])
            self._write_tencent_schedule(schedule)
            return

        if selected.get("last_run_date") == today or time.monotonic() < self._tencent_next_retry_at:
            return

        response = self.extract_todos_from_tencent_doc(selected["url"])
        task_id = response.get("task_id")
        selected["last_run_at"] = now.isoformat(timespec="seconds")
        if not task_id:
            selected["last_run_status"] = "failed"
            selected["last_run_message"] = str(response.get("error") or "无法启动定时识别")[:200]
            self._tencent_next_retry_at = time.monotonic() + 300
            self._write_tencent_schedule(schedule)
            return
        self._tencent_scheduled_task = {"date": today, "document_id": selected["id"], "task_id": task_id}
        selected["last_run_status"] = "running"
        selected["last_run_message"] = "正在识别，完成后将自动更新"
        self._write_tencent_schedule(schedule)
        logger.info("已触发每日腾讯文档待办识别（含补跑）：%s", today)

    def bind_window(self, window) -> None:
        """注入 pywebview 窗口引用（create_file_dialog 等需要）"""
        self._window = window

    # ==================== 生命周期 ====================

    def ping(self) -> dict:
        """前端 pywebviewready 后首调，确认桥接就绪"""
        return {"ready": True, "version": _APP_VERSION}

    def check_permissions(self) -> dict:
        """检测系统权限状态（macOS 辅助功能授权）

        macOS 键盘监听（CGEventTap）与窗口标题采集（AXUIElement）需辅助功能权限，
        未授权时返回 needs_permission=True，前端据此显示授权引导。
        Windows 无需此项权限，始终返回 granted=True。
        """
        import platform as _platform
        plat = _platform.system().lower()
        # 这里必须只反映 macOS 对当前 WorkTrace.app 的真实 AX 授权状态。
        # CGEventTap 能运行只说明按键钩子可用，不能说明外部应用的窗口/输入框
        # 已可通过 AXUIElement 读取；两者混用会把“外部文字无法采集”伪装成已授权。
        accessibility_granted = True
        input_monitoring_granted = True
        screen_recording_granted = True
        collector_active = False
        if plat == "darwin":
            try:
                from ApplicationServices import AXIsProcessTrusted
                accessibility_granted = bool(AXIsProcessTrusted())
            except Exception:
                accessibility_granted = False

            try:
                import Quartz
                preflight_input = getattr(Quartz, "CGPreflightListenEventAccess", None)
                input_monitoring_granted = bool(preflight_input()) if callable(preflight_input) else False
            except Exception:
                input_monitoring_granted = False

            # Independent probes: failure in one permission API must not
            # invalidate a successful result from another permission API.
            try:
                import Quartz
                screen_recording_granted = bool(Quartz.CGPreflightScreenCaptureAccess())
            except Exception:
                screen_recording_granted = False

            hook = getattr(self._engine, "_keyboard_hook", None)
            collector_active = bool(hook and hook.is_alive)
        return {
            "platform": "macos" if plat == "darwin" else "windows",
            "accessibility_granted": accessibility_granted,
            "needs_permission": (plat == "darwin" and not accessibility_granted),
            "collector_active": collector_active,
            "input_monitoring_granted": input_monitoring_granted,
            "screen_recording_granted": screen_recording_granted,
        }

    def request_accessibility_permission(self) -> dict:
        """请求 macOS 为当前已运行的 App 显示辅助功能授权入口。

        不会修改系统权限；仅由 macOS 显示授权提示/设置页，用户可在那里确认。
        单独提供此方法，避免普通状态轮询反复触发系统提示。
        """
        import platform as _platform

        if _platform.system().lower() != "darwin":
            return {"requested": False, "supported": False}

        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )

            granted = bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
            return {"requested": True, "supported": True, "granted": granted}
        except Exception:
            logger.exception("请求辅助功能授权入口失败")
            return {"requested": False, "supported": True, "granted": False}

    def open_screen_recording_settings(self) -> dict:
        """打开 macOS 屏幕与系统音频录制设置页。

        外部 App 未公开 AX 输入框时，本地 OCR 回退需要这一独立授权；本方法
        只导航到系统设置，开关始终由用户在 macOS 中确认。
        """
        import platform as _platform

        if _platform.system().lower() != "darwin":
            return {"opened": False, "supported": False}
        try:
            subprocess.Popen([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            ])
            return {"opened": True, "supported": True}
        except Exception:
            logger.exception("打开屏幕录制设置失败")
            return {"opened": False, "supported": True}

    def request_input_monitoring_permission(self) -> dict:
        """请求 macOS 输入监控授权入口。

        物理键盘回退依赖此权限，且与辅助功能、屏幕录制均为独立开关。
        该调用只交给 macOS 显示原生授权提示，绝不自行修改系统开关。
        """
        import platform as _platform

        if _platform.system().lower() != "darwin":
            return {"requested": False, "supported": False, "granted": False}
        try:
            import Quartz
            preflight = getattr(Quartz, "CGPreflightListenEventAccess", None)
            request = getattr(Quartz, "CGRequestListenEventAccess", None)
            if not callable(preflight) or not callable(request):
                return {"requested": False, "supported": False, "granted": False}
            if not preflight():
                request()
            return {"requested": True, "supported": True, "granted": bool(preflight())}
        except Exception:
            logger.exception("请求输入监控授权入口失败")
            return {"requested": False, "supported": True, "granted": False}

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
            # 只回传来源、时间、长度，绝不在状态接口暴露用户输入内容。
            "last_ime_record": getattr(engine, "_last_ime_record", None),
            "last_capture_record": getattr(engine, "_last_capture_record", None),
            "ime_listener": engine._ime_watcher.status() if getattr(engine, "_ime_watcher", None) else {"source": "", "state": "stopped"},
            "keyboard_listener": engine._keyboard_hook.status() if getattr(engine, "_keyboard_hook", None) else {"active": False, "event_count": 0},
        }

    def record_webview_ime_text(self, text: str) -> dict:
        """记录 WorkTrace 网页控件已确认的豆包/搜狗输入结果。

        WebView 的焦点控件在部分 macOS 上不向 AX 根节点公开 AXValue。前端只会
        在 compositionend 后把 InputEvent.data（最终上屏片段）交给此方法，
        不传整段输入框内容，也不会处理密码框。
        """
        value = str(text or "").strip()
        watcher = getattr(self._engine, "_ime_watcher", None)
        # WebView 的 compositionend 可能比 100ms 轮询更早到达，直接刷新一次
        # 当前输入源，避免因 watcher 状态尚未更新而丢弃真实的搜狗/豆包确认结果。
        source = ""
        if watcher:
            try:
                from src.collector.ime_watcher import _monitored_input_source
                source = _monitored_input_source(watcher._current_input_source_id())
                watcher._last_source = source
            except Exception:
                source = watcher.status().get("source", "")
        if source not in {"doubao_ime", "sogou_ime"}:
            return {"ok": False, "ignored": "unmonitored_input_source"}
        if not value or len(value) > 1000:
            return {"ok": False, "ignored": "empty_or_too_long"}

        from src.collector.keyboard_hook import KeyEvent, KeyEventType

        event = KeyEvent(KeyEventType.PRESS, key=None, char=value,
                         is_ime_composition=True, is_final_ime_result=True)
        event.input_source = source
        self._engine._on_keyboard_event(event)
        return {"ok": True, "source": source, "char_count": len(value)}

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
            # 日报生成成功后，后台静默生成待办推进建议（不阻断报告返回；仅日报，P2 §4.6）
            if report_type == "daily" and self._engine._todo_extractor:
                threading.Thread(
                    target=self._gen_advices_silent, args=(date,),
                    daemon=True, name="AutoAdvice",
                ).start()
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

    def extract_todos_from_tencent_doc(self, url: str) -> dict:
        """从公开腾讯文档链接提取待办，结果先进入草稿区。"""
        with self._lock:
            self._task_seq += 1
            task_id = f"task-{self._task_seq}"
            self._tasks[task_id] = {"status": "pending", "result": None, "error": None}
        threading.Thread(
            target=self._extract_tencent_doc_worker, args=(task_id, url), daemon=True,
            name=f"TencentDocTodo-{task_id}",
        ).start()
        return {"task_id": task_id}

    def get_tencent_doc_schedule(self) -> dict:
        """返回本地保存的腾讯文档自动识别设置（不含任何登录凭据）。"""
        schedule = self._read_tencent_schedule()
        selected = self._selected_tencent_document(schedule) or {}
        return {
            **schedule,
            "url": selected.get("url", ""),
            "enabled": bool(selected.get("enabled")),
            "last_run_date": selected.get("last_run_date", ""),
        }

    def save_tencent_doc_schedule(self, url: str, enabled: bool = True, name: str = "", document_id: str = "") -> dict:
        """新增或更新本地腾讯文档链接库中的一条记录。"""
        from src.processor.tencent_doc import validate_tencent_doc_url
        try:
            schedule = self._read_tencent_schedule()
            safe_url = validate_tencent_doc_url(url)
            now = datetime.now().isoformat(timespec="seconds")
            documents = schedule["documents"]
            current = next((item for item in documents if item["id"] == document_id), None)
            # 未指定 ID 时，相同链接视为更新，避免重复保存。
            current = current or next((item for item in documents if item["url"] == safe_url), None)
            display_name = str(name or "").strip()[:80] or (current or {}).get("name") or "未命名腾讯文档"
            if current:
                current.update({"name": display_name, "url": safe_url, "enabled": bool(enabled), "updated_at": now})
            else:
                current = {
                    "id": uuid.uuid4().hex[:12], "name": display_name, "url": safe_url,
                    "enabled": bool(enabled), "last_run_date": "", "created_at": now, "updated_at": now,
                }
                documents.append(current)
            schedule["selected_id"] = current["id"]
            self._write_tencent_schedule(schedule)
            return {"ok": True, "schedule": self.get_tencent_doc_schedule()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def select_tencent_doc_schedule(self, document_id: str) -> dict:
        """选中链接库中的一条文档，供手动提取和每日自动识别使用。"""
        schedule = self._read_tencent_schedule()
        if not any(item["id"] == document_id for item in schedule["documents"]):
            return {"ok": False, "error": "未找到该腾讯文档链接"}
        schedule["selected_id"] = document_id
        self._write_tencent_schedule(schedule)
        return {"ok": True, "schedule": self.get_tencent_doc_schedule()}

    def delete_tencent_doc_schedule(self, document_id: str) -> dict:
        """从本地链接库删除一条腾讯文档记录，不影响已导入的待办。"""
        schedule = self._read_tencent_schedule()
        remaining = [item for item in schedule["documents"] if item["id"] != document_id]
        if len(remaining) == len(schedule["documents"]):
            return {"ok": False, "error": "未找到该腾讯文档链接"}
        schedule["documents"] = remaining
        if schedule.get("selected_id") == document_id:
            schedule["selected_id"] = remaining[0]["id"] if remaining else ""
        self._write_tencent_schedule(schedule)
        return {"ok": True, "schedule": self.get_tencent_doc_schedule()}

    def _extract_tencent_doc_worker(self, task_id: str, url: str):
        try:
            from src.processor.tencent_doc import TencentDocError, extract_todo_table, fetch_public_text, validate_tencent_doc_url

            self._set_task(task_id, status="running")
            safe_url = validate_tencent_doc_url(url)
            text = fetch_public_text(safe_url)
            table_todos, diagnostics = extract_todo_table(text)
            result = self._engine.extract_todos_from_text(
                text, source_type="tencent_doc", source_ref=safe_url,
                table_todos=table_todos if diagnostics.get("recognized_columns") else None,
                diagnostics=diagnostics,
            )
            if not result.get("ok"):
                self._set_task(task_id, status="failed", error=result.get("error", "提取失败"))
                return
            self._set_task(task_id, status="done", result={
                "extracted": result.get("extracted", 0),
                "recognized": result.get("recognized", 0),
                "skipped_duplicates": result.get("skipped_duplicates", 0),
                "mode": result.get("mode", "ai"),
                "diagnostics": result.get("diagnostics", {}),
            })
        except TencentDocError as exc:
            self._set_task(task_id, status="failed", error=str(exc))
        except Exception as exc:
            logger.exception("腾讯文档待办提取失败")
            self._set_task(
                task_id,
                status="failed",
                error=f"腾讯文档网络请求失败：{exc}。请检查网络或文档是否公开。",
            )

    def import_local_documents(self) -> dict:
        """选择多个本地文档，逐份智能提取待办并放入草稿区。"""
        paths = self._pick_open_paths(("文档 (*.txt;*.md;*.markdown;*.csv;*.docx;*.pdf)",))
        if not paths:
            return {"cancelled": True}
        with self._lock:
            self._task_seq += 1
            task_id = f"task-{self._task_seq}"
            self._tasks[task_id] = {"status": "pending", "result": None, "error": None}
        threading.Thread(
            target=self._import_local_documents_worker, args=(task_id, paths), daemon=True,
            name=f"LocalDocumentTodo-{task_id}",
        ).start()
        return {"task_id": task_id}

    def recognize_todo_image(self) -> dict:
        """选择图片后使用 macOS Vision 本地 OCR，返回给新建待办表单。"""
        path = self._pick_open_path(("图片 (*.png;*.jpg;*.jpeg;*.heic;*.heif;*.webp;*.tiff)",))
        if not path:
            return {"ok": False, "cancelled": True}
        return self._recognize_todo_image_path(path)

    def recognize_todo_clipboard_image(self) -> dict:
        """读取用户已复制到剪贴板的图片，使用本地 Vision OCR。"""
        try:
            from AppKit import NSPasteboard, NSPasteboardTypePNG, NSPasteboardTypeTIFF
            from tempfile import NamedTemporaryFile

            pasteboard = NSPasteboard.generalPasteboard()
            data = pasteboard.dataForType_(NSPasteboardTypePNG)
            suffix = ".png"
            if not data:
                data = pasteboard.dataForType_(NSPasteboardTypeTIFF)
                suffix = ".tiff"
            if not data:
                return {"ok": False, "error": "剪贴板中没有可识别的图片，请先复制图片"}
            with NamedTemporaryFile(suffix=suffix, delete=False) as file:
                file.write(bytes(data))
                path = file.name
            return self._recognize_todo_image_path(path)
        except Exception:
            logger.exception("读取剪贴板图片失败")
            return {"ok": False, "error": "无法读取剪贴板图片"}

    def recognize_todo_text(self, text: str) -> dict:
        """AI 将手动输入的待办信息整理为标题和内容，结果仅回填表单。"""
        value = (text or "").strip()
        if not value:
            return {"ok": False, "error": "请先输入待办信息"}
        extractor = self._engine._todo_extractor
        if not extractor:
            return {"ok": False, "error": "AI 未配置，请先在设置中保存 API 配置"}
        todo = extractor.recognize_one_sync(value)
        if not todo:
            return {"ok": False, "error": "AI 未能识别，请检查网络与 AI 配置后重试"}
        return {"ok": True, "todo": todo, "local_fallback": bool(todo.get("local_fallback"))}

    @staticmethod
    def _recognize_todo_image_path(path: str) -> dict:
        try:
            from src.processor.image_text import ImageTextError, recognize_image_text

            return {"ok": True, "text": recognize_image_text(path)}
        except ImageTextError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            logger.exception("待办图片文字识别失败")
            return {"ok": False, "error": "图片文字识别失败"}

    def _import_local_documents_worker(self, task_id: str, paths: list[str]) -> None:
        from src.processor.local_document import LocalDocumentError, extract_local_document_text

        self._set_task(task_id, status="running")
        extracted = 0
        imported_files: list[str] = []
        failed_files: list[str] = []
        try:
            if not self._engine._todo_extractor:
                self._set_task(task_id, status="failed", error="AI 层未初始化，请检查设置中的 AI 配置")
                return
            for raw_path in paths:
                path = Path(raw_path)
                try:
                    text = extract_local_document_text(path)
                    result = self._engine.extract_todos_from_text(
                        text, source_type="local_document", source_ref=path.name,
                    )
                    if not result.get("ok"):
                        failed_files.append(f"{path.name}：{result.get('error', '智能识别失败')}")
                        continue
                    extracted += result.get("extracted", 0)
                    imported_files.append(path.name)
                except LocalDocumentError as exc:
                    failed_files.append(f"{path.name}：{exc}")
                except Exception:
                    logger.exception("本地文档待办提取失败：%s", path.name)
                    failed_files.append(f"{path.name}：读取或识别失败")
            self._set_task(task_id, status="done", result={
                "extracted": extracted,
                "imported_files": imported_files,
                "failed_files": failed_files,
            })
        except Exception:
            logger.exception("本地文档批量导入异常")
            self._set_task(task_id, status="failed", error="本地文档导入失败")

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
                 note: str = "", record_date: str = "", contact_person: str = "") -> dict:
        """手动新建待办（非草稿，直接正式入库）"""
        from src.storage.models import TodoRecord
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        title = (title or "").strip()
        if not title:
            return {"ok": False, "error": "待办内容不能为空"}
        try:
            now = datetime.now()
            # 手动填写的记录日期保留为当天 00:00，未填写时使用真实创建时间。
            try:
                created_at = datetime.fromisoformat(record_date).strftime("%Y-%m-%dT00:00:00") if record_date else now.isoformat()
            except ValueError:
                return {"ok": False, "error": "记录日期格式无效"}
            todo_id = engine._db.insert_todo(TodoRecord(
                title=title[:200],
                priority=priority if priority in ("low", "normal", "high", "urgent") else "normal",
                due_date=due_date or "",
                note=note or "",
                contact_person=(contact_person or "").strip()[:100],
                source_type="manual",
                is_draft=False,
                created_at=created_at,
                updated_at=now.isoformat(),
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
            # progress ↔ status 联动（PRD v4.3 §4.5 / §8 决策3）：
            # 进度调到 100 自动转 done；从 100 降下来且当前是 done 则回退 in_progress。
            # 仅在显式传 progress 时触发；纯拖拽改 status 不动 progress。
            if "progress" in fields:
                try:
                    p = max(0, min(100, int(fields["progress"])))
                except (TypeError, ValueError):
                    p = None
                if p is not None:
                    fields["progress"] = p
                    if p >= 100:
                        fields["status"] = "done"
                    else:
                        cur = engine._db.query_todo(todo_id)
                        if cur and cur.status == "done":
                            fields["status"] = "in_progress"
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
                todo = engine._db.query_todo(int(tid))
                if todo and todo.is_draft and engine._db.update_todo(int(tid), {"is_draft": False, "updated_at": now}):
                    adopted += 1
            return {"ok": True, "adopted": adopted}
        except Exception as e:
            logger.exception("采纳待办失败")
            return {"ok": False, "error": str(e)}

    def discard_todos(self, todo_ids: list) -> dict:
        """批量丢弃 AI 草稿，保留记录以便在“已删除”中恢复。"""
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            now = datetime.now().isoformat()
            discarded = 0
            for tid in (todo_ids or []):
                todo = engine._db.query_todo(int(tid))
                if todo and todo.is_draft and engine._db.update_todo(
                    int(tid), {"status": "cancelled", "updated_at": now}
                ):
                    discarded += 1
            return {"ok": True, "discarded": discarded}
        except Exception as e:
            logger.exception("批量丢弃草稿待办失败")
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

    def reorder_todos(self, items) -> dict:
        """批量更新待办排序（拖拽改序，前端算好新 sort_order 后传入）

        Args:
            items: [{"id": int, "sort_order": float}, ...]
        """
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            items = list(items or [])
            if not items:
                return {"ok": True, "updated": 0}
            updated = engine._db.reorder_todos(items)
            return {"ok": True, "updated": updated}
        except Exception as e:
            logger.exception("批量排序失败")
            return {"ok": False, "error": str(e)}

    def get_todo_stats(self) -> dict:
        """待办统计（4 指标：总任务 / 今日待办 / 已延期 / 已完成）

        today 取本机当前日期（口径见 PRD v4.3 §4.7）。数据库未连接时返回零值。
        """
        engine = self._engine
        if not engine._db.is_connected:
            return {"total": 0, "today_pending": 0, "overdue": 0, "done": 0}
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            return engine._db.get_todo_stats(today)
        except Exception:
            logger.exception("待办统计失败")
            return {"total": 0, "today_pending": 0, "overdue": 0, "done": 0}

    # ==================== 待办推进建议（P2 §4.6） ====================

    def get_todo_advices(self) -> list:
        """查询未处理的推进建议（关联 todo 标题，前端展示用）"""
        engine = self._engine
        if not engine._db.is_connected:
            return []
        try:
            return engine._db.query_todo_advices(status="pending")
        except Exception:
            logger.exception("查询推进建议失败")
            return []

    def apply_todo_advice(self, advice_id: int) -> dict:
        """采纳推进建议：按建议类型改待办（start→状态 / progress→进度，触发联动），再标记 applied

        stall 类型采纳=知晓，不改待办。
        """
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            advice = engine._db.query_advice(int(advice_id))
            if not advice:
                return {"ok": False, "error": "建议不存在"}
            if advice["status"] != "pending":
                return {"ok": False, "error": "建议已处理"}
            atype = advice["suggestion_type"]
            tid = advice["todo_id"]
            if atype == "start":
                # 标记进行中（复用 update_todo 的 status 联动：清/记 completed_at）
                self.update_todo(tid, {"status": advice["suggested_status"] or "in_progress"})
            elif atype == "progress":
                # 推进进度（复用 update_todo 的 progress↔done 联动）
                self.update_todo(tid, {"progress": advice["suggested_progress"] or 0})
            # stall：仅标记建议已处理，不动待办
            engine._db.update_advice_status(int(advice_id), "applied")
            return {"ok": True, "applied_type": atype}
        except Exception as e:
            logger.exception("采纳推进建议失败")
            return {"ok": False, "error": str(e)}

    def dismiss_todo_advice(self, advice_id: int) -> dict:
        """忽略推进建议"""
        engine = self._engine
        if not engine._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        try:
            ok = engine._db.update_advice_status(int(advice_id), "dismissed")
            return {"ok": ok}
        except Exception as e:
            logger.exception("忽略推进建议失败")
            return {"ok": False, "error": str(e)}

    def generate_todo_advices(self, date: str | None = None) -> dict:
        """异步生成推进建议（手动触发）：立即返回 task_id，前端轮询 get_task_status

        结果 result: {"generated": int}
        """
        with self._lock:
            self._task_seq += 1
            task_id = f"task-{self._task_seq}"
            self._tasks[task_id] = {"status": "pending", "result": None, "error": None}
        target = date or datetime.now().strftime("%Y-%m-%d")
        threading.Thread(
            target=self._gen_advices_worker,
            args=(task_id, target),
            daemon=True,
            name=f"GenAdvice-{task_id}",
        ).start()
        return {"task_id": task_id}

    def _gen_advices_worker(self, task_id: str, date: str):
        """推进建议生成工作线程"""
        try:
            self._set_task(task_id, status="running")
            result = self._engine.generate_todo_advices(date)
            if not result.get("ok"):
                self._set_task(task_id, status="failed", error=result.get("error", "生成失败"))
                return
            self._set_task(task_id, status="done", result={"generated": result.get("generated", 0)})
        except Exception as e:
            logger.exception("推进建议工作线程异常")
            self._set_task(task_id, status="failed", error=str(e))

    def _gen_advices_silent(self, date: str):
        """日报生成成功后静默生成推进建议（失败仅记日志，不打扰用户）"""
        try:
            self._engine.generate_todo_advices(date)
        except Exception:
            logger.exception("日报后自动生成推进建议失败")

    def check_todo_notifications(self) -> dict:
        """手动触发待办提醒检查（逾期/即将到期 toast），返回本次发送数（P3 §4.9）"""
        try:
            return self._engine.check_and_notify_todos()
        except Exception as e:
            logger.exception("待办提醒检查失败")
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
            "progress_note": t.progress_note,
            "contact_person": t.contact_person,
            "due_date": t.due_date,
            "source_type": t.source_type,
            "source_ref": t.source_ref,
            "is_draft": t.is_draft,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "completed_at": t.completed_at,
            "sort_order": t.sort_order,
            "progress": t.progress,
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

    def analyze_report(self, report_type: str, date: str) -> dict:
        """异步提取报告时间分布并生成环形图 SVG：立即返回 task_id，前端轮询 get_task_status

        结果 result: {"time_dist": [...], "svg": "..."}
        LLM 失败/无数据时 result.time_dist 为空、svg 为空串（前端隐藏图区）。
        """
        with self._lock:
            self._task_seq += 1
            task_id = f"task-{self._task_seq}"
            self._tasks[task_id] = {"status": "pending", "result": None, "error": None}
        threading.Thread(
            target=self._analyze_report_worker,
            args=(task_id, report_type, date),
            daemon=True,
            name=f"AnalyzeReport-{task_id}",
        ).start()
        return {"task_id": task_id}

    def _analyze_report_worker(self, task_id: str, report_type: str, date: str):
        """时间分布提取工作线程"""
        try:
            from src.storage.report_exporter import render_donut_svg

            self._set_task(task_id, status="running")
            result = self._engine.extract_timedist_from_report(report_type, date)
            time_dist = result.get("time_dist", []) if result.get("ok") else []
            svg = render_donut_svg(time_dist) if time_dist else ""
            self._set_task(task_id, status="done",
                           result={"time_dist": time_dist, "svg": svg})
        except Exception as e:
            logger.exception("时间分布提取工作线程异常")
            self._set_task(task_id, status="failed", error=str(e))

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

            # 尝试提取时间分布生成环形图（失败降级为无图，不阻断导出）
            time_dist = []
            try:
                td_result = self._engine.extract_timedist_from_report(report_type, date)
                if td_result.get("ok"):
                    time_dist = td_result.get("time_dist", [])
            except Exception:
                logger.exception("导出时提取时间分布失败，导出无图版本")

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
                render_report_html(rep["markdown"], title, subtitle, time_dist=time_dist),
                encoding="utf-8",
            )
            # HTML 已导出时直接交给 macOS 默认浏览器打开；用户无需再去数据目录寻找文件。
            import subprocess
            subprocess.Popen(["open", str(path.resolve())])
            return {"ok": True, "path": str(path), "filename": filename, "opened": True}
        except Exception as e:
            logger.exception("导出报告失败")
            return {"ok": False, "error": str(e)}

    def export_todos(self, status: str | None = None, include_drafts: bool = True) -> dict:
        """导出待办列表为 CSV（utf-8-sig，Excel/飞书多维表格直接打开）

        弹原生保存对话框让用户选保存位置；取消则不导出。

        Args:
            status: 按状态过滤（None = 全部），与待办视图当前筛选一致
            include_drafts: 是否包含草稿区
        """
        try:
            from src.storage.data_exporter import DataExporter

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"export_todos_{timestamp}.csv"
            save_path = self._pick_save_path(default_name, ("CSV Files (*.csv)",))
            if save_path is None:
                return {"ok": False, "cancelled": True}
            # 对话框可能不带扩展名，补 .csv
            if not save_path.lower().endswith(".csv"):
                save_path += ".csv"

            rows = self._engine._db.query_todos(status=status, include_drafts=include_drafts)
            exporter = DataExporter(self._engine._db)
            path = exporter.export_todos_csv(rows, output_path=Path(save_path))
            return {"ok": True, "path": str(path), "filename": Path(path).name, "count": len(rows)}
        except Exception as e:
            logger.exception("导出待办失败")
            return {"ok": False, "error": str(e)}

    def export_todos_json(self, status: str | None = None, include_drafts: bool = True) -> dict:
        """导出待办列表为 JSON 全量备份（P4 §4.10，含 status/priority/sort_order/progress 全字段）

        弹原生保存对话框让用户选位置；取消则不导出。便于跨库迁移 / 换机恢复。
        """
        try:
            from src.storage.data_exporter import DataExporter

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"export_todos_{timestamp}.json"
            save_path = self._pick_save_path(default_name, ("JSON Files (*.json)",))
            if save_path is None:
                return {"ok": False, "cancelled": True}
            if not save_path.lower().endswith(".json"):
                save_path += ".json"

            rows = self._engine._db.query_todos(status=status, include_drafts=include_drafts)
            exporter = DataExporter(self._engine._db)
            path = exporter.export_todos_json(rows, output_path=Path(save_path))
            return {"ok": True, "path": str(path), "filename": Path(path).name, "count": len(rows)}
        except Exception as e:
            logger.exception("导出待办 JSON 失败")
            return {"ok": False, "error": str(e)}

    def import_todos_json(self, mode: str = "append") -> dict:
        """从 JSON 全量备份导入待办（P4 §4.10）

        弹原生打开文件对话框选 JSON；mode=append(同标题跳过,默认安全) / merge(同标题更新内容)。
        """
        try:
            from src.storage.data_exporter import DataExporter

            open_path = self._pick_open_path(("JSON Files (*.json)",))
            if open_path is None:
                return {"ok": False, "cancelled": True}
            exporter = DataExporter(self._engine._db)
            return exporter.import_todos_json(Path(open_path), mode=mode)
        except Exception as e:
            logger.exception("导入待办 JSON 失败")
            return {"ok": False, "error": str(e)}

    def _pick_save_path(self, save_filename: str, file_types: tuple[str, ...]) -> str | None:
        """弹 pywebview 原生保存对话框，返回用户选定的路径（取消返回 None）

        无窗口引用时回退 None（调用方按取消处理）。
        """
        if not self._window:
            logger.warning("无 pywebview 窗口引用，跳过保存对话框")
            return None
        try:
            import webview

            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=save_filename,
                file_types=file_types,
            )
            if not result:
                return None
            return result[0]
        except Exception:
            logger.exception("保存对话框异常")
            return None

    def _pick_open_path(self, file_types: tuple[str, ...]) -> str | None:
        """弹 pywebview 原生打开文件对话框，返回用户选定的路径（取消返回 None）

        无窗口引用时回退 None。供 JSON 导入等场景使用。
        """
        if not self._window:
            logger.warning("无 pywebview 窗口引用，跳过打开对话框")
            return None
        try:
            import webview

            result = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=file_types)
            if not result:
                return None
            return result[0]
        except Exception:
            logger.exception("打开文件对话框异常")
            return None

    def _pick_open_paths(self, file_types: tuple[str, ...]) -> list[str]:
        """弹原生多选文件对话框，取消时返回空列表。"""
        if not self._window:
            logger.warning("无 pywebview 窗口引用，跳过打开对话框")
            return []
        try:
            import webview

            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=True, file_types=file_types,
            )
            return list(result or [])
        except Exception:
            logger.exception("多文件打开对话框异常")
            return []

    def reveal_path(self, path: str) -> dict:
        """在 Finder 中定位到指定文件（macOS: open -R）"""
        import subprocess
        try:
            # macOS 用 open -R 在 Finder 中显示文件
            subprocess.run(
                ["open", "-R", path],
                check=False,
            )
            return {"ok": True}
        except Exception as e:
            logger.exception("定位文件失败")
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
