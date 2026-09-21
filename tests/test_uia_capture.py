"""采集层专项测试 — UIA 焦点判据 / 差分引擎 / 三路仲裁

覆盖范围
--------
1. `diff_increment` 差分算法：尾部追加、退格删除、中间修改、空值、粘贴
2. `_is_editable` 焦点类型判据：接受 Edit/Document，拒绝 Group/Pane/Window 等容器
3. `_read_text` 三路降级：Value → Text → MSAA
4. `_merge` 合并策略：UIA 汉字优先、异常增量防呆
5. 基线隔离：不同控件互不污染
6. `CaptureRouter` 仲裁：COM 优先 > UIA > 键盘兜底、accurate_mode 开关
7. `WpsComCapture` 差分与降级
8. 异常容错：采集器抛异常不影响主链路

所有用例均不依赖真实 UIA/COM 环境（用桩对象），可在任意机器运行。
"""

from __future__ import annotations

import threading
import time

import pytest

from src.collector.uia_capture import UiaTextCapture, diff_increment
from src.collector.capture_router import CaptureRouter


# ==================== 1. 差分算法 ====================

class TestDiffIncrement:
    """差分引擎：从全量文本变化中提取本次新增内容"""

    def test_tail_append_basic(self):
        assert diff_increment("上面", "上面两句") == "两句"

    def test_tail_append_incremental_steps(self):
        """实测场景：逐字增长"""
        old = "上面两句是我"
        new = "上面两句是我打的"
        assert diff_increment(old, new) == "打的"

    def test_backspace_returns_empty(self):
        assert diff_increment("今天要完成", "今天要") == ""

    def test_identical_returns_empty(self):
        assert diff_increment("相同", "相同") == ""

    def test_empty_old_returns_new(self):
        assert diff_increment("", "全新内容") == "全新内容"

    def test_empty_new_returns_empty(self):
        assert diff_increment("有内容", "") == ""

    def test_middle_modification(self):
        """中间插入：取最长公共前缀之后的部分"""
        assert diff_increment("请查看图内容", "请查看图片内容") == "片内容"

    def test_full_replacement(self):
        """完全替换：无公共前缀"""
        assert diff_increment("abc", "xyz") == "xyz"

    def test_hanzi_with_punctuation(self):
        """标点也算增量（实测中全角标点必须保留）"""
        assert diff_increment("你好", "你好，世界") == "，世界"

    def test_gr_number_not_split(self):
        """编号整体作为增量"""
        assert diff_increment("项目", "项目GR1003") == "GR1003"


# ==================== 2. 焦点类型判据 ====================

class _StubControl:
    """UIA 控件桩对象"""

    def __init__(self, control_type: str, value: str | None = None,
                 text: str | None = None, msaa: str | None = None,
                 is_password: bool = False):
        self.ControlTypeName = control_type
        self._value = value
        self._text = text
        self._msaa = msaa
        self.IsPassword = is_password
        self.RuntimeId = [1, 2, 3]

    def GetPattern(self, pattern_id):
        # 用数字常量匹配，避免依赖 uiautomation 是否安装
        if pattern_id == 10002 and self._value is not None:
            return _StubPattern(self._value)
        if pattern_id == 10014 and self._text is not None:
            return _StubTextPattern(self._text)
        if pattern_id == 10018 and self._msaa is not None:
            return _StubPattern(self._msaa)
        return None


class _StubPattern:
    def __init__(self, value):
        self.Value = value


class _StubTextPattern:
    def __init__(self, text):
        self.DocumentRange = _StubRange(text)


class _StubRange:
    def __init__(self, text):
        self._text = text

    def GetText(self, max_length: int = 4000):
        return self._text[:max_length]


