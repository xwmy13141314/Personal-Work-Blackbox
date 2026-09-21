"""WPS / Office COM 文本采集器 — 从办公文档读取用户真实输入

为什么需要它
------------
实测结论(2026-09-11):WPS 表格(et.exe)的单元格文本**不通过 UIA 暴露** ——
焦点在单元格时,UIA 树只到窗口标题,读不到单元格内容。但 WPS 官方开放了
COM 自动化接口,可以精确读取当前活动单元格:

    app = win32com.client.GetActiveObject("Ket.Application")
    app.ActiveCell.Value2      # → '务必把这两个项目给确认下来'

覆盖范围
--------
| 应用      | 进程          | COM 类名            | 读取方式                    |
|-----------|---------------|---------------------|-----------------------------|
| WPS 表格  | et.exe        | Ket.Application     | ActiveCell.Value2 / .Text   |
| WPS 文字  | wps.exe       | Kwps.Application    | Selection.Text              |
| WPS 演示  | wpp.exe       | Kwpp.Application    | (无编辑文本,跳过)           |
| MS Excel  | EXCEL.EXE     | Excel.Application   | ActiveCell.Value2 / .Text   |
| MS Word   | WINWORD.EXE   | Word.Application    | Selection.Text              |

设计约束
--------
- **只读**:绝不写入/修改用户文档
- **零开销**:前台进程不在命中列表时,完全不触碰 COM
- **不新建实例**:优先 GetActiveObject 绑定运行中的实例;绝不启动新进程
- **静默降级**:绑定失败/超时/异常一律吞掉,不影响键盘钩子与 UIA 路径
- **单线程 COM**:COM 有单元线程限制,所有调用固定在专用线程
- **隐私优先**:复用 should_capture 回调,隐私模式/黑名单时直接跳过

接口与 UiaTextCapture 保持一致(start/stop/request_snapshot/get_typed_text),
便于 capture_router 统一仲裁。
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from pathlib import Path
from typing import Callable

try:
    import ctypes.wintypes as wt
except Exception:  # 非 Windows 平台
    wt = None

logger = logging.getLogger(__name__)

try:
    import pythoncom
    import win32com.client
    _HAS_COM = True
except Exception:
    _HAS_COM = False
    logger.info("pywin32 不可用，WPS/Office COM 采集不可用（可选功能）")

# 命中进程 → 可尝试的 COM 类名列表
#
# 重要（2026-09-11 实测修正）：**不能按进程名判断是表格还是文档**。
# WPS 表格在任务栏/前台窗口上报的进程常常是外壳 `wps.exe`，
# 而真正的表格组件是 `et.exe`。早期版本把 `wps.exe` 当作"文字类"、
# 走 Word 的 Selection 接口，导致 WPS 表格场景完全采集不到。
#
# 现在改为：**列出该进程所有可能的 COM 类，绑定成功后用 duck typing
# 判断是表格（有 ActiveCell）还是文档（有 Selection）**。
_TARGET_PROCS: dict[str, tuple[str, ...]] = {
    # WPS 表格（含外壳进程）
    "et.exe": ("Ket.Application", "Excel.Application"),
    "excel.exe": ("Excel.Application", "Ket.Application"),
    # WPS 文字（Kwps）也可能与表格外壳同名进程，所以把表格类也列进来一起试
    "wps.exe": ("Ket.Application", "Excel.Application", "Kwps.Application", "Word.Application"),
    "winword.exe": ("Word.Application", "Kwps.Application"),
    # WPS 演示 / PowerPoint（编辑文本能力有限，仅登记不强制）
    "wpp.exe": ("Kwpp.Application", "PowerPoint.Application"),
    "powerpnt.exe": ("PowerPoint.Application", "Kwpp.Application"),
}

_user32 = ctypes.WinDLL("user32", use_last_error=True) if hasattr(ctypes, "WinDLL") else None


def get_foreground_process() -> str:
    """获取前台窗口的进程名（小写）；失败返回空串"""
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        import win32api
        import win32con
        import win32process
        h = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        try:
            exe = win32process.GetModuleFileNameEx(h, 0)
        finally:
            win32api.CloseHandle(h)
        return Path(exe).name.lower()
    except Exception:
        return ""


class WpsComCapture:
    """WPS/Office COM 文本采集器（单线程 + 周期快照 + 基线差分）"""

    #: 单次 COM 调用的软超时（秒）——超时后本线程跳过本轮，避免卡死采集
    BIND_RETRY_SECONDS = 30.0

    def __init__(
        self,
        interval: float = 0.8,
        should_capture: Callable[[], bool] | None = None,
        max_text_length: int = 4000,
        on_committed: Callable[[str], None] | None = None,
    ):
        """
        Args:
            interval: 周期快照间隔（秒）
            should_capture: 采集前置检查（隐私模式/黑名单），返回 False 跳过本轮
            max_text_length: 单次读取的最大字符数
            on_committed: 单元格内容"提交"（从无到有 / 内容变更）时回调，
                参数为该单元格的完整文本。用于 WPS 表格的"提交回填"：
                编辑期间键盘钩子只能记下拼音，提交后用它换成汉字。
        """
        self._interval = max(0.2, interval)
        self._should_capture = should_capture
        self._max_text_length = max_text_length
        self._on_committed = on_committed

        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop_flag = False
        self._thread: threading.Thread | None = None

        # 控件键 → 上次提交基线
        self._baselines: dict[str, str] = {}
        self._last_snapshot: tuple[str, str, float] | None = None
        # 单元格地址 → 上次已通知"提交"的内容（避免重复回调；也用于判断"是否新输入"）
        self._last_committed: dict[str, str] = {}

        # 正在编辑中的单元格地址（编辑模式下读不到值，先记住地址，提交后按地址回读）
        # 为什么必须记住地址：用户提交（回车/点其他格）后 **ActiveCell 会移到下一个
        # 单元格**，此时再读 ActiveCell 只能读到空格子 → 永远回填不到刚提交的内容。
        # 实测（2026-09-14）：这正是"WPS 里明明打的是汉字、库里却一直是拼音"的原因。
        self._pending_addr: str | None = None
        self._pending_at: float = 0.0
        #: 待回读地址的有效期（秒），超过则放弃
        self.PENDING_TTL = 300.0

        self._app = None                 # COM 应用对象
        self._app_proc = ""             # 绑定时的进程名
        self._bind_failed_at = 0.0       # 上次绑定失败时间（做重试节流）
        self._fail_count = 0             # 连续失败计数

    # ==================== 生命周期 ====================

    def start(self):
        if not _HAS_COM:
            logger.info("WPS/Office COM 采集未启用：需要 pywin32")
            return
        if self._thread:
            return
        self._stop_flag = False
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="WpsComCapture",
        )
        self._thread.start()
        logger.info("WPS/Office COM 采集已启动 (interval=%.2fs)", self._interval)

    def stop(self):
        self._stop_flag = True
        self._wakeup.set()
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None
        with self._lock:
            self._app = None

    def request_snapshot(self):
        """异步请求立即快照（非阻塞）"""
        self._wakeup.set()

    @property
    def is_available(self) -> bool:
        return _HAS_COM

    # ==================== 采集线程 ====================

    def _thread_main(self):
        # COM 单元初始化（本线程专用）
        try:
            pythoncom.CoInitialize()
        except Exception:
            logger.debug("COM CoInitialize 失败（可能已初始化）", exc_info=True)

        try:
            while not self._stop_flag:
                self._wakeup.wait(self._interval)
                self._wakeup.clear()
                if self._stop_flag:
                    break
                if self._should_capture is not None and not self._should_capture():
                    continue
                self._take_snapshot()
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _take_snapshot(self):
        """读取当前活动单元格/选区文本，并检测"用户刚提交了某个单元格"

        提交检测的关键（2026-09-14 修复）
        --------------------------------
        WPS/Excel 提交（回车或点其他格）后 **ActiveCell 会跳到下一个单元格**，
        原来的实现只读 ActiveCell，于是只能读到空格子 → 刚提交的汉字永远读不到。
        现在改为：
          1. 编辑模式（Value2 为空）时，记住当前单元格**地址**
          2. 之后每一轮，按**地址**回读那个单元格，读到内容即视为提交
          3. 只对"经历过编辑状态的单元格"触发回调，避免把单元格原有内容
             误当成用户本次输入
        """
        proc = get_foreground_process()
        if proc not in _TARGET_PROCS:
            # 前台切走了：仍尝试回读待确认单元格（用户可能提交后立刻切窗口）
            if self._pending_addr:
                self._flush_pending(None)
            return  # 零开销：不是目标应用，不碰 COM

        app = self._bind(proc)
        if app is None:
            return

        # ---- 表格类：带地址的提交检测 ----
        if self._is_sheet(app):
            addr, text = self._read_active(app)
            if text is None:
                # 编辑模式（未回车）：先处理上一个待确认格，再记录当前格
                self._flush_pending(app, exclude=None)
                if addr:
                    self._pending_addr = addr
                    self._pending_at = time.time()
                return
            if self._last_committed.get(addr) == text:
                # 内容没变 → 可能是"编辑中读到的旧值"，标记为待观察，不算提交
                self._flush_pending(app, exclude=addr)
                if addr:
                    self._pending_addr = addr
                    self._pending_at = time.time()
            else:
                # 内容变了。只有"用户真的编辑过"的格才算新输入：
                #   - 该地址正处于待确认状态（编辑后提交），或
                #   - 该地址此前已被记录过（二次修改）
                typed = (addr == self._pending_addr) or (addr in self._last_committed)
                self._check_commit(addr, text, typed)
                self._flush_pending(app, exclude=addr)
            self._record_snapshot(addr, text)
            self._fail_count = 0
            return

        # ---- 文档类（Word/WPS 文字）：保持原有 Selection 逻辑 ----
        text = self._read_doc(app)
        if text is None:
            return
        if self._on_committed is not None:
            key = f"doc::{proc}"
            if text != self._last_committed.get(key):
                self._last_committed[key] = text
                self._notify(text)
        self._record_snapshot(f"com::{proc}", text)
        self._fail_count = 0

    # ==================== 提交检测辅助 ====================

    def _flush_pending(self, app, exclude: str | None = None):
        """按地址回读"待确认单元格"；读到内容即视为一次提交"""
        addr = self._pending_addr
        if not addr or addr == exclude:
            return
        if time.time() - self._pending_at > self.PENDING_TTL:
            self._pending_addr = None
            return
        if app is None:  # 前台已切走，重新绑定当前可用的表格实例
            app = self._bind_any()
            if app is None:
                return
        if not self._is_sheet(app):
            self._pending_addr = None
            return
        value = self._read_by_address(app, addr)
        if value is None or value == "":
            return  # 还没写入（仍在编辑）
        self._check_commit(addr, value, typed=True)
        self._pending_addr = None

    def _check_commit(self, addr: str, text: str, typed: bool):
        """内容变化时决定是否通知"提交"

        Args:
            typed: 该单元格是否经历过"用户编辑"状态。False 表示这是首次看到
                   单元格的既有内容，不能当成本次输入（否则会把旧内容回填进来）
        """
        if not addr:
            return
        if self._last_committed.get(addr) == text:
            return
        self._last_committed[addr] = text
        if len(self._last_committed) > 200:  # 规模有界
            self._last_committed = {addr: text}
        if typed and self._on_committed is not None:
            self._notify(text)

    def _notify(self, text: str):
        try:
            self._on_committed(text)
        except Exception:
            logger.debug("提交回调异常", exc_info=True)

    def _record_snapshot(self, key: str, text: str):
        """更新基线快照（供 get_typed_text 的差分使用）"""
        now = time.time()
        with self._lock:
            if key not in self._baselines:
                self._baselines[key] = text
            self._last_snapshot = (key, text, now)
            if len(self._baselines) > 64:
                self._baselines = {k: v for k, v in self._baselines.items() if k == key}

    @staticmethod
    def _control_key(proc: str) -> str:
        """控件键：进程名 + 天粒度，避免跨文档串扰"""
        return f"com::{proc}"

    # ==================== COM 读取 ====================

    def _bind(self, proc: str):
        """绑定运行中的 Office/WPS 实例（绝不新建进程）"""
        now = time.time()
        if self._app is not None and self._app_proc == proc:
            return self._app
        # 同一进程的绑定失败做节流重试，避免每轮都触发慢调用
        if self._app is None and self._app_proc == proc and \
                now - self._bind_failed_at < self.BIND_RETRY_SECONDS:
            return None

        classes = _TARGET_PROCS[proc]
        for cls in classes:
            try:
                self._app = win32com.client.GetActiveObject(cls)
                self._app_proc = proc
                logger.info("COM 已绑定 %s (%s)", cls, proc)
                return self._app
            except Exception:
                continue
        self._app = None
        self._app_proc = proc
        self._bind_failed_at = now
        return None

    @staticmethod
    def _is_sheet(app) -> bool:
        """用 duck typing 判断绑定到的是表格还是文档（不依赖进程名）

        WPS 表格在前台常以外壳进程 `wps.exe` 出现，按进程名判断会误走 Word 接口。
        """
        try:
            return hasattr(app, "ActiveCell")
        except Exception:
            return False

    def _read_active(self, app) -> tuple[str | None, str | None]:
        """读取当前活动单元格的 (地址, 文本)

        编辑模式下 Value2 为 None（内容尚未写入单元格），此时地址依然有效 ——
        地址正是"提交后按地址回读"的关键。
        """
        addr = None
        cell = None
        try:
            cell = app.ActiveCell
        except Exception:
            return None, None
        if cell is None:
            return None, None
        try:
            addr = str(cell.Address)
        except Exception:
            addr = None
        try:
            for attr in ("Value2", "Value", "Text"):
                try:
                    v = getattr(cell, attr)
                except Exception:
                    continue
                if v is not None and str(v) != "":
                    return addr, str(v)[: self._max_text_length]
        except Exception:
            pass
        return addr, None

    def _read_by_address(self, app, addr: str) -> str | None:
        """按地址回读单元格内容（提交后 ActiveCell 已移走，只能靠地址取回）"""
        for getter in (
            lambda: app.Range(addr),
            lambda: app.ActiveSheet.Range(addr),
        ):
            try:
                cell = getter()
                if cell is None:
                    continue
                for attr in ("Value2", "Value", "Text"):
                    try:
                        v = getattr(cell, attr)
                    except Exception:
                        continue
                    if v is not None and str(v) != "":
                        return str(v)[: self._max_text_length]
                return None
            except Exception:
                continue
        return None

    def _bind_any(self):
        """前台已切走时，尝试绑定任意一个可用的表格实例（用于回读待确认格）"""
        for proc in _TARGET_PROCS:
            try:
                app = self._bind(proc)
                if app is not None:
                    return app
            except Exception:
                continue
        return None

    def _read_document_text(self, proc: str) -> str | None:
        """读取文档当前内容；不可读返回 None（保留给 get_typed_text 路径使用）"""
        app = self._bind(proc)
        if app is None:
            return None
        if self._is_sheet(app):
            _addr, text = self._read_active(app)
            return text
        return self._read_doc(app)

    def _read_doc(self, app) -> str | None:
        """文字类：优先当前选区文本"""
        try:
            sel = app.Selection
            if sel is not None:
                try:
                    t = sel.Text
                    if t is not None:
                        return str(t)
                except Exception:
                    pass
        except Exception:
            pass
        return None

    # ==================== 提交时差分 ====================

    def get_typed_text(self, keyboard_text: str) -> str:
        """提交片段时调用：用 COM 读到的真实文本替换键盘推算文本

        与键盘文本差异不大或快照过期时,原样返回键盘文本。
        """
        with self._lock:
            snap = self._last_snapshot
        if snap is None:
            return keyboard_text

        key, text, ts = snap
        if time.time() - ts > 2.5:
            return keyboard_text  # 快照过期，交回键盘文本

        with self._lock:
            baseline = self._baselines.get(key, "")
            self._baselines[key] = text  # 基线推进

        delta = self._diff_increment(baseline, text)
        if not delta.strip():
            return keyboard_text
        return delta

    @staticmethod
    def _diff_increment(old: str, new: str) -> str:
        """从全量文本变化中提取本次新增内容

        - 尾部追加（主模式）→ 直接取增量
        - 退格删除 → 空
        - 中间修改/替换 → 取最长公共前缀之后的部分
        """
        if not old:
            return new
        if new == old:
            return ""
        if new.startswith(old):
            return new[len(old):]
        if old.startswith(new):
            return ""  # 删除操作，不产出新文本
        lcp = 0
        for a, b in zip(old, new):
            if a != b:
                break
            lcp += 1
        return new[lcp:]
