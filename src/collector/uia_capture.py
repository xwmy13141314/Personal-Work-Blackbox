"""UIA 焦点文本采集器 — 读取输入法上屏后的真实输入内容

原理
----
Windows UI Automation 可读取焦点控件的文本内容，即 IME 转换完成、用户选字
之后的最终文本。通过周期快照 + 基线差分提取每个输入片段的真实内容，在提交时
替换键盘钩子"按字母流逆推"的有损结果。

实测结论（2026-09-11，见 docs/输入记录准确性优化方案_v1.md §1）
----------------------------------------------------------------
| 应用类型              | 焦点控件类型      | 可读方式                     |
|-----------------------|-------------------|------------------------------|
| Win32 标准控件(记事本)| DocumentControl   | Value / Text / MSAA 三路全通 |
| Chromium(WorkBuddy等) | EditControl       | Value / Text / MSAA 三路全通 |
| Chromium 非输入区     | **GroupControl**  | **拒绝**（Name 装着整页文本）|
| WPS 表格单元格        | (无编辑控件)      | UIA 读不到 → 走 wps_com.py   |

两条关键设计判据
----------------
1. **焦点元素类型判据**：只接受 EditControl / DocumentControl。
   GroupControl、PaneControl、WindowControl 等容器**必须拒绝** ——
   实测 Chromium 的容器节点 Name 里装着整个页面的文本（661 字符），
   直接入库会把整屏内容当成"用户输入"。
2. **必须先判类型再取值**：焦点不在输入框时（点到页面空白处），
   GetFocusedControl() 会返回容器节点，此时应视为"无数据"而非"输入内容"。

读取顺序（三路降级）
--------------------
    ValuePattern.Value          → 输入框首选（Chromium / Win32 Edit）
    TextPattern.DocumentRange   → 文档类首选（记事本 / 富文本）
    LegacyIAccessiblePattern.Value → MSAA 桥兜底（老控件）

其他设计要点
------------
- 所有 UIA 调用固定在单一专用线程执行（COM 单元线程限制），
  其他线程通过 request_snapshot() 异步触发快照、get_typed_text() 读取差分结果
- 每个控件首次被观察到时记录基线（已有内容不算新输入），提交时基线推进
- 密码控件（IsPassword）跳过；黑名单应用/隐私模式由 should_capture 回调控制
- 连续失败时自动退避 60s，不影响键盘钩子链路
"""

from __future__ import annotations

import ctypes
import logging
import re
import threading
import time
from typing import Callable

try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
except Exception:  # 非 Windows 平台
    _user32 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 注意：uiautomation / comtypes 必须**惰性导入**，且只能在子进程里导入！
#
# 实测（2026-09-14，见 docs/输入记录准确性优化方案_v1.md §4）：
# 主进程一旦 `import comtypes`（uiautomation 的依赖），pywebview 的 WebView2
# 窗口就会彻底失效 —— 浏览器进程起不来（msedgewebview2 进程数 0）、
# 页面永远加载不出（loaded 事件不触发），表现为"白屏/黑屏窗口"。
# 拿掉该导入后立即恢复正常（进程数 6、loaded=True），与导入顺序、时机无关。
#
# 因此：UIA 采集整体隔离到 uia_worker.py 子进程，主进程只读取子进程的文本输出。
# 本模块被主进程导入时**不得**触碰 uiautomation。
# ---------------------------------------------------------------------------

auto = None  # 由 _load_uia() 在子进程中填充
# 常量兜底：与 UIAutomationClient 的 PatternId 枚举一致，
# 这样纯逻辑（差分/合并/判据）在主进程与未装库的环境下依然可用/可测
_PID_VALUE, _PID_TEXT, _PID_LEGACY = 10002, 10014, 10018
_HAS_UIA = False


def _load_uia() -> bool:
    """惰性导入 uiautomation（**只允许在 UIA 工作子进程中调用**）

    主进程调用会破坏 WebView2（见模块顶部说明）。
    """
    global auto, _HAS_UIA, _PID_VALUE, _PID_TEXT, _PID_LEGACY
    if _HAS_UIA:
        return True
    try:
        import uiautomation as _auto

        auto = _auto
        _PID_VALUE = _auto.PatternId.ValuePattern
        _PID_TEXT = _auto.PatternId.TextPattern
        _PID_LEGACY = _auto.PatternId.LegacyIAccessiblePattern
        _HAS_UIA = True
    except Exception:
        logger.warning("uiautomation 不可用（pip install uiautomation）", exc_info=True)
        _HAS_UIA = False
    return _HAS_UIA

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