class TestFocusTypeGuard:
    """焦点元素类型判据：这是采集准确性的第一道防线"""

    @pytest.mark.parametrize("ctype", ["EditControl", "DocumentControl"])
    def test_accepts_editable_types(self, ctype):
        assert UiaTextCapture._is_editable(_StubControl(ctype)) is True

    @pytest.mark.parametrize("ctype", [
        "GroupControl", "PaneControl", "WindowControl", "ListControl",
        "TreeControl", "TableControl", "MenuControl", "ToolBarControl",
    ])
    def test_rejects_container_types(self, ctype):
        """容器节点的 Name 装着整页文本，必须拒绝"""
        assert UiaTextCapture._is_editable(_StubControl(ctype)) is False

    def test_unknown_type_allowed_as_fallback(self):
        """类型未知时放行：靠 _read_text 第二道防线拦截容器"""
        assert UiaTextCapture._is_editable(_StubControl("UnknownControl")) is True

    def test_editable_only_flag_can_be_disabled(self):
        cap = UiaTextCapture(editable_only=False)
        assert cap._editable_only is False


# ==================== 3. 三路读取降级 ====================

class TestReadTextFallback:
    """读取顺序：Value → Text → MSAA"""

    def test_value_pattern_first(self):
        cap = UiaTextCapture()
        ctrl = _StubControl("EditControl", value="来自Value", text="来自Text")
        text, way = cap._read_text(ctrl)
        assert (text, way) == ("来自Value", "V")

    def test_text_pattern_when_no_value(self):
        cap = UiaTextCapture()
        ctrl = _StubControl("DocumentControl", text="来自Text")
        text, way = cap._read_text(ctrl)
        assert (text, way) == ("来自Text", "T")

    def test_msaa_last_resort(self):
        cap = UiaTextCapture()
        ctrl = _StubControl("EditControl", msaa="来自MSAA")
        text, way = cap._read_text(ctrl)
        assert (text, way) == ("来自MSAA", "A")

    def test_unreadable_returns_none(self):
        cap = UiaTextCapture()
        ctrl = _StubControl("EditControl")
        text, way = cap._read_text(ctrl)
        assert text is None and way == ""

    def test_empty_value_is_valid(self):
        """空串代表输入框被清空，是合法值而非读取失败"""
        cap = UiaTextCapture()
        ctrl = _StubControl("EditControl", value="")
        text, way = cap._read_text(ctrl)
        assert text == "" and way == "V"

    def test_max_length_truncation(self):
        cap = UiaTextCapture(max_text_length=5)
        ctrl = _StubControl("EditControl", value="1234567890")
        text, _ = cap._read_text(ctrl)
        assert text == "12345"


# ==================== 4. 合并策略 ====================

class TestMergeStrategy:
    """UIA 增量与键盘文本的合并"""

    def test_uia_hanzi_wins_over_pinyin(self):
        cap = UiaTextCapture()
        # 键盘只有拼音，UIA 有汉字 → 用 UIA
        assert cap._merge("niqueding", "你确定") == "你确定"

    def test_keyboard_wins_when_uia_empty(self):
        cap = UiaTextCapture()
        assert cap._merge("hello", "") == "hello"

    def test_paste_guard_rejects_huge_delta(self):
        """增量异常大（整段粘贴/切换输入框）→ 保留键盘文本"""
        cap = UiaTextCapture()
        kb = "短"
        huge = "很长的内容" * 100
        assert cap._merge(kb, huge) == kb

    def test_uia_wins_when_longer_and_equal_hanzi(self):
        cap = UiaTextCapture()
        # 汉字数相同，UIA 更长（含标点）→ 用 UIA
        assert cap._merge("你好世界", "你好，世界") == "你好，世界"

    def test_keyboard_wins_when_shorter_uia(self):
        cap = UiaTextCapture()
        assert cap._merge("你好世界啊", "你好") == "你好世界啊"


# ==================== 5. 基线隔离 ====================

