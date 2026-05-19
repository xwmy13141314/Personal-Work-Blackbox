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
    """获取应用根目录（兼容 PyInstaller 打包和源码运行）"""
    if getattr(sys, 'frozen', False):
        # 打包版：项目根目录 = exe 的上级目录（exe 在 dist/ 下）
        return Path(sys.executable).parent.parent
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
        )
        self._db.initialize()

        self._exporter = MarkdownExporter(
            db=self._db,
            export_dir=self._settings.markdown_dir,
        )

        self._privacy_filter = PrivacyFilter(self._settings.privacy)
        self._session_manager = SessionManager(on_session_end=self._on_session_end)
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

        # AI 摘要层
        self._report_generator = None
        self._init_ai_layer()

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

        # 启动键盘监听
        if self._settings.collection["keyboard_enabled"]:
            self._keyboard_hook = KeyboardHook(
                on_event=self._on_keyboard_event,
                capture_hotkeys=self._settings.collection["capture_hotkeys"],
            )
            self._keyboard_hook.start()

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

    def stop(self):
        """停止采集引擎（保留数据库连接，支持后续报告生成）"""
        logger.info("正在停止 Personal Work Blackbox...")
        self._running = False

        # 按逆序停止各组件
        if self._idle_detector:
            self._idle_detector.stop()
        if self._clipboard_monitor:
            self._clipboard_monitor.stop()
        if self._keyboard_hook:
            self._keyboard_hook.stop()
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

        # 注意：不关闭数据库，保持连接活跃以支持报告查看/生成
        logger.info("=== Personal Work Blackbox 已停止 ===")

    def shutdown(self):
        """完全关闭引擎（含数据库），仅在应用退出时调用"""
        if self._running:
            self.stop()
        self._db.close()
        logger.info("引擎已完全关闭（数据库连接已释放）")

    def pause(self):
        """暂停采集"""
        self._session_manager.pause()
        if self._keyboard_hook:
            self._keyboard_hook.stop()
            self._keyboard_hook = None

    def resume(self):
        """恢复采集"""
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            self._session_manager.resume(ctx)
        if self._settings.collection["keyboard_enabled"]:
            self._keyboard_hook = KeyboardHook(
                on_event=self._on_keyboard_event,
                capture_hotkeys=self._settings.collection["capture_hotkeys"],
            )
            self._keyboard_hook.start()

    def toggle_privacy_mode(self, duration_minutes: float | None = None):
        """切换隐私模式"""
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
            logger.info("AI 摘要层已初始化，提供商: %s", ai_config.get("default_provider"))

        except Exception:
            logger.exception("AI 层初始化失败")

    def generate_daily_report(self, date: str | None = None) -> str | None:
        """手动触发生成日报"""
        if not self._report_generator:
            logger.warning("AI 层未初始化，无法生成日报")
            return None

        if not self._db.is_connected:
            logger.warning("数据库未连接，无法生成日报")
            return None

        # 先提交当前缓冲区（仅在运行中有意义，停止后为空操作）
        if self._running:
            self._input_buffer.force_commit()

        try:
            report = self._report_generator.generate_sync(date)
            if report:
                logger.info("日报生成成功")
            return report
        except Exception:
            logger.exception("日报生成失败")
            return None

    def get_daily_report(self, date: str | None = None):
        """查询已有的日报"""
        if not self._db.is_connected:
            logger.warning("数据库未连接，无法查询日报")
            return None
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        return self._db.query_daily_report(target_date)

    # ==================== 事件处理 ====================

    def _on_window_switch(self, from_ctx: WindowContext, to_ctx: WindowContext, duration: float):
        """窗口切换事件"""
        # 提交当前输入缓冲区
        self._input_buffer.force_commit()

        # 通知会话管理器
        self._session_manager.on_window_switch(from_ctx, to_ctx, duration)

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
        # 隐私模式检查
        if self._privacy_filter.is_privacy_mode:
            return

        # 检查当前窗口是否在黑名单
        if self._window_tracker:
            ctx = self._window_tracker.current_context
            if self._privacy_filter.should_pause_recording(ctx.process_name, ctx.window_title):
                return

        # 传递给输入缓冲区
        self._input_buffer.process_event(event)

    def _on_text_commit(self, text: str):
        """输入缓冲区提交回调"""
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
        """会话结束回调：将 Session 持久化到数据库"""
        # 插入会话记录
        session_record = SessionRecord(
            start_time=datetime.fromtimestamp(session.start_time).isoformat(),
            end_time=datetime.fromtimestamp(session.end_time).isoformat() if session.end_time else None,
            process_name=session.process_name,
            window_title=session.window_title,
            idle_seconds=session.idle_seconds,
            active_seconds=session.active_seconds,
            is_filtered=session.is_filtered,
        )
        session_id = self._db.insert_session(session_record)

        # 插入文本片段
        for seg in session.text_segments:
            seg_record = TextSegmentRecord(
                session_id=session_id,
                timestamp=datetime.fromtimestamp(seg.timestamp).isoformat(),
                raw_text=seg.text,
                source=seg.source,
                is_filtered=seg.is_filtered,
                char_count=seg.char_count,
            )
            self._db.insert_text_segment(seg_record)

        # 剪贴板记录已在 _on_clipboard_change 中直接入库

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
    # frozen exe 模式下，将 CWD 切换到项目根目录（exe 的上级目录）
    # 这样开发和打包版共用同一个 data/ 目录
    if getattr(sys, 'frozen', False):
        os.chdir(Path(sys.executable).parent.parent)

    if "--no-tray" in sys.argv:
        main()
    elif "--gui" in sys.argv or "--ui" in sys.argv:
        from src.ui.gui import run_gui
        run_gui()
    else:
        # 默认 GUI 模式
        from src.ui.gui import run_gui
        run_gui()
