"""UIA 子进程隔离层测试

覆盖 2026-09-14 的关键架构变更：主进程严禁导入 comtypes/uiautomation
（会破坏 pywebview 的 WebView2 窗口），UIA 采集改为独立子进程 + JSON 协议。

测两类：
1. `uia_worker`（子进程）：参数解析、协议输出
2. `uia_worker_capture`（主进程代理）：命令行拼装、行解析、基线/差分/择优
"""

from __future__ import annotations

import json
import sys
import time

import pytest

from src.collector import uia_worker_capture as uwc
from src.collector.uia_worker_capture import UiaWorkerCapture


# ==================== 1. 主进程不得导入 comtypes ====================

class TestMainProcessIsolation:
    def test_module_import_does_not_load_comtypes(self):
        """导入代理模块后，comtypes/uiautomation 不得出现在 sys.modules"""
        assert "comtypes" not in sys.modules, "主进程导入了 comtypes，会破坏 WebView2！"
        assert "uiautomation" not in sys.modules, "主进程导入了 uiautomation！"

    def test_uia_capture_module_is_safe_to_import(self):
        """uia_capture 必须能被主进程安全导入（惰性加载）"""
        from src.collector import uia_capture

        assert uia_capture._HAS_UIA is False  # 未调用 _load_uia() 前不应加载
        assert "comtypes" not in sys.modules

    def test_router_import_is_safe(self):
        from src.collector.capture_router import CaptureRouter  # noqa: F401

        assert "comtypes" not in sys.modules


# ==================== 2. 子进程命令行拼装 ====================