class TestBaselineIsolation:
    """不同控件/窗口的基线互不污染（修复 P1-5 跨窗口污染）"""

    def test_different_control_keys_have_separate_baselines(self):
        cap = UiaTextCapture()
        with cap._lock:
            cap._baselines[("hwnd", 1)] = "窗口A内容"
            cap._baselines[("hwnd", 2)] = "窗口B内容"
        assert cap._baselines[("hwnd", 1)] == "窗口A内容"
        assert cap._baselines[("hwnd", 2)] == "窗口B内容"

    def test_snapshot_none_returns_keyboard_text(self):
        cap = UiaTextCapture()
        assert cap.get_typed_text("原样返回") == "原样返回"

    def test_stale_snapshot_returns_keyboard_text(self):
        cap = UiaTextCapture()
        with cap._lock:
            cap._last_snapshot = (("hwnd", 1), "旧内容", time.time() - 10)
        assert cap.get_typed_text("键盘文本") == "键盘文本"

    def test_baseline_advances_after_commit(self):
        cap = UiaTextCapture()
        key = ("hwnd", 1)
        with cap._lock:
            cap._baselines[key] = "基线"
            cap._last_snapshot = (key, "基线新增", time.time())
        cap.get_typed_text("x")
        with cap._lock:
            assert cap._baselines[key] == "基线新增"


# ==================== 6. 三路仲裁 ====================

class _StubCapture:
    """采集器桩：可控返回"""

    def __init__(self, result: str, available: bool = True):
        self._result = result
        self._available = available
        self.start_called = False
        self.stop_called = False
        self.snapshot_called = False

    def start(self):
        self.start_called = True

    def stop(self):
        self.stop_called = True

    def request_snapshot(self):
        self.snapshot_called = True

    def get_typed_text(self, keyboard_text: str) -> str:
        return self._result if self._result else keyboard_text

    @property
    def is_available(self):
        return self._available


class TestCaptureRouter:
    """仲裁规则：COM > UIA > 键盘兜底"""

    def test_com_wins_over_uia(self):
        com = _StubCapture("COM结果")
        uia = _StubCapture("UIA结果")
        router = CaptureRouter(uia=uia, com=com)
        assert router.get_typed_text("键盘") == "COM结果"
        assert router.last_source == "com"

    def test_uia_used_when_com_empty(self):
        com = _StubCapture("")          # 无产出 → 原样返回键盘文本
        uia = _StubCapture("UIA结果")
        router = CaptureRouter(uia=uia, com=com)
        assert router.get_typed_text("键盘") == "UIA结果"
        assert router.last_source == "uia"

    def test_keyboard_fallback_when_all_empty(self):
        router = CaptureRouter(uia=_StubCapture(""), com=_StubCapture(""))
        assert router.get_typed_text("键盘文本") == "键盘文本"
        assert router.last_source == "keyboard"

    def test_accurate_mode_off_returns_keyboard(self):
        """总开关关闭 → 完全不介入"""
        com = _StubCapture("COM结果")
        uia = _StubCapture("UIA结果")
        router = CaptureRouter(uia=uia, com=com, accurate_mode=False)
        assert router.get_typed_text("键盘文本") == "键盘文本"
        assert router.last_source == "keyboard"

    def test_accurate_mode_off_does_not_start(self):
        com = _StubCapture("x")
        uia = _StubCapture("x")
        router = CaptureRouter(uia=uia, com=com, accurate_mode=False)
        router.start()
        assert com.start_called is False
        assert uia.start_called is False

    def test_start_starts_both(self):
        com, uia = _StubCapture("x"), _StubCapture("x")
        router = CaptureRouter(uia=uia, com=com)
        router.start()
        assert com.start_called and uia.start_called

    def test_stop_stops_both(self):
        com, uia = _StubCapture("x"), _StubCapture("x")
        router = CaptureRouter(uia=uia, com=com)
        router.stop()
        assert com.stop_called and uia.stop_called

    def test_request_snapshot_wakes_both(self):
        com, uia = _StubCapture("x"), _StubCapture("x")
        router = CaptureRouter(uia=uia, com=com)
        router.request_snapshot()
        assert com.snapshot_called and uia.snapshot_called

    def test_none_captures_are_safe(self):
        """两条路径都不可用时不能崩"""
        router = CaptureRouter(uia=None, com=None)
        assert router.get_typed_text("键盘") == "键盘"
        router.start()
        router.stop()
        router.request_snapshot()
        assert router.is_available is False

    def test_exception_in_capture_does_not_break(self):
        """采集器抛异常时必须优雅降级"""

        class _Boom:
            def get_typed_text(self, t):
                raise RuntimeError("boom")

            @property
            def is_available(self):
                return True

            def start(self):
                raise RuntimeError("boom")

            def stop(self):
                raise RuntimeError("boom")

            def request_snapshot(self):
                raise RuntimeError("boom")

        router = CaptureRouter(uia=_Boom(), com=_Boom())
        assert router.get_typed_text("键盘") == "键盘"
        router.start()   # 不应抛出

    def test_is_available_true_when_any_available(self):
        router = CaptureRouter(uia=_StubCapture("x", available=False),
                               com=_StubCapture("x", available=True))
        assert router.is_available is True

    def test_status_reports_both_paths(self):
        router = CaptureRouter(uia=_StubCapture("x"), com=_StubCapture("x"))
        st = router.status()
        assert st["accurate_mode"] is True
        assert st["uia"]["available"] is True
        assert st["com"]["available"] is True


