"""Personal Work Blackbox — 主入口

串联所有模块：采集层 → 处理管道 → 存储层 → 托盘 UI
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event


def get_app_root() -> Path:
    """获取应用根目录（兼容 PyInstaller 打包和源码运行）

    源码版：src/ 的上级目录（项目根）。
    打包版：智能区分两种部署——
      - 开发者：exe 在项目内 dist/ 子目录，其上级即项目根（检测到 src/ 目录
        作为标志），与源码运行共用同一套 config/ data/ logs/，杜绝双库分叉；
      - 外部用户：exe 单独分发（下载到任意目录），data/ config/ 就近放 exe 同级。
    """
    if getattr(sys, 'frozen', False):
        exe_parent = Path(sys.executable).parent
        candidate = exe_parent.parent  # 若 exe 在 dist/，上级即项目根
        if (candidate / "src").is_dir():  # 项目根标志 → 开发者场景
            return candidate
        return exe_parent  # 外部用户：data/config 在 exe 旁
    return Path(__file__).parent.parent


def get_bundled_root() -> Path:
    """获取 PyInstaller 打包的内部资源目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def ensure_config():
    """首次运行时在 exe 旁生成配置文件（优先从打包资源提取模板，其次用默认值）"""
    config_dir = get_app_root() / "config"
    config_file = config_dir / "config.yaml"
    if config_file.exists():
        return config_file

    config_dir.mkdir(parents=True, exist_ok=True)

    # 优先从 PyInstaller 打包资源中提取模板配置（不含 API Key）
    bundled = get_bundled_root() / "config" / "config.example.yaml"
    if bundled.exists():
        import shutil
        shutil.copy2(str(bundled), str(config_file))
        logger.info("已从打包模板提取配置: %s", config_file)
        return config_file

    # 回退：用默认值生成（无 API Key，需用户手动配置）
    from src.config.defaults import DEFAULTS
    import yaml
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULTS, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info("已生成默认配置（请手动配置 API Key）: %s", config_file)
    return config_file

from src.collector.clipboard_monitor import ClipboardMonitor, ClipboardRecord
from src.collector.idle_detector import IdleDetector, IdleState
from src.collector.keyboard_hook import KeyEvent, KeyboardHook
from src.collector.window_tracker import WindowContext, WindowTracker
from src.config.settings import Settings
from src.processor.app_classifier import AppClassifier
from src.processor.input_buffer import InputBuffer
from src.processor.privacy_filter import PrivacyFilter
from src.processor.session_manager import Session, SessionManager
from src.storage.database import Database
from src.storage.markdown_exporter import MarkdownExporter
from src.storage.models import (
    ClipboardRecordModel,
    SessionRecord,
    TextSegmentRecord,
    WindowEventRecord,
)

logger = logging.getLogger(__name__)