class TestWorkerCommand:
    def test_source_mode_uses_module(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        cmd = uwc._worker_command(0.5)
        assert cmd[0] == sys.executable
        assert "-m" in cmd
        assert "src.collector.uia_worker" in cmd
        assert "--uia-worker" in cmd
        assert "--interval" in cmd

    def test_frozen_mode_reuses_exe(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        cmd = uwc._worker_command(0.5)
        assert cmd == [sys.executable, "--uia-worker", "--interval", "0.500"]

    def test_popen_hides_console_on_windows(self):
        kwargs = uwc._popen_kwargs()
        assert kwargs["stdout"] is not None
        assert kwargs["encoding"] == "utf-8"
        if uwc.os.name == "nt":
            assert kwargs["creationflags"] == getattr(sys.modules["subprocess"], "CREATE_NO_WINDOW", 0)


class TestParseInterval:
    def test_default(self):
        from src.collector.uia_worker import _parse_interval

        assert _parse_interval([]) == 0.5

    def test_explicit(self):
        from src.collector.uia_worker import _parse_interval

        assert _parse_interval(["--interval", "0.25"]) == 0.25

    def test_malformed_falls_back(self):
        from src.collector.uia_worker import _parse_interval

        assert _parse_interval(["--interval", "abc"]) == 0.5
        assert _parse_interval(["--interval"]) == 0.5


# ==================== 3. 协议行解析 / 基线 / 差分 ====================

def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


class TestHandleLine:
    def _cap(self, **kw) -> UiaWorkerCapture:
        return UiaWorkerCapture(interval=0.4, should_capture=lambda: True, **kw)

    def test_ready_sets_flag(self):
        cap = self._cap()
        assert cap._ready is False
        cap._handle_line(_line(ready=True, interval=0.4))
        assert cap._ready is True

    def test_none_observation_clears_way(self):
        cap = self._cap()
        cap._handle_line(_line(t=1.0, key={"k": "hwnd", "v": 1}, text="abc", way="V"))
        assert cap.last_way == "V"
        cap._handle_line(_line(t=2.0, none=True))
        assert cap.last_way == ""

    def test_error_line_ignored(self):
        cap = self._cap()
        cap._handle_line(_line(t=1.0, error="boom"))
        assert cap._last_snapshot is None

    def test_fatal_line_ignored(self):
        cap = self._cap()
        cap._handle_line(_line(fatal="no uiautomation"))
        assert cap._last_snapshot is None

    def test_garbage_line_ignored(self):
        cap = self._cap()
        cap._handle_line("not json at all")
        cap._handle_line("")
        assert cap._last_snapshot is None

    def test_first_observation_becomes_baseline(self):
        cap = self._cap()
        cap._handle_line(_line(t=1.0, key={"k": "hwnd", "v": 7}, text="已有内容", way="V"))
        assert cap._baselines["hwnd:7"] == "已有内容"
        assert cap._last_control_type == ""

    def test_metadata_recorded(self):
        cap = self._cap()
        cap._handle_line(_line(
            t=1.0, key={"k": "hwnd", "v": 7}, text="你好",
            way="V", ctype="EditControl", proc="workbuddy.exe",
        ))
        assert cap.last_way == "V"
        assert cap._last_control_type == "EditControl"
        assert cap._last_proc == "workbuddy.exe"

    def test_should_capture_false_drops_data(self):
        cap = UiaWorkerCapture(interval=0.4, should_capture=lambda: False)
        cap._handle_line(_line(t=1.0, key={"k": "hwnd", "v": 7}, text="敏感内容", way="V"))
        assert cap._last_snapshot is None
        assert cap._baselines == {}

    def test_baseline_dict_is_bounded(self):
        cap = self._cap()
        for i in range(400):
            cap._handle_line(_line(t=1.0, key={"k": "hwnd", "v": i}, text="x", way="V"))
        # 触发阈值(>128)后会裁剪到仅保留最新控件，规模始终有界且远小于 400
        assert len(cap._baselines) <= 129
        assert "hwnd:399" in cap._baselines

    def test_key_of_variants(self):
        assert UiaWorkerCapture._key_of({"k": "rid", "v": [1, 2]}) == "rid:[1, 2]"
        assert UiaWorkerCapture._key_of({"k": "hwnd", "v": 5}) == "hwnd:5"
        assert UiaWorkerCapture._key_of("raw") == "raw"


class TestGetTypedText:
    def _cap_with(self, baseline: str, current: str, age: float = 0.0) -> UiaWorkerCapture:
        cap = UiaWorkerCapture(interval=0.4, should_capture=lambda: True)
        cap._baselines["hwnd:1"] = baseline
        cap._last_snapshot = ("hwnd:1", current, time.time() - age)
        return cap

    def test_no_snapshot_returns_keyboard(self):
        cap = UiaWorkerCapture(interval=0.4)
        assert cap.get_typed_text("pinyin") == "pinyin"

    def test_stale_snapshot_returns_keyboard(self):
        cap = self._cap_with("", "天线问题", age=5.0)
        assert cap.get_typed_text("tianxianwenti") == "tianxianwenti"

    def test_empty_delta_returns_keyboard(self):
        cap = self._cap_with("天线问题", "天线问题")
        assert cap.get_typed_text("tianxianwenti") == "tianxianwenti"

    def test_uia_chinese_wins_over_pinyin(self):
        """核心场景：UIA 有汉字、键盘只有拼音 → 用 UIA"""
        cap = self._cap_with("天线问题", "天线问题今天必须搞定GR1003")
        assert cap.get_typed_text("tianxiantiwentijintianbixudingGR1003") \
            == "今天必须搞定GR1003"

    def test_baseline_advances_after_read(self):
        cap = self._cap_with("", "天线问题")
        cap.get_typed_text("tianxianwenti")
        assert cap._baselines["hwnd:1"] == "天线问题"
        # 基线已推进 → 再次调用不应重复产出同一段
        assert cap.get_typed_text("tianxianwenti") == "tianxianwenti"

    def test_huge_delta_treated_as_paste(self):
        cap = self._cap_with("", "汉" * 500)
        assert cap.get_typed_text("a") == "a"

    def test_snapshot_per_control_isolated(self):
        cap = UiaWorkerCapture(interval=0.4, should_capture=lambda: True)
        cap._baselines["hwnd:1"] = "AAA"
        cap._baselines["hwnd:2"] = "BBB"
        cap._last_snapshot = ("hwnd:2", "BBB新内容", time.time())
        assert cap.get_typed_text("xinneirong") == "新内容"


# ==================== 4. 生命周期健壮性 ====================

class TestLifecycle:
    def test_status_shape(self):
        cap = UiaWorkerCapture(interval=0.4)
        st = cap.status()
        assert st["mode"] == "subprocess"
        assert st["alive"] is False
        assert st["ready"] is False
        assert st["pid"] is None

    def test_is_available_false_without_process(self):
        cap = UiaWorkerCapture(interval=0.4)
        assert cap.is_available is False

    def test_request_snapshot_is_noop(self):
        cap = UiaWorkerCapture(interval=0.4)
        cap.request_snapshot()  # 不应抛异常

    def test_stop_without_start(self):
        cap = UiaWorkerCapture(interval=0.4)
        cap.stop()  # 不应抛异常

    def test_interval_clamped(self):
        assert UiaWorkerCapture(interval=0.01)._interval == 0.2