# ==================== 7. WPS COM 差分与降级 ====================

class TestWpsComCapture:
    """COM 采集器的差分逻辑与安全降级"""

    def test_diff_increment_tail_append(self):
        from src.collector.wps_com import WpsComCapture
        assert WpsComCapture._diff_increment("前面", "前面后面") == "后面"

    def test_diff_increment_backspace(self):
        from src.collector.wps_com import WpsComCapture
        assert WpsComCapture._diff_increment("前面后面", "前面") == ""

    def test_diff_increment_identical(self):
        from src.collector.wps_com import WpsComCapture
        assert WpsComCapture._diff_increment("一样", "一样") == ""

    def test_diff_increment_middle_change(self):
        from src.collector.wps_com import WpsComCapture
        assert WpsComCapture._diff_increment("项目评估", "项目外观评估") == "外观评估"

    def test_no_snapshot_returns_keyboard(self):
        from src.collector.wps_com import WpsComCapture
        cap = WpsComCapture()
        assert cap.get_typed_text("键盘文本") == "键盘文本"

    def test_stale_snapshot_returns_keyboard(self):
        from src.collector.wps_com import WpsComCapture
        cap = WpsComCapture()
        with cap._lock:
            cap._last_snapshot = ("com::et.exe", "内容", time.time() - 10)
        assert cap.get_typed_text("键盘文本") == "键盘文本"

    def test_target_process_mapping(self):
        """WPS 表格的 COM 名要在**所有可能的进程名**下都能命中

        关键回归点：WPS 表格在前台常以外壳进程 `wps.exe` 出现，
        早期版本把 `wps.exe` 只映射到文字接口，导致表格完全采不到。
        """
        from src.collector.wps_com import _TARGET_PROCS
        assert "Ket.Application" in _TARGET_PROCS["et.exe"]
        assert "Ket.Application" in _TARGET_PROCS["wps.exe"]      # 外壳进程也必须能走表格
        assert "Excel.Application" in _TARGET_PROCS["excel.exe"]
        assert "Kwps.Application" in _TARGET_PROCS["winword.exe"]

    def test_unknown_process_not_in_targets(self):
        """非办公应用不在命中列表 → 采集器完全不触碰 COM（零开销）"""
        from src.collector.wps_com import _TARGET_PROCS
        assert "notepad.exe" not in _TARGET_PROCS
        assert "chrome.exe" not in _TARGET_PROCS


# ==================== 8. 子树搜索（WinUI3 场景）====================

