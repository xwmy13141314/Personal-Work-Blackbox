"""macOS 原生采集器：活动窗口 / 剪贴板 / 键盘文本。

设计要点：
- 所有 pyobjc 调用延迟 import（方法内），保证非 darwin 平台 import 本模块不崩。
- 三个采集器的回调契约与 Windows 端（blackbox_runtime.BlackboxRuntimeBridge）完全一致，
  因此 BlackboxAdapter + KeyboardTextBuffer 可零改动复用。
- 权限缺失时打印中文提示并优雅降级，绝不抛异常阻断其余采集。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class KeyEvent:
    # 满足 KeyboardTextBuffer.handle_key_event 的 getattr 取值契约
    is_printable_char: bool = False
    char: str = ""
    is_backspace: bool = False
    is_enter: bool = False
    is_tab: bool = False


@dataclass
class WindowContext:
    process_name: str = ""
    window_title: str = ""
    bundle_id: str = ""
    pid: int = 0


@dataclass
class ClipboardRecord:
    content: str
    source_process: str = ""
    source_window: str = ""


class MacWindowTracker:
    """轮询前台应用 + 窗口标题，切换时回调 on_switch(from_ctx, to_ctx, duration)。"""

    def __init__(self, on_switch, poll_interval: float = 1.0):
        self._on_switch = on_switch
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._current: WindowContext | None = None
        self._since: float = time.monotonic()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="mac-window", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ctx = self._snapshot()
                if ctx is not None:
                    self._maybe_emit(ctx)
            except Exception:
                pass  # 单次轮询失败不中断
            self._stop.wait(self._poll_interval)

    def _snapshot(self) -> WindowContext | None:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        name = str(app.localizedName() or "")
        bid = str(app.bundleIdentifier() or "")
        pid = int(app.processIdentifier() or 0)
        title = self._window_title_for_pid(pid)
        return WindowContext(process_name=name, window_title=title, bundle_id=bid, pid=pid)

    def _window_title_for_pid(self, pid: int) -> str:
        # 缺"屏幕录制"权限时 kCGWindowName 取不到 → 返回 ""，process_name 仍有效
        try:
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
                kCGWindowOwnerPID,
                kCGWindowName,
                kCGWindowLayer,
            )
            windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
            for w in windows:
                if w.get(kCGWindowOwnerPID) == pid:
                    if w.get(kCGWindowLayer, 0) == 0:  # 仅正常窗口层
                        name = w.get(kCGWindowName, "")
                        if name:
                            return str(name)
        except Exception:
            pass
        return ""

    def _maybe_emit(self, ctx: WindowContext) -> None:
        now = time.monotonic()
        prev = self._current
        if prev is None:
            self._current = ctx
            self._since = now
            return
        switched = prev.process_name != ctx.process_name or prev.window_title != ctx.window_title
        if switched:
            duration = now - self._since
            self._current = ctx
            self._since = now
            try:
                self._on_switch(prev, ctx, duration)
            except Exception:
                pass


class MacClipboardMonitor:
    """轮询 pasteboard changeCount，变化时回调 on_change(ClipboardRecord)。"""

    def __init__(self, on_change, max_length: int = 400, poll_interval: float = 0.5):
        self._on_change = on_change
        self._max_length = max_length
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_count: int | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="mac-clipboard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        from AppKit import NSPasteboard, NSStringPboardType
        while not self._stop.is_set():
            try:
                pb = NSPasteboard.generalPasteboard()
                count = pb.changeCount()
                if self._last_count is not None and count != self._last_count:
                    self._handle(pb, NSStringPboardType)
                self._last_count = count
            except Exception:
                pass
            self._stop.wait(self._poll_interval)

    def _handle(self, pb, pb_type) -> None:
        content = pb.stringForType_(pb_type)
        if not content:
            return
        content = str(content)
        if len(content) > self._max_length:
            content = content[: self._max_length]
        # macOS 不暴露"谁复制了" → 用前台 app 名近似
        proc = ""
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is not None:
                proc = str(app.localizedName() or "")
        except Exception:
            pass
        record = ClipboardRecord(content=content, source_process=proc, source_window="")
        try:
            self._on_change(record)
        except Exception:
            pass


class MacKeyboardHook:
    """经 CGEventTap 监听按键，缓冲前回调 on_event(KeyEvent)。

    需"输入监控"权限（kCGEventTapOptionListen 只需此轻量权限）。
    权限缺失时打印中文提示并优雅返回，不抛异常。
    """

    _KEY_BACKSPACE = 51
    _KEY_RETURN = 36
    _KEY_TAB = 48

    def __init__(self, on_event, capture_hotkeys: bool = False):
        self._on_event = on_event
        self._capture_hotkeys = capture_hotkeys
        self._thread: threading.Thread | None = None
        self._tap = None
        self._source = None
        self._run_loop = None
        self._started = threading.Event()
        # 延迟填充：Quartz + CoreFoundation 符号
        self._Q = None
        self._cf = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="mac-keyboard", daemon=True)
        self._thread.start()
        self._started.wait(timeout=5.0)  # 等初始化结果（成功或降级）

    def stop(self) -> None:
        if self._run_loop is not None and self._cf is not None:
            try:
                self._cf["stop"](self._run_loop)  # CFRunLoopStop，跨线程安全
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._tap is not None and self._Q is not None:
            try:
                self._Q.CFMachPortInvalidate(self._tap)
            except Exception:
                pass

    def _run(self) -> None:
        if not self._init_native():
            return
        if not self._ensure_permission():
            self._started.set()
            return
        if not self._create_tap():
            self._started.set()
            return

        Q = self._Q
        cf = self._cf
        self._run_loop = cf["get_current"]()
        self._source = cf["create_source"](None, self._tap, 0)
        cf["add_source"](self._run_loop, self._source, cf["default_mode"])
        Q.CGEventTapEnable(self._tap, True)
        self._started.set()
        cf["run"]()  # 阻塞，直到 stop() 调 CFRunLoopStop

    def _init_native(self) -> bool:
        try:
            import Quartz
            from CoreFoundation import (
                CFMachPortCreateRunLoopSource,
                CFRunLoopAddSource,
                CFRunLoopGetCurrent,
                CFRunLoopRun,
                CFRunLoopStop,
                kCFRunLoopDefaultMode,
            )
            self._Q = Quartz
            self._cf = {
                "create_source": CFMachPortCreateRunLoopSource,
                "add_source": CFRunLoopAddSource,
                "get_current": CFRunLoopGetCurrent,
                "run": CFRunLoopRun,
                "stop": CFRunLoopStop,
                "default_mode": kCFRunLoopDefaultMode,
            }
            return True
        except Exception as exc:  # pyobjc 未装 / 非 darwin
            print(f"[mac-keyboard] 无法加载 pyobjc 原生库：{exc}。键盘采集已禁用（窗口/剪贴板不受影响）。")
            return False

    def _ensure_permission(self) -> bool:
        Q = self._Q
        try:
            granted = bool(Q.CGPreflightListenEventAccess())  # 不弹窗
        except Exception:
            granted = False
        if granted:
            return True
        try:
            Q.CGRequestListenEventAccess()  # 触发系统"输入监控"授权弹窗
        except Exception:
            pass
        try:
            granted = bool(Q.CGPreflightListenEventAccess())
        except Exception:
            granted = False
        if not granted:
            print(
                "[mac-keyboard] 未获得「输入监控」权限。键盘采集已禁用（窗口/剪贴板不受影响）。\n"
                "请到 系统设置 → 隐私与安全性 → 输入监控，勾选本程序（或终端）后"
                "完全退出本进程并重试（首次授权通常需重启进程才生效）。"
            )
        return granted

    def _create_tap(self) -> bool:
        Q = self._Q
        mask = 1 << Q.kCGEventKeyDown
        if self._capture_hotkeys:
            mask |= 1 << Q.kCGEventFlagsChanged
        # kCGEventTapOptionListenOnly(1)：被动监听，只需"输入监控"权限（非"辅助功能"）
        self._tap = Q.CGEventTapCreate(
            Q.kCGSessionEventTap,
            Q.kCGHeadInsertEventTap,
            Q.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            print(
                "[mac-keyboard] CGEventTapCreate 返回 None（权限被拒或被 MDM 拦截）。"
                "键盘采集已禁用（窗口/剪贴板不受影响）。"
            )
            return False
        return True

    # pyobjc CGEventTapCallBack 签名：(proxy, type, event, refcon)
    def _callback(self, proxy, event_type, event, refcon):
        try:
            Q = self._Q
            keycode = int(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode))
            ev: KeyEvent | None = None
            if keycode == self._KEY_BACKSPACE:
                ev = KeyEvent(is_backspace=True)
            elif keycode == self._KEY_RETURN:
                ev = KeyEvent(is_enter=True)
            elif keycode == self._KEY_TAB:
                ev = KeyEvent(is_tab=True)
            else:
                char = self._char_from_event(event)
                if char and (char.isprintable() or char in (" ", "　")):
                    ev = KeyEvent(is_printable_char=True, char=char)
            if ev is not None:
                self._on_event(ev)  # 仅推入内存 buffer，禁做 IO
        except Exception:
            pass
        return event  # Listen 模式返回值被忽略，返回 event 安全

    def _char_from_event(self, event) -> str:
        # pyobjc 下 CGEventKeyboardGetUnicodeString 返回形态可能是 (str, int) / str / (int, str)，容错
        try:
            result = self._Q.CGEventKeyboardGetUnicodeString(event, 4)
        except Exception:
            return ""
        if isinstance(result, str):
            return result
        if isinstance(result, (tuple, list)):
            for item in result:
                if isinstance(item, str) and item:
                    return item
        return ""
