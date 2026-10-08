"""专注模式测试"""
import pytest
import time
from src.processor.focus_mode import FocusModeManager, FocusSession


@pytest.fixture
def manager():
    reminders = []
    m = FocusModeManager(
        on_remind=lambda title, msg: reminders.append((title, msg)),
        check_interval=1,
    )
    m.start_monitor()
    yield m, reminders
    m.stop_monitor()


def test_focus_session_start_stop(manager):
    m, _ = manager
    session = m.start_focus_session("写报告", 25)
    assert session.is_active
    assert session.goal == "写报告"
    assert session.duration_minutes == 25

    result = m.stop_focus_session()
    assert result is not None
    assert result["goal"] == "写报告"


def test_window_change_tracks_category(manager):
    m, _ = manager
    # 模拟切换到娱乐应用
    m.on_window_change("bilibili.exe", "B站")
    assert m._current_category == "娱乐休闲"

    # 等待一小段时间
    time.sleep(0.1)

    # 切换到工作应用
    m.on_window_change("code.exe", "main.py")
    assert m._current_category == "开发工具"
    assert m._distraction_total_today > 0


def test_daily_stats(manager):
    m, _ = manager
    m.on_window_change("code.exe", "main.py")
    time.sleep(0.1)
    m.on_window_change("explorer.exe", "文件")
    time.sleep(0.1)

    stats = m.get_daily_stats()
    assert "work_seconds" in stats
    assert "distraction_seconds" in stats
    assert "goal_progress" in stats
    assert stats["work_seconds"] > 0


def test_set_daily_goal(manager):
    m, _ = manager
    m.set_daily_goal(360)
    assert m._daily_goal_minutes == 360

    # 边界检查
    m.set_daily_goal(10)  # 太小，应被限制到最小值
    assert m._daily_goal_minutes == 60


def test_reminder_sent(manager):
    m, reminders = manager
    # 设置很小的阈值
    m.set_distraction_threshold(1)

    # 模拟娱乐应用使用
    m.on_window_change("bilibili.exe", "B站")
    time.sleep(2)

    # 再次切换触发检查
    m.on_window_change("code.exe", "main.py")

    # 应该有提醒（可能在 _check_distraction_reminder 中触发）
    # 注意：由于冷却时间，可能需要重置
    m._last_reminder_time = None
    m._distraction_total_today = 100  # 超过阈值
    m.on_window_change("bilibili.exe", "B站")
    m.on_window_change("code.exe", "main.py")
    assert len(reminders) > 0