class BlackboxEngine:
    """核心引擎：协调采集 → 处理 → 存储"""

    def __init__(self, config_path: str | Path | None = None):
        self._settings = Settings.get_instance(config_path)
        self._settings.ensure_dirs()

        # 初始化各层组件
        self._db = Database(
            db_path=self._settings.db_path,
            journal_mode=self._settings.performance["journal_mode"],
            encryption_key=self._settings.db_encryption_key,
        )
        self._db.initialize()

        self._exporter = MarkdownExporter(
            db=self._db,
            export_dir=self._settings.markdown_dir,
        )

        self._privacy_filter = PrivacyFilter(self._settings.privacy)
        self._classifier = AppClassifier()
        self._session_manager = SessionManager(
            on_session_end=self._on_session_end,
            classifier=self._classifier,
        )
        self._input_buffer = InputBuffer(
            on_commit=self._on_text_commit,
            max_length=self._settings.performance["input_buffer_max_length"],
            timeout=self._settings.performance["input_buffer_timeout"],
        )

        # 采集器（延迟初始化）
        self._window_tracker: WindowTracker | None = None
        self._keyboard_hook: KeyboardHook | None = None
        self._clipboard_monitor: ClipboardMonitor | None = None
        self._idle_detector: IdleDetector | None = None

        # 状态
        self._running = False
        self._stop_event = Event()
        self._keyboard_paused = False  # 暂停标志（替代 stop/start 钩子）

        # AI 摘要层
        self._report_generator = None
        self._todo_extractor = None
        self._timedist_extractor = None
        self._init_ai_layer()

        # REST API 服务器
        self._rest_api = None
        self._init_rest_api()

        # 专注模式
        self._focus_mode = None
        self._init_focus_mode()

    def _init_focus_mode(self):
        """初始化专注模式"""
        try:
            from src.processor.focus_mode import FocusModeManager
            from src.ui.notification import send_toast

            def on_remind(title, message):
                send_toast(title, message)

            self._focus_mode = FocusModeManager(on_remind=on_remind)
            self._focus_mode.start_monitor()
        except Exception:
            logger.exception("专注模式初始化失败")

    def _init_rest_api(self):
        """初始化 REST API 服务器"""
        try:
            rest_config = self._settings.config.get("rest_api", {})
            if rest_config.get("enabled", False):
                from src.ui.rest_api import RestAPIServer
                port = rest_config.get("port", 19527)
                self._rest_api = RestAPIServer(self, port=port)
                self._rest_api.start()
        except Exception:
            logger.exception("REST API 初始化失败")

    def start(self):
        """启动采集引擎"""
        if self._running:
            logger.warning("引擎已在运行")
            return

        self._running = True
        logger.info("=== Personal Work Blackbox 启动 ===")

        # 启动窗口追踪
        self._window_tracker = WindowTracker(
            on_switch=self._on_window_switch,
            poll_interval=self._settings.collection["window_poll_interval"],
        )
        self._window_tracker.start()

        # 创建初始会话
        ctx = self._window_tracker.current_context
        if ctx.is_valid:
            self._session_manager.resume(ctx)

        # 启动键盘监听（KeyboardHook 内部创建专用线程 + 消息泵）
        if self._settings.collection["keyboard_enabled"]:
            if not self._keyboard_hook:
                self._keyboard_hook = KeyboardHook(
                    on_event=self._on_keyboard_event,
                    capture_hotkeys=self._settings.collection["capture_hotkeys"],
                )
                self._keyboard_hook.start()
            elif not self._keyboard_hook.is_alive:
                # 钩子已停止，需要重新创建
                self._keyboard_hook = KeyboardHook(
                    on_event=self._on_keyboard_event,
                    capture_hotkeys=self._settings.collection["capture_hotkeys"],
                )
                self._keyboard_hook.start()
            self._keyboard_paused = False

        # 启动剪贴板监控
        if self._settings.collection["clipboard_enabled"]:
            self._clipboard_monitor = ClipboardMonitor(
                on_change=self._on_clipboard_change,
                max_length=self._settings.collection["clipboard_max_length"],
            )
            self._clipboard_monitor.start()

        # 启动空闲检测
        self._idle_detector = IdleDetector(
            on_state_change=self._on_idle_state_change,
            threshold=self._settings.collection["idle_threshold"],
        )
        self._idle_detector.start()

        # 启动超时检查循环
        self._timeout_thread()

        # 启动 REST API（若已在 __init__ 中启动则跳过）
        if self._rest_api and not self._rest_api.is_running:
            self._rest_api.start()

        # 启动待办提醒检查（逾期/即将到期 toast，每小时一次，P3 §4.9）
        self._todo_notify_thread()

    def stop(self):
        """停止采集引擎（保留数据库连接和键盘钩子，支持后续报告生成）"""
        logger.info("正在停止 Personal Work Blackbox...")
        self._running = False

        # 按逆序停止各组件（键盘钩子不停止，只设暂停标志）
        self._keyboard_paused = True
        if self._idle_detector:
            self._idle_detector.stop()
        if self._clipboard_monitor:
            self._clipboard_monitor.stop()
        if self._window_tracker:
            self._window_tracker.stop()

        # 提交残留缓冲区
        self._input_buffer.force_commit()

        # 结束当前会话
        self._session_manager.flush()

        # 导出今日日志
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            self._exporter.export_daily(today)
        except Exception:
            logger.exception("导出日志异常")

        # 停止 REST API
        if self._rest_api:
            self._rest_api.stop()

        # 停止专注模式监控
        if self._focus_mode:
            self._focus_mode.stop_monitor()

        # 注意：不关闭数据库，保持连接活跃以支持报告查看/生成
        logger.info("=== Personal Work Blackbox 已停止 ===")

    def shutdown(self):
        """完全关闭引擎（含数据库和键盘钩子），仅在应用退出时调用"""
        if self._running:
            self.stop()
        # 现在才卸载键盘钩子
        if self._keyboard_hook:
            self._keyboard_hook.stop()
            self._keyboard_hook = None
        if self._rest_api:
            self._rest_api.stop()
        self._db.close()
        logger.info("引擎已完全关闭（数据库连接已释放）")

    def pause(self):
        """暂停采集（不卸载钩子，改用标志位忽略事件）"""
        self._session_manager.pause()
        self._keyboard_paused = True

    def resume(self):
        """恢复采集"""
        self._keyboard_paused = False
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            self._session_manager.resume(ctx)

    def toggle_privacy_mode(self, duration_minutes: float | None = None):
        """切换隐私模式：已开启则关闭，未开启则激活指定时长"""
        if self._privacy_filter.is_privacy_mode:
            self._privacy_filter.deactivate_privacy_mode()
        else:
            self._privacy_filter.activate_privacy_mode(duration_minutes)

    @property
    def is_privacy_mode(self) -> bool:
        return self._privacy_filter.is_privacy_mode

    # ==================== AI 报告 ====================

    def _init_ai_layer(self):
        """初始化 AI 摘要层"""
        try:
            from src.ai.llm_client import LLMClient
            from src.ai.prompt_engine import PromptEngine
            from src.ai.report_generator import ReportGenerator

            ai_config = self._settings.ai
            llm_client = LLMClient(ai_config)

            if not llm_client.has_provider:
                logger.warning("未配置任何 LLM 提供商，AI 日报功能不可用")
                return

            template_dir = get_app_root() / "config" / "prompts"
            prompt_engine = PromptEngine(template_dir)

            self._report_generator = ReportGenerator(
                db=self._db,
                llm_client=llm_client,
                prompt_engine=prompt_engine,
            )

            from src.ai.todo_extractor import TodoExtractor
            self._todo_extractor = TodoExtractor(
                db=self._db,
                llm_client=llm_client,
                prompt_engine=prompt_engine,
            )

            from src.ai.timedist_extractor import TimeDistExtractor
            self._timedist_extractor = TimeDistExtractor(
                db=self._db,
                llm_client=llm_client,
                prompt_engine=prompt_engine,
            )
            logger.info("AI 摘要层已初始化，提供商: %s", ai_config.get("default_provider"))

            # 自动补生成缺失的日报
            self._auto_generate_missing_reports()

        except Exception:
            logger.exception("AI 层初始化失败")

    def _auto_generate_missing_reports(self):
        """后台线程自动补生成缺失的日报"""
        import threading

        def _worker():
            try:
                generated = self._report_generator.auto_generate_missing(days=7)
                if generated:
                    logger.info("自动补生成日报完成: %s", generated)
            except Exception:
                logger.exception("自动补生成日报异常")

        t = threading.Thread(target=_worker, daemon=True, name="AutoReportGen")
        t.start()

    def generate_daily_report(self, date: str | None = None) -> str | None:
        """手动触发生成日报"""
        if not self._report_generator:
            logger.warning("AI 层未初始化，无法生成日报")
            return None

        if not self._db.is_connected:
            logger.warning("数据库未连接，无法生成日报")
            return None

        # 先提交当前缓冲区并持久化进行中的会话（仅在运行中有意义，停止后为空操作）
        if self._running:
            self._input_buffer.force_commit()
            self._flush_active_session()

        try:
            report = self._report_generator.generate_sync(date)
            if report:
                logger.info("日报生成成功")
            return report
        except Exception:
            logger.exception("日报生成失败")
            return None

    def _flush_active_session(self):
        """生成报告前强制持久化当前会话，并立即开新会话接续录制

        进行中的会话内容只暂存于内存，生成日报时查 DB 会缺失当前内容。
        flush 结束当前会话并持久化，随后基于当前窗口立即开新会话，用户无感。
        暂停状态下 current_session 为空，直接返回，不受影响。
        """
        sm = self._session_manager
        if not sm.current_session:
            return
        sm.flush()
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            if ctx.is_valid:
                sm.resume(ctx)

    def get_daily_report(self, date: str | None = None):
        """查询已有的日报"""
        if not self._db.is_connected:
            logger.warning("数据库未连接，无法查询日报")
            return None
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        return self._db.query_daily_report(target_date)

    def generate_weekly_report(self, date: str | None = None) -> str | None:
        """生成周报"""
        if not self._report_generator:
            logger.warning("AI 层未初始化，无法生成周报")
            return None
        if not self._db.is_connected:
            logger.warning("数据库未连接，无法生成周报")
            return None
        try:
            return self._report_generator.generate_period_sync("weekly", date)
        except Exception:
            logger.exception("周报生成失败")
            return None

    def generate_monthly_report(self, date: str | None = None) -> str | None:
        """生成月报"""
        if not self._report_generator:
            logger.warning("AI 层未初始化，无法生成月报")
            return None
        if not self._db.is_connected:
            logger.warning("数据库未连接，无法生成月报")
            return None
        try:
            return self._report_generator.generate_period_sync("monthly", date)
        except Exception:
            logger.exception("月报生成失败")
            return None

    def extract_todos_from_report(self, report_type: str, date: str) -> dict:
        """从指定报告中提取待办，批量存入草稿区

        Args:
            report_type: daily / weekly / monthly
            date: 报告对应日期（YYYY-MM-DD；周期报告传该周期内任意一天）

        Returns:
            {"ok": bool, "extracted": int, "error": str?}
        """
        if not self._todo_extractor:
            return {"ok": False, "error": "AI 层未初始化，无法提取待办"}
        if not self._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}

        # 1. 取报告文本
        if report_type == "daily":
            record = self._db.query_daily_report(date)
            source_ref = date
        elif report_type in ("weekly", "monthly"):
            from src.ai.report_generator import _week_range, _month_range
            if report_type == "weekly":
                period_start, _ = _week_range(date)
            else:
                period_start, _ = _month_range(date)
            record = self._db.query_period_report(report_type, period_start)
            source_ref = period_start
        else:
            return {"ok": False, "error": f"未知报告类型: {report_type}"}

        if not record or not getattr(record, "structured_report", ""):
            return {"ok": False, "error": f"未找到 {report_type} 报告，请先生成报告"}

        # 2. 提取（复用 LLMClient 重试降级）
        try:
            todos = self._todo_extractor.extract_sync(record.structured_report)
        except Exception:
            logger.exception("待办提取失败")
            return {"ok": False, "error": "待办提取失败，请检查网络与 API 配置"}

        # 3. 批量入草稿区（is_draft=True，待用户采纳）
        from src.storage.models import TodoRecord
        now = datetime.now().isoformat()
        inserted = 0
        for t in todos:
            try:
                rec = TodoRecord(
                    title=t["title"],
                    priority=t.get("priority", "normal"),
                    due_date=t.get("due_date", ""),
                    note=t.get("note", ""),
                    source_type=f"{report_type}_report",
                    source_ref=source_ref,
                    is_draft=True,
                    created_at=now,
                    updated_at=now,
                )
                self._db.insert_todo(rec)
                inserted += 1
            except Exception:
                logger.exception("插入待办草稿失败: %s", t)

        logger.info("从 %s 报告提取待办 %d 条，入库 %d 条", report_type, len(todos), inserted)
        return {"ok": True, "extracted": inserted}

    def generate_todo_advices(self, date: str | None = None) -> dict:
        """结合当日活动对未完成待办生成 AI 推进建议（P2 §4.6）

        日报生成后或手动触发调用。只针对未完成（pending/in_progress）正式待办，
        对照当日采集活动（query_app_usage_stats）生成建议入 todo_advices 表
        （同待办已有 pending 建议则去重跳过）。只建议，不改待办状态。

        Args:
            date: 基于哪天的活动（默认今天）

        Returns:
            {"ok": bool, "generated": int, "error": str?}
        """
        if not self._todo_extractor:
            return {"ok": False, "error": "AI 层未初始化，无法生成推进建议"}
        if not self._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}

        target_date = date or datetime.now().strftime("%Y-%m-%d")
        todos = self._db.query_todos(include_drafts=False)
        active = [t for t in todos if t.status in ("pending", "in_progress")]
        if not active:
            logger.info("无未完成待办，跳过推进建议生成")
            return {"ok": True, "generated": 0}

        # 当日活动摘要（与日报同源）
        app_stats = self._db.query_app_usage_stats(target_date)
        try:
            advices = self._todo_extractor.advise_sync(active, app_stats)
        except Exception:
            logger.exception("推进建议生成失败")
            return {"ok": False, "error": "推进建议生成失败，请检查网络与 API 配置"}

        # 持久化（去重：同 todo_id 已有 pending 跳过）
        from src.storage.models import TodoAdvice
        now = datetime.now().isoformat()
        inserted = 0
        for a in advices:
            try:
                rec = TodoAdvice(
                    todo_id=a["todo_id"],
                    suggestion_type=a["type"],
                    reason=a["reason"],
                    suggested_status="in_progress" if a["type"] == "start" else "",
                    suggested_progress=a.get("suggested_progress"),
                    status="pending",
                    source_date=target_date,
                    created_at=now,
                    updated_at=now,
                )
                if self._db.insert_todo_advice(rec):
                    inserted += 1
            except Exception:
                logger.exception("插入推进建议失败: %s", a)

        logger.info("生成推进建议 %d 条，新入库 %d 条（去重 %d）",
                    len(advices), inserted, len(advices) - inserted)
        return {"ok": True, "generated": inserted}

    def check_and_notify_todos(self) -> dict:
        """检查逾期待办与即将到期待办，发桌面 toast（每任务每日每类最多 1 次，P3 §4.9）

        overdue: due_date < 今天；upcoming: due_date == 明天。
        只对未完成（pending/in_progress）正式待办（有 due_date）触发。

        Returns:
            {"ok": bool, "notified": int, "error": str?}
        """
        if not self._db.is_connected:
            return {"ok": False, "error": "数据库未连接"}
        from src.ui.notification import send_toast
        from datetime import timedelta
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        todos = self._db.query_todos(include_drafts=False)
        active = [t for t in todos if t.status in ("pending", "in_progress") and t.due_date]
        notified = 0
        for t in active:
            ntype = None
            if t.due_date < today:
                ntype = "overdue"
            elif t.due_date == tomorrow:
                ntype = "upcoming"
            if ntype and self._db.record_todo_notify(t.id, today, ntype):
                title = "⏰ 待办逾期" if ntype == "overdue" else "📅 待办即将到期"
                send_toast(title, t.title[:60])
                notified += 1
        if notified:
            logger.info("待办提醒：发送 %d 条 toast", notified)
        return {"ok": True, "notified": notified}

    def _todo_notify_thread(self):
        """后台线程：启动后稍延迟检查一次，之后每小时检查待办提醒（P3 §4.9）"""
        import threading

        def _loop():
            time.sleep(15)  # 启动延迟，等窗口与采集就绪
            try:
                self.check_and_notify_todos()
            except Exception:
                logger.exception("待办提醒检查异常（启动）")
            while self._running:
                time.sleep(3600)
                try:
                    self.check_and_notify_todos()
                except Exception:
                    logger.exception("待办提醒检查异常")

        t = threading.Thread(target=_loop, daemon=True, name="TodoNotify")
        t.start()

    def extract_timedist_from_report(self, report_type: str, date: str) -> dict:
        """提取时间分布数据（供报告页环形图 / 导出 HTML 使用）

        数据源优先级：DB 分类统计（query_category_stats，基于真实前台活跃时长）
        → 降级 LLM 从报告文本提取。DB 路径不依赖报告是否生成（无报告也能出图）。

        Args:
            report_type: daily / weekly / monthly
            date: 报告对应日期（周期报告传该周期内任意一天）

        Returns:
            {"ok": bool, "time_dist": [{"category","minutes","percent"}, ...],
             "source": "db"|"llm"?, "error": str?}
        """
        if report_type not in ("daily", "weekly", "monthly"):
            return {"ok": False, "error": f"未知报告类型: {report_type}", "time_dist": []}
        if not self._db.is_connected:
            return {"ok": False, "error": "数据库未连接", "time_dist": []}

        # 1. DB 优先：按真实前台活跃时长统计
        db_dist = self._timedist_from_db(report_type, date)
        if db_dist:
            logger.info("时间分布取自 DB 分类统计（%d 类）", len(db_dist))
            return {"ok": True, "time_dist": db_dist, "source": "db"}

        # 2. 降级：LLM 从报告文本提取
        if not getattr(self, "_timedist_extractor", None):
            return {"ok": False, "error": "AI 层未初始化", "time_dist": []}

        if report_type == "daily":
            record = self._db.query_daily_report(date)
        else:
            from src.ai.report_generator import _week_range, _month_range
            if report_type == "weekly":
                period_start, _ = _week_range(date)
            else:
                period_start, _ = _month_range(date)
            record = self._db.query_period_report(report_type, period_start)

        if not record or not getattr(record, "structured_report", ""):
            return {"ok": False, "error": "未找到报告，请先生成报告", "time_dist": []}

        try:
            time_dist = self._timedist_extractor.extract_sync(record.structured_report)
        except Exception:
            logger.exception("时间分布提取失败")
            return {"ok": False, "error": "时间分布提取失败，请检查网络与 API 配置", "time_dist": []}

        logger.info("时间分布取自 LLM 提取（%d 类）", len(time_dist))
        return {"ok": True, "time_dist": time_dist, "source": "llm"}

    def _timedist_from_db(self, report_type: str, date: str) -> list[dict] | None:
        """从 DB 分类统计生成时间分布（DB 优先路径）

        复用 query_category_stats（按 category 聚合 active_seconds），转成
        render_donut_svg 所需格式。无有效数据或查询失败返回 None（交由调用方降级）。
        """
        from src.ai.report_generator import _week_range, _month_range
        from src.ai.timedist_extractor import category_stats_to_timedist

        if report_type == "daily":
            start = end = date
        elif report_type == "weekly":
            start, end = _week_range(date)
        elif report_type == "monthly":
            start, end = _month_range(date)
        else:
            return None

        try:
            items = self._db.query_category_stats(start_date=start, end_date=end)
        except Exception:
            logger.exception("DB 分类统计查询失败")
            return None

        return category_stats_to_timedist(items) or None

    def get_period_report(self, report_type: str, date: str | None = None):
        """查询已有的周报/月报"""
        if not self._db.is_connected:
            return None
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        # 根据 date 计算周期起始日
        from src.ai.report_generator import _week_range, _month_range
        if report_type == "weekly":
            period_start, _ = _week_range(target_date)
        elif report_type == "monthly":
            period_start, _ = _month_range(target_date)
        else:
            return None
        return self._db.query_period_report(report_type, period_start)

    # ==================== 事件处理 ====================

    def _on_window_switch(self, from_ctx: WindowContext, to_ctx: WindowContext, duration: float):
        """窗口切换事件"""
        # 提交当前输入缓冲区
        self._input_buffer.force_commit()

        # 通知会话管理器
        self._session_manager.on_window_switch(from_ctx, to_ctx, duration)

        # 通知专注模式
        if self._focus_mode:
            self._focus_mode.on_window_change(to_ctx.process_name, to_ctx.window_title)

        # 记录窗口事件
        event = WindowEventRecord(
            timestamp=datetime.now().isoformat(),
            event_type="switch",
            process_name=to_ctx.process_name,
            window_title=to_ctx.window_title,
            duration_seconds=duration,
        )
        self._db.insert_window_event(event)

        # 检查新窗口是否需要暂停键盘记录
        if self._privacy_filter.should_pause_recording(to_ctx.process_name, to_ctx.window_title):
            logger.info("黑名单应用，暂停键盘记录: %s", to_ctx.process_name)

    def _on_keyboard_event(self, event: KeyEvent):
        """键盘事件"""
        # 暂停标志检查
        if self._keyboard_paused:
            return

        # 隐私模式检查
        if self._privacy_filter.is_privacy_mode:
            return

        # 检查当前窗口是否在黑名单
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            if self._privacy_filter.should_pause_recording(ctx.process_name, ctx.window_title):
                # 诊断：首次被隐私过滤拦截
                if not getattr(self, '_kb_filtered_logged', False):
                    self._kb_filtered_logged = True
                    logger.info("键盘事件被隐私过滤拦截: process=%s, title=%s",
                                ctx.process_name, ctx.window_title)
                return

        # 诊断：首次到达引擎的键盘事件
        if not getattr(self, '_kb_event_logged', False):
            self._kb_event_logged = True
            logger.info("引擎首次收到键盘事件: key=%s, char=%s", event.key, event.char)

        # 传递给输入缓冲区
        self._input_buffer.process_event(event)

    def _on_text_commit(self, text: str):
        """输入缓冲区提交回调"""
        # 诊断：首次文本提交
        if not getattr(self, '_text_commit_logged', False):
            self._text_commit_logged = True
            logger.info("引擎首次收到文本提交: text=%r", text[:50])

        # 隐私过滤
        context = ""
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            context = f"{ctx.process_name} {ctx.window_title}"

        filtered_text, was_filtered = self._privacy_filter.filter_text(text, context)

        # 通知会话管理器
        self._session_manager.on_text_committed(
            text=filtered_text,
            source="keyboard",
            is_filtered=was_filtered,
        )

    def _on_clipboard_change(self, record: ClipboardRecord):
        """剪贴板变化事件"""
        if self._privacy_filter.is_privacy_mode:
            return

        # 检查当前窗口是否在黑名单（与键盘事件保持一致）
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            if self._privacy_filter.should_pause_recording(ctx.process_name, ctx.window_title):
                return

        # 隐私过滤
        filtered_content, was_filtered = self._privacy_filter.filter_clipboard(record.content)

        # 获取来源信息
        source_process = ""
        source_window = ""
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            source_process = ctx.process_name
            source_window = ctx.window_title

        # 存储到数据库
        db_record = ClipboardRecordModel(
            timestamp=datetime.fromtimestamp(record.timestamp).isoformat(),
            content=filtered_content,
            content_length=len(filtered_content),
            source_process=source_process,
            source_window=source_window,
            is_filtered=was_filtered,
        )
        self._db.insert_clipboard_record(db_record)

        # 通知会话管理器
        self._session_manager.on_clipboard_change(
            content=filtered_content,
            is_filtered=was_filtered,
        )

    def _on_idle_state_change(self, new_state: IdleState, duration: float):
        """空闲状态变化"""
        if new_state == IdleState.IDLE:
            # 空闲 → 提交当前缓冲区
            self._input_buffer.force_commit()
            self._session_manager.on_idle_start(duration)
            event_type = "idle_start"
        else:
            self._session_manager.on_idle_end(duration)
            event_type = "idle_end"

        # 记录事件
        event = WindowEventRecord(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            duration_seconds=duration,
        )
        self._db.insert_window_event(event)

    # ==================== 会话持久化 ====================

    def _on_session_end(self, session: Session):
        """会话结束回调：将 Session 原子性持久化到数据库

        使用 insert_session_with_segments 单事务写入，
        避免旧版逐条 insert 导致的"有会话无片段"不一致问题。
        """
        # 构建会话记录
        session_record = SessionRecord(
            start_time=datetime.fromtimestamp(session.start_time).isoformat(),
            end_time=datetime.fromtimestamp(session.end_time).isoformat() if session.end_time else None,
            process_name=session.process_name,
            window_title=session.window_title,
            idle_seconds=session.idle_seconds,
            active_seconds=session.active_seconds,
            is_filtered=session.is_filtered,
            category=session.category,
            icon=session.icon,
        )

        # 构建文本片段记录列表
        seg_records = [
            TextSegmentRecord(
                session_id=0,  # 占位，实际 ID 由批量插入设置
                timestamp=datetime.fromtimestamp(seg.timestamp).isoformat(),
                raw_text=seg.text,
                source=seg.source,
                is_filtered=seg.is_filtered,
                char_count=seg.char_count,
            )
            for seg in session.text_segments
        ]

        logger.info("会话持久化: process=%s, segments=%d, active=%.0fs",
                     session.process_name, len(seg_records), session.active_seconds)

        # 原子性批量插入（单事务）
        try:
            self._db.insert_session_with_segments(session_record, seg_records)
        except Exception:
            logger.exception("会话批量持久化异常")

    # ==================== 超时检查 ====================

    def _timeout_thread(self):
        """输入缓冲区超时检查（在主线程中周期性调用）"""
        import threading

        def _loop():
            while self._running:
                self._input_buffer.check_timeout()
                time.sleep(5)

        t = threading.Thread(target=_loop, daemon=True, name="TimeoutChecker")
        t.start()


