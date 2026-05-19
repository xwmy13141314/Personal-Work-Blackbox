"""Personal Work Blackbox — GUI 操作面板

基于 tkinter 的轻量级操作界面，无需额外依赖。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    CENTER,
    DISABLED,
    EW,
    HORIZONTAL,
    LEFT,
    NORMAL,
    RIGHT,
    TOP,
    W,
    X,
    Y,
    Button,
    Entry,
    Frame,
    Label,
    scrolledtext,
    ttk,
    StringVar,
)

logger = logging.getLogger(__name__)

# 配色方案
COLORS = {
    "bg": "#1e1e2e",
    "surface": "#2a2a3d",
    "surface_light": "#363650",
    "primary": "#7c3aed",
    "primary_hover": "#6d28d9",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "text": "#e2e8f0",
    "text_dim": "#94a3b8",
    "border": "#404060",
}


class BlackboxGUI:
    """主界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("Personal Work Blackbox")
        self.root.geometry("680x580")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(True, True)

        # 状态
        self.engine = None
        self.is_running = False
        self.is_paused = False

        # 构建 UI
        self._build_ui()

        # 启动后自动初始化引擎
        self.root.after(500, self._init_engine)

    # ==================== UI 构建 ====================

    def _build_ui(self):
        """构建界面"""
        # ---- 顶栏：状态 + 标题 ----
        top_frame = Frame(self.root, bg=COLORS["surface"], height=60)
        top_frame.pack(fill=X, padx=0, pady=0)
        top_frame.pack_propagate(False)

        self.status_dot = Label(
            top_frame, text="●", font=("Segoe UI", 18),
            fg=COLORS["text_dim"], bg=COLORS["surface"],
        )
        self.status_dot.pack(side=LEFT, padx=(16, 4), pady=10)

        self.status_label = Label(
            top_frame, text="未启动", font=("Segoe UI", 11),
            fg=COLORS["text_dim"], bg=COLORS["surface"], anchor=W,
        )
        self.status_label.pack(side=LEFT, padx=4, pady=10)

        self.time_label = Label(
            top_frame, text="", font=("Consolas", 10),
            fg=COLORS["text_dim"], bg=COLORS["surface"],
        )
        self.time_label.pack(side=RIGHT, padx=16, pady=10)

        # ---- 中间：控制按钮区 ----
        ctrl_frame = Frame(self.root, bg=COLORS["bg"])
        ctrl_frame.pack(fill=X, padx=16, pady=(16, 8))

        buttons = [
            ("▶ 启动", self._on_start, "start_btn", COLORS["success"]),
            ("⏸ 暂停", self._on_pause, "pause_btn", COLORS["warning"]),
            ("⏹ 停止", self._on_stop, "stop_btn", COLORS["danger"]),
        ]

        for text, cmd, attr, color in buttons:
            btn = Button(
                ctrl_frame, text=text, font=("Segoe UI", 11, "bold"),
                fg="white", bg=color, activebackground=color,
                activeforeground="white", relief="flat", cursor="hand2",
                command=cmd, width=10, height=1,
            )
            btn.pack(side=LEFT, padx=(0, 8), expand=True, fill=X)
            setattr(self, attr, btn)

        self.start_btn.config(state=NORMAL)
        self.pause_btn.config(state=DISABLED)
        self.stop_btn.config(state=DISABLED)

        # ---- AI 报告区 ----
        ai_frame = Frame(self.root, bg=COLORS["bg"])
        ai_frame.pack(fill=X, padx=16, pady=(4, 4))

        ai_title = Label(
            ai_frame, text="AI 报告", font=("Segoe UI", 10, "bold"),
            fg=COLORS["text_dim"], bg=COLORS["bg"], anchor=W,
        )
        ai_title.pack(fill=X)

        # 第一行：日期选择 + 前后按钮 + 生成/查看按钮
        ai_row1 = Frame(ai_frame, bg=COLORS["bg"])
        ai_row1.pack(fill=X, pady=(4, 0))

        date_label = Label(
            ai_row1, text="日期:", font=("Segoe UI", 10),
            fg=COLORS["text_dim"], bg=COLORS["bg"],
        )
        date_label.pack(side=LEFT)

        self.date_var = StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.date_combo = ttk.Combobox(
            ai_row1, textvariable=self.date_var, font=("Consolas", 10),
            width=12, justify=CENTER, state="readonly",
        )
        self.date_combo.pack(side=LEFT, padx=(4, 4), ipady=2)

        # 前一天 / 后一天按钮
        nav_frame = Frame(ai_row1, bg=COLORS["bg"])
        nav_frame.pack(side=LEFT, padx=(0, 8))

        self.prev_day_btn = Button(
            nav_frame, text="◀", font=("Segoe UI", 9),
            fg="white", bg=COLORS["surface_light"], activebackground=COLORS["surface"],
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_prev_day, width=3,
        )
        self.prev_day_btn.pack(side=LEFT, padx=(0, 2))

        self.next_day_btn = Button(
            nav_frame, text="▶", font=("Segoe UI", 9),
            fg="white", bg=COLORS["surface_light"], activebackground=COLORS["surface"],
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_next_day, width=3,
        )
        self.next_day_btn.pack(side=LEFT)

        self.report_btn = Button(
            ai_row1, text="生成报告", font=("Segoe UI", 10),
            fg="white", bg=COLORS["primary"], activebackground=COLORS["primary_hover"],
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_generate_report, width=12,
        )
        self.report_btn.pack(side=LEFT, padx=(0, 4))

        self.view_btn = Button(
            ai_row1, text="查看报告", font=("Segoe UI", 10),
            fg=COLORS["text"], bg=COLORS["surface_light"], activebackground=COLORS["surface"],
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_view_report, width=12,
        )
        self.view_btn.pack(side=LEFT)

        self.privacy_btn = Button(
            ai_row1, text="隐私模式", font=("Segoe UI", 10),
            fg=COLORS["text"], bg=COLORS["surface_light"], activebackground=COLORS["surface"],
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_privacy_mode, width=10,
        )
        self.privacy_btn.pack(side=RIGHT)

        # ---- 分隔线 ----
        sep = Frame(self.root, bg=COLORS["border"], height=1)
        sep.pack(fill=X, padx=16, pady=(12, 4))

        # ---- 日志区 ----
        log_title = Label(
            self.root, text="运行日志", font=("Segoe UI", 10, "bold"),
            fg=COLORS["text_dim"], bg=COLORS["bg"], anchor=W,
        )
        log_title.pack(fill=X, padx=16, pady=(4, 2))

        self.log_text = scrolledtext.ScrolledText(
            self.root, font=("Consolas", 9),
            bg=COLORS["surface"], fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat", wrap="word", height=10,
            state=DISABLED, borderwidth=0,
        )
        self.log_text.pack(fill=BOTH, expand=True, padx=16, pady=(0, 12))

        # 配置日志 tag
        self.log_text.tag_config("info", foreground=COLORS["text"])
        self.log_text.tag_config("success", foreground=COLORS["success"])
        self.log_text.tag_config("warning", foreground=COLORS["warning"])
        self.log_text.tag_config("error", foreground=COLORS["danger"])

        # ---- 底栏 ----
        bottom = Frame(self.root, bg=COLORS["surface"], height=28)
        bottom.pack(fill=X, side=BOTTOM)
        bottom.pack_propagate(False)

        self.bottom_label = Label(
            bottom, text="Personal Work Blackbox v2.0 | Ctrl+Alt+P 暂停 | Ctrl+Alt+R 报告",
            font=("Segoe UI", 8), fg=COLORS["text_dim"], bg=COLORS["surface"],
        )
        self.bottom_label.pack(side=LEFT, padx=12, pady=4)

        self.data_btn = Label(
            bottom, text="打开数据目录", font=("Segoe UI", 8, "underline"),
            fg=COLORS["primary"], bg=COLORS["surface"], cursor="hand2",
        )
        self.data_btn.pack(side=RIGHT, padx=12, pady=4)
        self.data_btn.bind("<Button-1>", lambda e: self._open_data_dir())

    # ==================== 引擎管理 ====================

    def _init_engine(self):
        """初始化引擎（延迟执行，避免阻塞 UI）"""
        self._log("正在初始化引擎...", "info")
        self.root.update()

        try:
            from src.main import BlackboxEngine, get_app_root, ensure_config
            config_path = get_app_root() / "config" / "config.yaml"
            if not config_path.exists():
                config_path = ensure_config()
            self.engine = BlackboxEngine(str(config_path))
            self._log("引擎初始化完成，点击「启动」开始采集", "success")
            # 加载有数据的日期列表
            self._refresh_date_list()
        except Exception as e:
            self._log(f"引擎初始化失败: {e}", "error")

    def _on_start(self):
        """启动采集"""
        if not self.engine:
            self._log("引擎未初始化", "error")
            return

        try:
            self.engine.start()
            self.is_running = True
            self.is_paused = False
            self._update_status("running", "采集中...")
            self.start_btn.config(state=DISABLED)
            self.pause_btn.config(state=NORMAL, text="⏸ 暂停")
            self.stop_btn.config(state=NORMAL)
            self._log("采集已启动", "success")
            self._start_clock()
        except Exception as e:
            self._log(f"启动失败: {e}", "error")

    def _on_pause(self):
        """暂停/恢复采集"""
        if not self.engine:
            return

        if self.is_paused:
            self.engine.resume()
            self.is_paused = False
            self.pause_btn.config(text="⏸ 暂停")
            self._update_status("running", "采集中...")
            self._log("采集已恢复", "success")
        else:
            self.engine.pause()
            self.is_paused = True
            self.pause_btn.config(text="▶ 恢复")
            self._update_status("paused", "已暂停")
            self._log("采集已暂停", "warning")

    def _on_stop(self):
        """停止采集"""
        if not self.engine:
            return

        self.engine.stop()
        self.is_running = False
        self.is_paused = False
        self._update_status("stopped", "已停止")
        self.start_btn.config(state=NORMAL)
        self.pause_btn.config(state=DISABLED, text="⏸ 暂停")
        self.stop_btn.config(state=DISABLED)
        # 停止后仍可生成/查看报告（数据库连接保持活跃）
        self._log("采集已停止，日志已导出（仍可生成 AI 报告）", "success")

    # ==================== AI 报告 ====================

    def _get_selected_date(self) -> str:
        """获取日期输入框的值，格式校验"""
        date_str = self.date_var.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            return datetime.now().strftime("%Y-%m-%d")

    def _on_generate_report(self):
        """生成 AI 日报"""
        if not self.engine:
            self._log("引擎未初始化", "error")
            return

        # 检查 AI 层是否可用
        if not self.engine._report_generator:
            self._log("AI 层未初始化，请检查 config.yaml 中的 api_key 配置", "error")
            return

        target_date = self._get_selected_date()

        # 预校验：检查目标日期是否有采集数据
        try:
            sessions = self.engine._db.query_sessions(date=target_date, limit=1)
            if not sessions:
                self._log(f"⚠ {target_date} 没有采集数据，无法生成日报", "warning")
                return
        except Exception as e:
            self._log(f"数据查询失败: {e}", "error")
            return

        self._log(f"正在为 {target_date} 生成日报...", "info")
        self.report_btn.config(state=DISABLED, text="生成中...")
        self.root.update()

        def _gen():
            try:
                report = self.engine.generate_daily_report(date=target_date)
                if report:
                    now = datetime.now()
                    report_path = Path(self.engine._settings.markdown_dir) / f"{target_date}_{now.strftime('%H%M%S')}_report.md"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(f"# AI 每日报告 - {target_date}\n\n{report}", encoding="utf-8")
                    self.root.after(0, lambda: self._log(f"日报已保存: {report_path.name}", "success"))
                    self.root.after(0, lambda: self._show_report_preview(report))
                else:
                    self.root.after(0, lambda: self._log(f"{target_date} 无活动数据或 AI 调用失败，请查看 blackbox.log", "warning"))
            except Exception as e:
                import traceback
                self.root.after(0, lambda: self._log(f"日报生成失败: {e}", "error"))
                logger.exception("日报生成异常")
            finally:
                self.root.after(0, lambda: self.report_btn.config(state=NORMAL, text="生成报告"))

        threading.Thread(target=_gen, daemon=True).start()

    def _show_report_preview(self, report: str):
        """在日志区显示报告预览"""
        self.log_text.config(state=NORMAL)
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "=" * 50 + "\n", "info")
        self.log_text.insert("end", " AI 日报预览\n", "success")
        self.log_text.insert("end", "=" * 50 + "\n\n", "info")
        self.log_text.insert("end", report[:3000], "info")
        if len(report) > 3000:
            self.log_text.insert("end", "\n\n... (已截断，完整内容请查看文件)", "warning")
        self.log_text.config(state=DISABLED)

    def _on_view_report(self):
        """查看选中日期的报告"""
        target_date = self._get_selected_date()
        report_dir = Path(self.engine._settings.markdown_dir) if self.engine else Path("data/logs")
        # 按日期匹配最新的报告文件
        report_files = sorted(report_dir.glob(f"{target_date}_*_report.md"), reverse=True)
        if report_files:
            os.startfile(str(report_files[0]))
            self._log(f"已打开报告: {report_files[0].name}", "info")
        else:
            self._log(f"{target_date} 没有报告，请先生成", "warning")

    def _on_privacy_mode(self):
        """隐私模式"""
        if not self.engine:
            self._log("引擎未初始化", "error")
            return
        self.engine.toggle_privacy_mode()
        self._update_status("privacy", "隐私模式 (30min)")
        self._log("隐私模式已激活，持续 30 分钟", "warning")

    # ==================== 日期导航 ====================

    def _refresh_date_list(self):
        """刷新日期下拉列表"""
        if not self.engine or not self.engine._db:
            return

        try:
            dates = self.engine._db.query_available_dates(limit=30)
        except Exception:
            dates = []

        today = datetime.now().strftime("%Y-%m-%d")
        # 确保今天始终在列表顶部
        if today not in dates:
            dates.insert(0, today)

        self.date_combo["values"] = dates
        # 保持当前选中日期
        current = self.date_var.get()
        if current not in dates:
            self.date_var.set(today)

    def _on_prev_day(self):
        """切换到列表中的前一个日期"""
        values = list(self.date_combo["values"])
        if not values:
            return
        current = self.date_var.get()
        try:
            idx = values.index(current)
            if idx < len(values) - 1:
                self.date_var.set(values[idx + 1])
        except ValueError:
            self.date_var.set(values[0])

    def _on_next_day(self):
        """切换到列表中的下一个日期"""
        values = list(self.date_combo["values"])
        if not values:
            return
        current = self.date_var.get()
        try:
            idx = values.index(current)
            if idx > 0:
                self.date_var.set(values[idx - 1])
        except ValueError:
            self.date_var.set(values[0])

    # ==================== 辅助方法 ====================

    def _update_status(self, state: str, text: str):
        """更新状态显示"""
        color_map = {
            "running": COLORS["success"],
            "paused": COLORS["warning"],
            "stopped": COLORS["danger"],
            "privacy": COLORS["warning"],
        }
        color = color_map.get(state, COLORS["text_dim"])
        self.status_dot.config(fg=color)
        self.status_label.config(text=text, fg=color)

    def _log(self, message: str, level: str = "info"):
        """在日志区输出信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=NORMAL)
        self.log_text.insert("end", f"[{timestamp}] {message}\n", level)
        self.log_text.see("end")
        self.log_text.config(state=DISABLED)
        logger.info(message)

    def _start_clock(self):
        """启动时钟更新"""
        if not self.is_running:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=now)
        self.root.after(1000, self._start_clock)

    def _open_data_dir(self):
        """打开数据目录"""
        data_dir = Path("./data")
        data_dir.mkdir(exist_ok=True)
        os.startfile(str(data_dir.resolve()))

    def on_closing(self):
        """窗口关闭事件"""
        if self.engine:
            self.engine.shutdown()
        self.root.destroy()


def run_gui():
    """启动 GUI"""
    import tkinter as tk
    from tkinter import messagebox

    # 初始化文件日志（确保异常可追踪）
    from src.main import setup_logging
    setup_logging()

    try:
        root = tk.Tk()
    except Exception as e:
        print(f"[FATAL] tkinter 初始化失败: {e}")
        input("按回车键退出...")
        return

    # 设置窗口图标（如果有的话）
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = BlackboxGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    # 居中显示
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"+{x}+{y}")

    try:
        root.mainloop()
    except Exception as e:
        logger.exception("GUI 主循环异常退出")
        try:
            messagebox.showerror("程序异常", f"Personal Work Blackbox 遇到错误:\n\n{e}")
        except Exception:
            pass


if __name__ == "__main__":
    run_gui()
