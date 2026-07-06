"""专注模式与提醒系统

功能：
1. 娱乐应用检测与提醒：当用户在娱乐类应用上花费超过阈值时间时，发出提醒
2. 专注会话：设定专注目标和时长，期间监控娱乐应用使用
3. 效率目标：设定每日工作时长目标，统计达成率
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from src.processor.app_classifier import AppClassifier

logger = logging.getLogger(__name__)

# 娱乐应用分类列表
DISTRACTION_CATEGORIES = {"娱乐休闲"}


class FocusSession:
    """专注会话"""

    def __init__(self, goal: str, duration_minutes: int):
        self.goal = goal
        self.duration_minutes = duration_minutes
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=duration_minutes)
        self.distraction_seconds = 0.0
        self.work_seconds = 0.0
        self.reminders_sent = 0
        self.is_active = True

    @property
    def remaining_minutes(self) -> float:
        if not self.is_active:
            return 0
        remaining = (self.end_time - datetime.now()).total_seconds()
        return max(0, remaining / 60)

    @property
    def elapsed_minutes(self) -> float:
        return (datetime.now() - self.start_time).total_seconds() / 60

    @property
    def distraction_ratio(self) -> float:
        total = self.distraction_seconds + self.work_seconds
        if total == 0:
            return 0
        return self.distraction_seconds / total

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "duration_minutes": self.duration_minutes,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "remaining_minutes": round(self.remaining_minutes, 1),
            "elapsed_minutes": round(self.elapsed_minutes, 1),
            "distraction_seconds": round(self.distraction_seconds, 1),
            "work_seconds": round(self.work_seconds, 1),
            "distraction_ratio": round(self.distraction_ratio, 3),
            "reminders_sent": self.reminders_sent,
            "is_active": self.is_active,
        }


class FocusModeManager:
    """专注模式管理器"""

    def __init__(
        self,
        on_remind: Callable[[str, str], None] | None = None,
        check_interval: int = 30,
    ):
        self._classifier = AppClassifier()
        self._on_remind = on_remind
        self._check_interval = check_interval  # 秒

        # 当前专注会话
        self._focus_session: FocusSession | None = None

        # 娱乐应用追踪
        self._current_category: str = "其他"
        self._category_start_time: datetime = datetime.now()
        self._distraction_total_today: float = 0.0  # 今日娱乐总时长（秒）
        self._work_total_today: float = 0.0  # 今日工作总时长（秒）

        # 提醒配置
        self._distraction_threshold = 300  # 5分钟娱乐触发提醒
        self._last_reminder_time: datetime | None = None
        self._reminder_cooldown = 600  # 10分钟冷却

        # 每日目标
        self._daily_goal_minutes = 480  # 8小时工作目标

        # 监控线程
        self._monitor_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    def start_focus_session(self, goal: str, duration_minutes: int) -> FocusSession:
        """启动专注会话"""
        with self._lock:
            self._focus_session = FocusSession(goal, duration_minutes)
            logger.info("专注会话已启动: %s (%d分钟)", goal, duration_minutes)
            return self._focus_session

    def stop_focus_session(self) -> dict | None:
        """停止专注会话"""
        with self._lock:
            if not self._focus_session:
                return None
            self._focus_session.is_active = False
            result = self._focus_session.to_dict()
            self._focus_session = None
            logger.info("专注会话已停止")
            return result

    def get_focus_session(self) -> dict | None:
        """获取当前专注会话状态"""
        with self._lock:
            if not self._focus_session:
                return None
            # 检查是否已超时
            if self._focus_session.remaining_minutes <= 0:
                self._focus_session.is_active = False
                if self._on_remind:
                    self._on_remind("专注完成", f"目标「{self._focus_session.goal}」已完成！")
            return self._focus_session.to_dict()

    def on_window_change(self, process_name: str, window_title: str):
        """窗口切换时调用：更新分类追踪"""
        category, _ = self._classifier.classify(process_name, window_title)

        with self._lock:
            now = datetime.now()
            duration = (now - self._category_start_time).total_seconds()

            # 累加上一个分类的时长
            if self._current_category in DISTRACTION_CATEGORIES:
                self._distraction_total_today += duration
                if self._focus_session:
                    self._focus_session.distraction_seconds += duration
            else:
                self._work_total_today += duration
                if self._focus_session:
                    self._focus_session.work_seconds += duration

            # 更新当前分类
            self._current_category = category
            self._category_start_time = now

            # 检查是否需要提醒
            if category in DISTRACTION_CATEGORIES:
                self._check_distraction_reminder()

    def _check_distraction_reminder(self):
        """检查是否需要发送娱乐提醒"""
        now = datetime.now()

        # 冷却期检查
        if self._last_reminder_time:
            elapsed = (now - self._last_reminder_time).total_seconds()
            if elapsed < self._reminder_cooldown:
                return

        # 专注会话期间的额外检查
        if self._focus_session and self._focus_session.is_active:
            if self._focus_session.distraction_seconds >= self._distraction_threshold:
                if self._on_remind:
                    msg = f"你在专注期间已花费 {int(self._focus_session.distraction_seconds / 60)} 分钟在娱乐应用上"
                    self._on_remind("专注提醒", msg)
                self._focus_session.reminders_sent += 1
                self._last_reminder_time = now
        elif self._distraction_total_today >= self._distraction_threshold:
            if self._on_remind:
                msg = f"今日娱乐应用使用已达 {int(self._distraction_total_today / 60)} 分钟，建议专注工作"
                self._on_remind("效率提醒", msg)
            self._last_reminder_time = now

    def get_daily_stats(self) -> dict:
        """获取今日效率统计"""
        with self._lock:
            now = datetime.now()
            # 累加当前分类的时长
            current_duration = (now - self._category_start_time).total_seconds()
            distraction = self._distraction_total_today
            work = self._work_total_today
            if self._current_category in DISTRACTION_CATEGORIES:
                distraction += current_duration
            else:
                work += current_duration

            total = distraction + work
            goal_seconds = self._daily_goal_minutes * 60
            return {
                "work_seconds": round(work, 1),
                "distraction_seconds": round(distraction, 1),
                "total_seconds": round(total, 1),
                "work_ratio": round(work / total, 3) if total > 0 else 0,
                "distraction_ratio": round(distraction / total, 3) if total > 0 else 0,
                "daily_goal_minutes": self._daily_goal_minutes,
                "goal_progress": round(work / goal_seconds, 3) if goal_seconds > 0 else 0,
                "goal_achieved": work >= goal_seconds,
                "current_category": self._current_category,
            }

    def set_daily_goal(self, minutes: int):
        """设置每日工作目标"""
        with self._lock:
            self._daily_goal_minutes = max(60, min(1440, minutes))
            logger.info("每日目标已设置: %d 分钟", minutes)

    def set_distraction_threshold(self, seconds: int):
        """设置娱乐提醒阈值"""
        with self._lock:
            self._distraction_threshold = max(60, min(3600, seconds))

    def start_monitor(self):
        """启动监控线程"""
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="FocusMonitor"
        )
        self._monitor_thread.start()
        logger.info("专注模式监控已启动")

    def stop_monitor(self):
        """停止监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None
        logger.info("专注模式监控已停止")

    def _monitor_loop(self):
        """监控循环：定期检查专注会话超时"""
        while self._running:
            try:
                if self._focus_session and self._focus_session.is_active:
                    if self._focus_session.remaining_minutes <= 0:
                        self._focus_session.is_active = False
                        if self._on_remind:
                            self._on_remind(
                                "专注完成",
                                f"目标「{self._focus_session.goal}」已完成！"
                            )
            except Exception:
                logger.exception("专注监控异常")
            time.sleep(self._check_interval)