#: 允许作为"编辑目标"的控件类型（实测确认）
_EDITABLE_TYPES = frozenset(("EditControl", "DocumentControl"))

#: 明确拒绝的容器类型（其 Name 是整页/整块文本，非用户输入）
_REJECTED_TYPES = frozenset((
    "GroupControl", "PaneControl", "WindowControl", "ListControl",
    "TreeControl", "TableControl", "DataGridControl", "MenuControl",
    "ToolBarControl", "TabControl", "ScrollBarControl",
))

#: 判为"粘贴/整体替换"的增量长度阈值
_PASTE_THRESHOLD = 300


def diff_increment(old: str, new: str) -> str:
    """从全量文本变化中提取本次新增内容

    - 尾部追加（主模式，实测最常见）→ 直接取增量
    - 退格删除 → 空串
    - 中间修改/替换 → 取最长公共前缀之后的部分
    """
    if not new:
        return ""
    if not old:
        return new
    if new == old:
        return ""
    if new.startswith(old):
        return new[len(old):]
    if old.startswith(new):
        return ""  # 纯删除，不产出新文本
    lcp = 0
    for a, b in zip(old, new):
        if a != b:
            break
        lcp += 1
    return new[lcp:]


def merge_keyboard_and_uia(keyboard_text: str, uia_delta: str) -> str:
    """键盘文本与 UIA 增量的合并策略

    核心场景：UIA 有汉字而键盘只有拼音字母 → 采用 UIA（真实上屏文本）。
    提为模块级函数，便于主进程（uia_worker_capture.py）与子进程共用同一套策略。
    """
    # 防呆：增量异常大（切换输入框/整段粘贴）→ 保留键盘文本
    if len(uia_delta) > max(80, len(keyboard_text) * 4 + 40) \
            and len(uia_delta) > _PASTE_THRESHOLD:
        return keyboard_text

    kb_cjk = len(_CJK_RE.findall(keyboard_text))
    uia_cjk = len(_CJK_RE.findall(uia_delta))

    if uia_cjk > kb_cjk:
        return uia_delta
    if uia_cjk == kb_cjk and len(uia_delta) >= len(keyboard_text):
        return uia_delta
    return keyboard_text