class _TreeNode:
    """UIA 控件树桩节点"""

    def __init__(self, control_type: str, children: list | None = None,
                 value: str | None = None):
        self.ControlTypeName = control_type
        self._children = children or []
        self._value = value
        self.RuntimeId = [9, 9]
        self.NativeWindowHandle = 777

    def GetFirstChildControl(self):
        return self._children[0] if self._children else None

    def GetNextSiblingControl(self):
        return None

    def GetPattern(self, pattern_id):
        if pattern_id == 10002 and self._value is not None:
            return _StubPattern(self._value)
        return None


def _link(nodes: list) -> list:
    """把兄弟列表串成 GetNextSiblingControl 链"""
    for i, n in enumerate(nodes):
        n.GetNextSiblingControl = (lambda nxt: (lambda: nxt))(nodes[i + 1]) \
            if i + 1 < len(nodes) else (lambda: None)
    return nodes


class TestSubtreeSearch:
    """子树搜索：Win11 记事本(WinUI3)场景 —— 焦点与编辑控件是兄弟分支"""

    def test_finds_nested_document(self):
        doc = _TreeNode("DocumentControl", value="内容")
        inner = _TreeNode("PaneControl", _link([doc]))
        root = _TreeNode("WindowControl", _link([inner]))
        cap = UiaTextCapture()
        assert cap._search_subtree(root) is doc

    def test_returns_none_when_no_editable(self):
        inner = _TreeNode("TextControl")
        root = _TreeNode("WindowControl", _link([inner]))
        cap = UiaTextCapture()
        assert cap._search_subtree(root) is None

    def test_prefers_editable_over_container(self):
        doc = _TreeNode("DocumentControl", value="x")
        container = _TreeNode("PaneControl", _link([doc]))
        root = _TreeNode("WindowControl", _link([container]))
        cap = UiaTextCapture()
        found = cap._search_subtree(root)
        assert found.ControlTypeName == "DocumentControl"

    def test_finds_sibling_branch(self):
        """焦点分支无编辑控件，编辑控件在兄弟分支（记事本真实结构）"""
        focus_branch = _TreeNode("PaneControl", _link([_TreeNode("TabControl")]))
        edit_container = _TreeNode("PaneControl", _link([
            _TreeNode("DocumentControl", value="文本")]))
        root = _TreeNode("WindowControl", _link([edit_container, focus_branch]))
        cap = UiaTextCapture()
        assert cap._search_subtree(root).ControlTypeName == "DocumentControl"

    def test_depth_limit_respected(self):
        """超过深度限制不返回"""
        deep = _TreeNode("DocumentControl")
        node = deep
        for _ in range(20):
            node = _TreeNode("PaneControl", _link([node]))
        cap = UiaTextCapture()
        assert cap._search_subtree(node, max_depth=5) is None

    def test_handles_none_root(self):
        cap = UiaTextCapture()
        assert cap._search_subtree(None) is None


# ==================== 9. 单元格提交检测（WPS 回填）====================