def setup_logging(level: str = "INFO"):
    """配置日志"""
    log_path = get_app_root() / "blackbox.log"
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_path), encoding="utf-8"),
        ],
    )


def run_with_tray():
    """带托盘的主入口"""
    from src.ui.system_tray import SystemTray
    from src.ui.hotkey_manager import HotkeyManager
    from src.ui.notification import send_toast

    setup_logging()

    # 确定配置文件路径
    config_path = get_app_root() / "config" / "config.yaml"
    if not config_path.exists():
        config_path = ensure_config()

    engine = BlackboxEngine(config_path)
    engine.start()

    # 状态
    is_paused = False

    def toggle_pause():
        nonlocal is_paused
        is_paused = not is_paused
        if is_paused:
            engine.pause()
            logger.info("采集已暂停")
        else:
            engine.resume()
            logger.info("采集已恢复")

    def activate_privacy():
        engine.toggle_privacy_mode()
        logger.info("隐私模式已激活（30分钟）")
        send_toast("隐私模式", "已激活 30 分钟，所有记录暂停")

    def export_today():
        today = datetime.now().strftime("%Y-%m-%d")
        path = engine._exporter.export_daily(today)
        logger.info("日志已导出: %s", path)
        send_toast("导出成功", f"日志已保存到 {path}")

    def generate_report():
        report = engine.generate_daily_report()
        if report:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            timestamp = now.strftime("%Y-%m-%d_%H%M%S")
            report_path = Path(engine._settings.markdown_dir) / f"{timestamp}_report.md"
            report_path.write_text(f"# AI 每日报告 - {today}\n\n{report}", encoding="utf-8")
            send_toast("日报生成成功", f"已保存到 {report_path}")
            logger.info("日报已保存: %s", report_path)
        else:
            send_toast("日报生成失败", "请检查 AI 配置或查看日志")

    def view_report():
        """查看今日报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        report = engine.get_daily_report(today)
        if report:
            import subprocess
            # 找到今天最新的报告文件
            report_dir = Path(engine._settings.markdown_dir)
            report_files = sorted(report_dir.glob(f"{today}_*_report.md"), reverse=True)
            if report_files:
                report_path = report_files[0]
            else:
                report_path = report_dir / f"{today}_manual_report.md"
                report_path.write_text(f"# AI 每日报告 - {today}\n\n{report.structured_report}", encoding="utf-8")
            subprocess.Popen(["notepad", str(report_path)])
        else:
            send_toast("无报告", "今日尚未生成报告，请先点击「生成 AI 日报」")

    def quit_app():
        engine.shutdown()

    # 注册全局快捷键
    hotkey_manager = HotkeyManager(
        on_toggle_pause=toggle_pause,
        on_export=export_today,
        on_privacy_mode=activate_privacy,
    )
    hotkey_manager.start()

    # 启动系统托盘（阻塞）
    tray = SystemTray(
        on_pause_resume=toggle_pause,
        on_privacy_mode=activate_privacy,
        on_export=export_today,
        on_quit=quit_app,
        on_generate_report=generate_report,
        on_view_report=view_report,
    )

    try:
        tray.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        hotkey_manager.stop()
        engine.shutdown()


def main():
    """无托盘的主入口（命令行模式）"""
    setup_logging()

    config_path = get_app_root() / "config" / "config.yaml"
    if not config_path.exists():
        config_path = ensure_config()

    engine = BlackboxEngine(config_path)

    stop_event = Event()

    def signal_handler(sig, frame):
        logger.info("收到退出信号: %s", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    engine.start()

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.shutdown()


if __name__ == "__main__":
    # PyInstaller windowed(console=False)模式下 stdout/stderr 为 None，
    # 会导致依赖 print/stderr 的库（pywebview/pythonnet）运行时崩溃，
    # 重定向到 devnull 规避（仅 windowed exe 受影响，源码版有控制台不受影响）
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    # frozen exe 模式下，将 CWD 切换到项目根目录（exe 的上级目录）
    # 这样开发和打包版共用同一个 data/ 目录
    if getattr(sys, 'frozen', False):
        os.chdir(Path(sys.executable).parent.parent)

    if "--no-tray" in sys.argv:
        main()
    elif "--gui-tk" in sys.argv:
        # tkinter 回退入口（保留旧 GUI）
        from src.ui.gui import run_gui
        run_gui()
    else:
        # 默认 Web UI（pywebview）；--gui / --ui 也走 Web
        from src.ui.web_ui import run_web
        run_web()