class UiaTextCapture:
    """UIA 焦点文本采集器（单线程 COM + 周期快照 + 基线差分）"""

    def __init__(
        self,
        interval: float = 0.5,
        should_capture: Callable[[], bool] | None = None,
        max_text_length: int = 4000,
        editable_only: bool = True,
    ):
        """
        Args:
            interval: 周期快照间隔（秒），默认 0.5s（实测可完整跟上逐字输入）
            should_capture: 采集前置检查（隐私模式/黑名单），返回 False 跳过本轮
            max_text_length: 单次读取的最大字符数
            editable_only: 是否启用焦点类型判据（拒绝容器节点），默认开启
        """
        self._interval = max(0.2, interval)
        self._should_capture = should_capture
        self._max_text_length = max_text_length
        self._editable_only = editable_only

        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop_flag = False
        self._thread: threading.Thread | None = None

        # 控件键 → 上次提交时的基线
        self._baselines: dict[object, str] = {}
        # 最近一次快照 (control_key, text, timestamp)
        self._last_snapshot: tuple[object, str, float] | None = None
        # 最近一次采集到的读法（诊断用：V/T/A）
        self._last_way: str = ""
        self._last_control_type: str = ""

        self._disabled_until = 0.0
        self._fail_count = 0

    # ==================== 生命周期 ====================

    def start(self):
        if not _load_uia():
            logger.warning("UIA 增强采集未启用：pip install uiautomation")
            return
        if self._thread:
            return
        self._stop_flag = False
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="UiaCapture",
        )
        self._thread.start()
        logger.info("UIA 焦点文本采集已启动 (interval=%.2fs)", self._interval)

    def stop(self):
        self._stop_flag = True
        self._wakeup.set()
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None

    def request_snapshot(self):
        """异步请求立即快照（非阻塞；IME 上屏时调用，尽快记录当前输入框内容）"""
        self._wakeup.set()

    @property
    def is_available(self) -> bool:
        return _HAS_UIA

    @property
    def last_way(self) -> str:
        """最近一次成功读取所用的方式（V/T/A），供诊断使用"""
        return self._last_way

    # ==================== 采集线程 ====================

    def _thread_main(self):
        # COM 初始化（本线程专用，COM 单元限制）
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            logger.debug("comtypes CoInitialize 失败（可能已初始化）", exc_info=True)

        while not self._stop_flag:
            self._wakeup.wait(self._interval)
            self._wakeup.clear()
            if self._stop_flag:
                break
            if self._should_capture is not None and not self._should_capture():
                continue
            self._take_snapshot()

    def _take_snapshot(self):
        """读取焦点控件文本并更新快照状态"""
        if time.time() < self._disabled_until:
            return
        try:
            el = auto.GetFocusedControl()
            if el is None:
                return
            if self._is_password_control(el):
                return

            ctype = self._control_type(el)
            text, way = None, ""

            # 第一优先：焦点元素本身可读（Chromium 输入框 / 标准编辑控件）
            if self._editable_only and not self._is_editable(el, ctype):
                text, way = None, ""
            else:
                text, way = self._read_text(el)
                target = el

            # 第二优先：焦点元素不可读 → 解析真正的编辑控件
            # 场景：Win11 记事本(WinUI3)焦点报在输入站点容器
            # (PaneControl / Windows.UI.Input.InputSite.WindowClass) 上，
            # 而编辑控件 DocumentControl 在窗口的另一分支
            if text is None:
                child = self._find_edit_target(el)
                if child is not None:
                    t2, w2 = self._read_text(child)
                    if t2 is not None:
                        text, way, target = t2, w2, child

            if text is None:
                # 焦点处确无可读编辑控件（点到空白/容器）→ 视为无数据
                self._last_way = ""
                self._last_control_type = ctype
                return

            key = self._control_key(target)
            if key is None:
                return

            self._last_way = way
            self._last_control_type = self._control_type(target)
            with self._lock:
                # 控件首次出现：当前内容即为基线（已有内容不算新输入）
                if key not in self._baselines:
                    self._baselines[key] = text
                self._last_snapshot = (key, text, time.time())
                self._prune_states()
            self._fail_count = 0
        except Exception:
            self._fail_count += 1
            if self._fail_count >= 5:
                self._disabled_until = time.time() + 60
                self._fail_count = 0
                logger.warning("UIA 采集连续失败，暂停 60 秒", exc_info=True)

    def _prune_states(self):
        """限制状态字典规模（调用方需持锁）"""
        if len(self._baselines) > 128:
            keep = self._last_snapshot[0] if self._last_snapshot else None
            self._baselines = {k: v for k, v in self._baselines.items() if k == keep}

    # ==================== UIA 读取辅助 ====================

    @staticmethod
    def _control_type(el) -> str:
        try:
            return el.ControlTypeName or ""
        except Exception:
            return ""

    @classmethod
    def _is_editable(cls, el, ctype: str | None = None) -> bool:
        """焦点元素类型判据

        只接受 EditControl / DocumentControl；显式拒绝已知容器类型。
        类型未知时**放行** —— 因为容器节点通常不支持 ValuePattern/TextPattern，
        会被 _read_text 这道第二防线自然拦下（实测 Chromium 容器即如此）。
        """
        ctype = ctype if ctype is not None else cls._control_type(el)
        if ctype in _REJECTED_TYPES:
            return False
        if ctype in _EDITABLE_TYPES:
            return True
        return True

    def _search_subtree(self, root, max_depth: int = 12, max_nodes: int = 400):
        """在控件子树中查找可读的编辑控件（只认 EditControl / DocumentControl）"""
        if root is None:
            return None
        counter = [0]

        def walk(ctrl, depth: int):
            if ctrl is None or depth > max_depth or counter[0] > max_nodes:
                return None
            counter[0] += 1
            if self._control_type(ctrl) in _EDITABLE_TYPES:
                return ctrl
            try:
                child = ctrl.GetFirstChildControl()
            except Exception:
                return None
            while child is not None:
                found = walk(child, depth + 1)
                if found is not None:
                    return found
                if counter[0] > max_nodes:
                    return None
                try:
                    child = child.GetNextSiblingControl()
                except Exception:
                    return None
            return None

        try:
            return walk(root, 0)
        except Exception:
            return None

    def _find_edit_target(self, focus_el):
        """解析出真正的编辑控件

        WinUI3/UWP（如 Win11 记事本）的控件树结构：
            WindowControl class=Notepad
              PaneControl class=NotepadTextBox
                DocumentControl class=RichEditD2DPT   ← 编辑控件
              PaneControl class=DesktopWindowContentBridge
                PaneControl class=Windows.UI.Input.InputSite.WindowClass  ← 焦点在这

        即"焦点元素"与"编辑控件"是**兄弟分支**，且焦点元素的父链通往桌面
        （XAML 岛特性），所以既不能向下搜、也不能沿父链找窗口。
        正确做法：取**当前前台窗口**的句柄 → 转 UIA 元素 → 在其子树中搜索。
        """
        # 1) 先在焦点元素自身子树里找（部分应用编辑控件就在焦点下）
        found = self._search_subtree(focus_el, max_depth=8, max_nodes=200)
        if found is not None:
            return found

        # 2) 退回到"前台窗口子树"搜索
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return None
            win = auto.ControlFromHandle(hwnd)
            if win is None:
                return None
            return self._search_subtree(win, max_depth=12, max_nodes=400)
        except Exception:
            return None

    @staticmethod
    def _is_password_control(el) -> bool:
        """密码控件保护：不读取密码框内容"""
        try:
            if el.IsPassword:
                return True
        except Exception:
            pass
        return False

    def _read_text(self, el) -> tuple[str | None, str]:
        """读取控件文本，三路降级

        Returns:
            (文本, 读法标记)；不可读时返回 (None, "")
            文本可为空串 = 输入框被清空
        """
        # V: ValuePattern（输入框首选）
        try:
            vp = el.GetPattern(_PID_VALUE)
            if vp is not None:
                v = vp.Value
                if v is not None:
                    return str(v)[: self._max_text_length], "V"
        except Exception:
            pass

        # T: TextPattern（文档类首选）
        try:
            tp = el.GetPattern(_PID_TEXT)
            if tp is not None:
                t = tp.DocumentRange.GetText(self._max_text_length)
                if t is not None:
                    return str(t)[: self._max_text_length], "T"
        except Exception:
            pass

        # A: MSAA 桥（老控件兜底）
        try:
            ap = el.GetPattern(_PID_LEGACY)
            if ap is not None:
                v = ap.Value
                if v is not None:
                    return str(v)[: self._max_text_length], "A"
        except Exception:
            pass

        return None, ""

    @staticmethod
    def _control_key(el):
        """控件唯一键：RuntimeId 优先，原生窗口句柄兜底"""
        try:
            rid = el.RuntimeId
            if rid:
                return ("rid", tuple(rid))
        except Exception:
            pass
        try:
            hwnd = el.NativeWindowHandle
            if hwnd:
                return ("hwnd", hwnd)
        except Exception:
            pass
        return None

    # ==================== 提交时差分 ====================

    def get_typed_text(self, keyboard_text: str) -> str:
        """提交片段时调用：结合焦点控件快照与键盘文本，返回更接近真实输入的文本

        UIA 增量可用且质量优于键盘推算时替换之，否则原样返回键盘文本。
        """
        with self._lock:
            snap = self._last_snapshot
        if snap is None:
            return keyboard_text

        key, text, ts = snap
        if time.time() - ts > 2.5:
            return keyboard_text  # 快照过期（采集退避/停摆），交回键盘文本

        with self._lock:
            baseline = self._baselines.get(key, "")
            # 基线推进到当前快照：即使本轮差分为空，下轮也从最新内容起算
            self._baselines[key] = text

        delta = diff_increment(baseline, text)
        if not delta.strip():
            return keyboard_text
        return self._merge(keyboard_text, delta)

    def _merge(self, keyboard_text: str, uia_delta: str) -> str:
        """键盘文本与 UIA 增量的合并策略（见模块级 merge_keyboard_and_uia）"""
        return merge_keyboard_and_uia(keyboard_text, uia_delta)
