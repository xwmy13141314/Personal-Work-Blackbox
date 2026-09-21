"""UIA 采集代理（主进程侧）—— 与 uia_worker 子进程通信

背景：主进程绝不能导入 comtypes/uiautomation（会毁掉 pywebview 的 WebView2
窗口，见 uia_worker.py 说明）。所以 UIA 读取放在子进程，本模块做代理：

    主进程                          子进程 (uia_worker)
    ┌──────────────────┐   stdout   ┌──────────────────────┐
    │ 读取 JSON 观察行 │ ◀───────── │ uiautomation 读焦点  │
    │ 控件基线 + 差分  │            │ 文本, 每 0.5s 一行   │
    │ 提交时择优替换   │            └──────────────────────┘
    └──────────────────┘

对外契约与 `UiaTextCapture` 完全一致（start/stop/request_snapshot/
get_typed_text/is_available/last_way），因此 CaptureRouter 无需改动。

额外特性：
- 子进程意外退出 → 自动重启（带退避），不影响键盘链路
- 隐私模式/黑名单由父进程 `should_capture()` 门控（子进程读到的内容直接丢弃）
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable

from src.collector.uia_capture import diff_increment, merge_keyboard_and_uia

logger = logging.getLogger(__name__)

#: 观察行视为"过期"的秒数（与 UiaTextCapture 一致）
_SNAPSHOT_TTL = 2.5

#: 子进程重启的最小间隔（防止崩溃循环烧 CPU）
_RESTART_BACKOFF = 5.0

#: 子进程无输出的告警阈值（秒）
_SILENCE_WARN = 30.0


def _worker_command(interval: float) -> list[str]:
    """拼装子进程命令行（打包版复用自身 exe，源码版用 python -m）"""
    args = ["--uia-worker", "--interval", f"{interval:.3f}"]
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "src.collector.uia_worker", *args]


def _popen_kwargs() -> dict:
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if os.name == "nt":  # 隐藏子进程控制台窗口
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


class UiaWorkerCapture:
    """UIA 子进程采集代理（主进程侧，永不导入 comtypes）"""

    def __init__(
        self,
        interval: float = 0.5,
        should_capture: Callable[[], bool] | None = None,
        max_text_length: int = 4000,
        editable_only: bool = True,
    ):
        self._interval = max(0.2, interval)
        self._should_capture = should_capture
        self._max_text_length = max_text_length
        self._editable_only = editable_only

        self._lock = threading.Lock()
        self._stop_flag = False
        self._reader: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None

        self._baselines: dict[str, str] = {}
        self._last_snapshot: tuple[str, str, float] | None = None
        self._last_way = ""
        self._last_control_type = ""
        self._last_proc = ""
        self._last_line_at = 0.0
        self._ready = False

    # ==================== 生命周期 ====================

    def start(self):
        if self._reader is not None:
            return
        self._stop_flag = False
        self._reader = threading.Thread(
            target=self._reader_main, daemon=True, name="UiaWorkerReader",
        )
        self._reader.start()
        logger.info("UIA 采集已启动（独立子进程模式, interval=%.2fs）", self._interval)

    def stop(self):
        self._stop_flag = True
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._reader is not None:
            self._reader.join(timeout=2)
            self._reader = None
        logger.info("UIA 采集已停止")

    def request_snapshot(self):
        """子进程按固定间隔轮询，无需唤醒（保留接口兼容）"""
        return

    @property
    def is_available(self) -> bool:
        """子进程存活且近期有输出"""
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return False
        return self._ready

    @property
    def last_way(self) -> str:
        return self._last_way

    # ==================== 子进程读取循环 ====================

    def _reader_main(self):
        last_restart = 0.0
        while not self._stop_flag:
            if self._proc is None or self._proc.poll() is not None:
                now = time.time()
                if now - last_restart < _RESTART_BACKOFF:
                    time.sleep(0.5)
                    continue
                last_restart = now
                if not self._spawn():
                    time.sleep(_RESTART_BACKOFF)
                    continue
            try:
                line = self._proc.stdout.readline()
            except Exception:
                line = ""
            if not line:
                if self._stop_flag:
                    break
                time.sleep(0.2)
                continue
            self._handle_line(line)
        self._cleanup_proc()

    def _spawn(self) -> bool:
        self._cleanup_proc()
        try:
            cmd = _worker_command(self._interval)
            self._proc = subprocess.Popen(cmd, **_popen_kwargs())
            self._last_line_at = time.time()
            logger.info("UIA 子进程已启动: %s", " ".join(cmd[:3]) + " …")
            return True
        except Exception:
            logger.warning("UIA 子进程启动失败", exc_info=True)
            self._proc = None
            return False

    def _cleanup_proc(self):
        proc = self._proc
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        self._proc = None
        self._ready = False

    def _handle_line(self, line: str):
        line = line.strip()
        if not line:
            return
        self._last_line_at = time.time()
        try:
            msg = json.loads(line)
        except Exception:
            return
        if not isinstance(msg, dict):
            return

        if msg.get("fatal"):
            logger.warning("UIA 子进程报告不可用: %s", msg["fatal"])
            return
        if msg.get("ready"):
            self._ready = True
            logger.info("UIA 子进程就绪")
            return
        if msg.get("error"):
            logger.debug("UIA 子进程单次异常: %s", msg["error"])
            return
        if msg.get("none") or msg.get("key") is None:
            self._last_way = ""
            return

        # 隐私模式/黑名单：直接丢弃，不建基线
        if self._should_capture is not None and not self._should_capture():
            return

        key = self._key_of(msg["key"])
        text = str(msg.get("text") or "")[: self._max_text_length]
        with self._lock:
            if key not in self._baselines:
                self._baselines[key] = text  # 首次观察：已有内容即基线
            self._last_snapshot = (key, text, time.time())
            if len(self._baselines) > 128:
                keep = key
                self._baselines = {k: v for k, v in self._baselines.items() if k == keep}
        self._last_way = str(msg.get("way") or "")
        self._last_control_type = str(msg.get("ctype") or "")
        self._last_proc = str(msg.get("proc") or "")

    @staticmethod
    def _key_of(raw) -> str:
        try:
            return f"{raw.get('k')}:{raw.get('v')}"
        except Exception:
            return str(raw)

    # ==================== 提交时差分（与 UiaTextCapture 同策略）====================

    def get_typed_text(self, keyboard_text: str) -> str:
        with self._lock:
            snap = self._last_snapshot
        if snap is None:
            return keyboard_text

        key, text, ts = snap
        if time.time() - ts > _SNAPSHOT_TTL:
            return keyboard_text

        with self._lock:
            baseline = self._baselines.get(key, "")
            self._baselines[key] = text  # 基线推进

        delta = diff_increment(baseline, text)
        if not delta.strip():
            return keyboard_text
        return merge_keyboard_and_uia(keyboard_text, delta)

    # ==================== 诊断 ====================

    def status(self) -> dict:
        proc = self._proc
        return {
            "mode": "subprocess",
            "pid": getattr(proc, "pid", None),
            "alive": bool(proc is not None and proc.poll() is None),
            "ready": self._ready,
            "last_way": self._last_way,
            "last_control_type": self._last_control_type,
            "last_foreground": self._last_proc,
            "last_line_age": (time.time() - self._last_line_at) if self._last_line_at else None,
        }
