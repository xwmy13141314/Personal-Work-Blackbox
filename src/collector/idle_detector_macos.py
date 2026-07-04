"""空闲检测器（macOS）— 通过 ioreg 读取 HIDIdleTime 检测用户空闲状态

ioreg -c IOHIDSystem 输出的 HIDIdleTime（纳秒）= 距上次输入的空闲时长，
免权限、跨 macOS 版本稳定。状态机复刻 Windows 版 idle_detector.py，
IdleState 语义一致（ACTIVE/IDLE），便于上层零改动复用。
"""
from __future__ import annotations

import logging
import subprocess
import time
from enum import Enum, auto
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)


class IdleState(Enum):
    ACTIVE = auto()
    IDLE = auto()


class IdleDetector:
    """空闲状态检测器（macOS）"""

    def __init__(
        self,
        on_state_change: Callable[[IdleState, float], None],
        threshold: float = 300.0,
        poll_interval: float = 5.0,
    ):
        self._on_state_change = on_state_change
        self._threshold = threshold
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._state = IdleState.ACTIVE
        self._idle_start_time: float | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True, name="IdleDetectorMac")
        self._thread.start()
        logger.info("IdleDetector(macOS)已启动，阈值 %.0f 秒", self._threshold)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("IdleDetector(macOS)已停止")

    @property
    def state(self) -> IdleState:
        return self._state

    @property
    def idle_seconds(self) -> float:
        s = self._read_idle_seconds()
        return s if s is not None else 0.0

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                idle_time = self.idle_seconds

                if self._state == IdleState.ACTIVE and idle_time >= self._threshold:
                    self._state = IdleState.IDLE
                    self._idle_start_time = time.time() - idle_time
                    self._on_state_change(IdleState.IDLE, idle_time)
                    logger.debug("进入空闲状态，已空闲 %.0f 秒", idle_time)

                elif self._state == IdleState.IDLE and idle_time < self._threshold:
                    idle_duration = time.time() - self._idle_start_time if self._idle_start_time else 0
                    self._state = IdleState.ACTIVE
                    self._idle_start_time = None
                    self._on_state_change(IdleState.ACTIVE, idle_duration)
                    logger.debug("恢复活跃状态，空闲了 %.0f 秒", idle_duration)

            except Exception:
                logger.exception("空闲检测异常（macOS）")

            self._stop_event.wait(self._poll_interval)

    @staticmethod
    def _read_idle_seconds() -> float | None:
        """ioreg 读取 HIDIdleTime（纳秒）→ 秒"""
        try:
            out = subprocess.check_output(
                ["ioreg", "-c", "IOHIDSystem"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            )
            for line in out.splitlines():
                if "HIDIdleTime" in line:
                    parts = line.split("=")
                    if len(parts) == 2:
                        return int(parts[1].strip()) / 1_000_000_000.0
        except Exception:
            logger.debug("ioreg 读取 HIDIdleTime 失败")
        return None
