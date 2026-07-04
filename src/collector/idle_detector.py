"""空闲检测器 — 通过 GetLastInputInfo 检测用户空闲状态"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import time
from enum import Enum, auto
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class IdleState(Enum):
    ACTIVE = auto()
    IDLE = auto()


class IdleDetector:
    """空闲状态检测器"""

    def __init__(
        self,
        on_state_change: Callable[[IdleState, float], None],
        threshold: float = 300.0,
        poll_interval: float = 5.0,
    ):
        """
        Args:
            on_state_change: 状态变更回调 (new_state, idle_seconds)
            threshold: 空闲阈值（秒）
            poll_interval: 检测间隔（秒）
        """
        self._on_state_change = on_state_change
        self._threshold = threshold
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._state = IdleState.ACTIVE
        self._idle_start_time: float | None = None

    def start(self):
        """启动检测线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True, name="IdleDetector")
        self._thread.start()
        logger.info("IdleDetector 已启动，阈值 %.0f 秒", self._threshold)

    def stop(self):
        """停止检测"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("IdleDetector 已停止")

    @property
    def state(self) -> IdleState:
        return self._state

    @property
    def idle_seconds(self) -> float:
        """当前已空闲的秒数"""
        last_input = self._get_last_input_time()
        if last_input is None:
            return 0.0
        return time.time() - last_input

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                idle_time = self.idle_seconds

                if self._state == IdleState.ACTIVE and idle_time >= self._threshold:
                    # active → idle
                    self._state = IdleState.IDLE
                    self._idle_start_time = time.time() - idle_time
                    self._on_state_change(IdleState.IDLE, idle_time)
                    logger.debug("进入空闲状态，已空闲 %.0f 秒", idle_time)

                elif self._state == IdleState.IDLE and idle_time < self._threshold:
                    # idle → active
                    idle_duration = time.time() - self._idle_start_time if self._idle_start_time else 0
                    self._state = IdleState.ACTIVE
                    self._idle_start_time = None
                    self._on_state_change(IdleState.ACTIVE, idle_duration)
                    logger.debug("恢复活跃状态，空闲了 %.0f 秒", idle_duration)

            except Exception:
                logger.exception("空闲检测异常")

            self._stop_event.wait(self._poll_interval)

    @staticmethod
    def _get_last_input_time() -> float | None:
        """获取最后一次输入的时间戳"""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)

        if user32.GetLastInputInfo(ctypes.byref(lii)):
            # dwTime 是系统启动后的毫秒数
            millis = kernel32.GetTickCount64() if hasattr(kernel32, 'GetTickCount64') else kernel32.GetTickCount()
            idle_ms = millis - lii.dwTime
            return time.time() - (idle_ms / 1000.0)
        return None