class TestCommitDetection:
    """WPS 表格"提交"检测：值从无到有 / 变更时触发回调

    背景：编辑模式下 `ActiveCell.Value2` 返回 None，
    只有内容真正写入单元格（用户离开单元格）后才可读。
    上层据此把刚才入库的拼音片段替换成汉字。

    桩说明：新版 `_take_snapshot` 走"绑定 COM → duck typing → 地址回读"，
    因此 mock `_bind`/`_is_sheet`/`_read_active` 三个内部方法；
    `values` 按轮次提供 (addr, text)，模拟"编辑中(值 None) → 提交(有值)"。
    """

    def _make(self, monkeypatch, proc: str, values: list):
        from src.collector.wps_com import WpsComCapture
        calls: list[str] = []
        cap = WpsComCapture(on_committed=lambda t: calls.append(t))
        monkeypatch.setattr("src.collector.wps_com.get_foreground_process", lambda: proc)

        class _FakeApp:
            pass

        app = _FakeApp()
        monkeypatch.setattr(cap, "_bind", lambda p: app)
        monkeypatch.setattr(cap, "_is_sheet", lambda app: True)
        it = iter(values)
        monkeypatch.setattr(cap, "_read_active", lambda app: next(it))
        return cap, calls

    def test_commit_fires_on_new_content(self, monkeypatch):
        # 编辑中读到 None → 记录地址；提交后按地址回读成功 → 触发回调
        cap, calls = self._make(monkeypatch, "et.exe", [
            ("$A$1", None), ("$A$1", "今天要完成GR1003"),
        ])
        cap._take_snapshot()
        cap._take_snapshot()
        assert calls == ["今天要完成GR1003"]

    def test_same_content_not_refired(self, monkeypatch):
        """同一内容只通知一次，避免重复回填"""
        cap, calls = self._make(monkeypatch, "et.exe", [
            ("$A$1", None), ("$A$1", "你好"), ("$A$1", "你好"),
        ])
        cap._take_snapshot()
        cap._take_snapshot()
        cap._take_snapshot()
        assert calls == ["你好"]

    def test_content_change_fires_again(self, monkeypatch):
        cap, calls = self._make(monkeypatch, "et.exe", [
            ("$A$1", None), ("$A$1", "第一版"), ("$A$1", "第二版"),
        ])
        cap._take_snapshot()
        cap._take_snapshot()
        cap._take_snapshot()
        assert calls == ["第一版", "第二版"]

    def test_no_commit_when_editing(self, monkeypatch):
        """编辑模式（读到 None）不触发提交"""
        cap, calls = self._make(monkeypatch, "et.exe", [("$A$1", None)])
        cap._take_snapshot()
        assert calls == []

    def test_no_commit_for_non_target_process(self, monkeypatch):
        """非办公应用完全不触碰 COM，也不触发"""
        cap, calls = self._make(monkeypatch, "chrome.exe", [])
        cap._take_snapshot()
        assert calls == []

    def test_no_callback_when_not_provided(self, monkeypatch):
        """未提供回调时不报错"""
        from src.collector.wps_com import WpsComCapture
        cap = WpsComCapture()
        monkeypatch.setattr("src.collector.wps_com.get_foreground_process", lambda: "et.exe")

        class _FakeApp:
            pass

        app = _FakeApp()
        monkeypatch.setattr(cap, "_bind", lambda p: app)
        monkeypatch.setattr(cap, "_is_sheet", lambda app: True)
        vals = iter([("$A$1", None), ("$A$1", "内容")])
        monkeypatch.setattr(cap, "_read_active", lambda app: next(vals))
        cap._take_snapshot()
        cap._take_snapshot()  # 不应抛出

    def test_callback_exception_does_not_break_snapshot(self, monkeypatch):
        """回调抛异常不能影响采集主流程"""
        from src.collector.wps_com import WpsComCapture

        def boom(_t):
            raise RuntimeError("callback boom")

        cap = WpsComCapture(on_committed=boom)
        monkeypatch.setattr("src.collector.wps_com.get_foreground_process", lambda: "et.exe")

        class _FakeApp:
            pass

        app = _FakeApp()
        monkeypatch.setattr(cap, "_bind", lambda p: app)
        monkeypatch.setattr(cap, "_is_sheet", lambda app: True)
        vals = iter([("$A$1", None), ("$A$1", "内容")])
        monkeypatch.setattr(cap, "_read_active", lambda app: next(vals))
        cap._take_snapshot()
        cap._take_snapshot()
        assert cap._last_snapshot is not None   # 快照照样更新


# ==================== 10. 线程安全 ====================

class TestThreadSafety:
    """并发访问采集状态不应出错"""

    def test_concurrent_get_typed_text(self):
        cap = UiaTextCapture()
        key = ("hwnd", 1)
        with cap._lock:
            cap._baselines[key] = "基线"
            cap._last_snapshot = (key, "基线内容", time.time())

        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(50):
                    cap.get_typed_text("键盘")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_router_concurrent_calls(self):
        router = CaptureRouter(uia=_StubCapture("A"), com=_StubCapture("B"))
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(50):
                    router.get_typed_text("键盘")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
