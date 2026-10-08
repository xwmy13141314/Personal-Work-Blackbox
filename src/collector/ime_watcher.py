"""中文输入法（IME）结果监听器 — macOS AXUIElement 轮询框架

CGEventTap 只能捕获按键流，无法直接获取中文输入法确认后的汉字文本
（IME 由系统接管，keydown 事件对中文输入只发 marked 事件）。本模块作为
键盘监听的补充，通过轮询前台聚焦控件的 AXValue，对比变化提取新增的中文
字符，经 is_ime_composition 通道发射 KeyEvent，复用 InputBuffer._on_ime_text
的拼音去重逻辑（自动移除缓冲区末尾的拼音字母）。

工作原理：
  1. 轮询 NSWorkspace.frontmostApplication 获取前台 PID
  2. AXUIElementCreateApplication(pid) → AXFocusedUIElement → 聚焦控件
  3. AXUIElementCopyAttributeValue("AXValue") → 控件当前文本（NSString）
  4. 对比上次文本，提取新增片段中的中文字符（CJK 统一汉字范围）
  5. 发射 KeyEvent(is_ime_composition=True, char=新增中文)

权限要求：辅助功能（Accessibility）——与键盘钩子/窗口标题相同。

局限（需真机验证）：
  - AXValue 的可访问性因应用而异（部分应用如 Electron 可能不暴露完整 AXValue）
  - 轮询 diff 对"中间插入/删除"场景不精确；本框架采用前缀匹配简化处理
  - 后续可优化为 AXObserver 事件驱动（kAXValueChangedNotification），减少轮询开销
"""

from __future__ import annotations

import logging
import subprocess
import time
from threading import Event, Thread
from typing import Callable

from src.collector.keyboard_hook import KeyEvent, KeyEventType

logger = logging.getLogger(__name__)

def _monitored_input_source(source_id: str) -> str:
    """返回允许记录的输入法来源；其他输入法一律不采集文字。"""
    normalized = (source_id or "").lower()
    if "doubao" in normalized:
        return "doubao_ime"
    if "sogou" in normalized:
        return "sogou_ime"
    return ""


def _is_doubao_input_source(source_id: str) -> bool:
    """兼容旧调用：判断当前 macOS 输入源是否为豆包输入法。"""
    return _monitored_input_source(source_id) == "doubao_ime"


def is_plausible_ime_commit(text: str) -> bool:
    """判断 CGEvent 回退文本是否像真实的中文输入法确认结果。

    少数输入法会在按键层输出 UTF-8 字节被错误映射后的单字符（如 ``å``）。
    这类内容不能作为语音/候选确认文本写入活动记录；真正的中文确认至少包含
    一个 CJK 字符。完整英文转写仍由 AXValue/AXSelectedText 主通道记录。
    """
    return bool(text) and any("\u3400" <= char <= "\u9fff" for char in text)


def _extract_new_text(last: str, cur: str) -> str:
    """对比 AXValue，提取本次由指定输入法确认写入的文本。

    不再只保留汉字：豆包/搜狗的语音转写常包含数字、英文和标点，它们也属于
    用户确认的输入结果。支持在已有正文中插入或替换选区：保留变化前后的公共
    前缀、后缀，只返回中间新增的确认文字；纯删除不会形成记录。
    """
    if not cur:
        return ""
    prefix = 0
    max_prefix = min(len(last), len(cur))
    while prefix < max_prefix and last[prefix] == cur[prefix]:
        prefix += 1

    # 从尾部找公共部分时，不能穿过已经确定的前缀，否则“整段替换”会相互重叠。
    suffix = 0
    max_suffix = min(len(last) - prefix, len(cur) - prefix)
    while suffix < max_suffix and last[-(suffix + 1)] == cur[-(suffix + 1)]:
        suffix += 1

    end = len(cur) - suffix if suffix else len(cur)
    return cur[prefix:end].strip()


# 保持旧名称可供外部插件调用；新实现同时包含语音转写中的标点、数字和英文。
_extract_new_cjk = _extract_new_text


class ImeWatcher:
    """中文 IME 结果监听器（AXValue 轮询）"""

    def __init__(
        self,
        on_event: Callable[[KeyEvent], None],
        poll_interval: float = 0.25,
        screen_ocr_enabled: bool = True,
        screen_ocr_interval: float = 2.5,
    ):
        """
        Args:
            on_event: IME 文本事件回调（发射 is_ime_composition=True 的 KeyEvent）
            poll_interval: AX 轮询间隔（秒），默认 250ms（平衡响应性与性能）
            screen_ocr_interval: 本地 Vision OCR 最短间隔（秒），切换 App 时立即执行
        """
        self._on_event = on_event
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        # None 表示尚未取得该前台应用的首个可访问文本值；空字符串则是
        # 已建立基线的空输入框。两者不能混用，否则输入框第一次输入会漏记。
        self._last_value: str | None = None
        self._last_value_attribute: str = ""
        self._last_pid: int = 0
        # 仅保存监听健康状态与输入法来源，绝不保存焦点控件的原始文字。
        self._last_source: str = ""
        self._last_ax_state: str = "waiting"
        self._last_target: str = ""
        self._screen_ocr_enabled = screen_ocr_enabled
        self._screen_ocr_interval = max(float(screen_ocr_interval), 0.5)
        self._screen_permission_prompted = False
        self._last_screen_ocr_at = 0.0
        # 仅记录 OCR 可用性和字符数量，帮助排查外部 App；绝不写入截图或文本。
        self._last_screen_ocr_log_key = ""

    def start(self):
        """启动监听线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True, name="ImeWatcher")
        self._thread.start()
        logger.info("ImeWatcher 已启动（AXValue 轮询），间隔 %.2f 秒", self._poll_interval)

    def stop(self):
        """停止监听"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("ImeWatcher 已停止")

    def _poll_loop(self):
        """轮询主循环"""
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.debug("ImeWatcher 轮询异常", exc_info=True)
            self._stop_event.wait(self._poll_interval)

    def _poll_once(self):
        """单次轮询：获取前台聚焦控件 AXValue，diff 提取新增中文"""
        try:
            from AppKit import NSWorkspace
            try:
                from ApplicationServices import (
                    AXIsProcessTrusted,
                    AXUIElementCreateApplication,
                    AXUIElementCreateSystemWide,
                    AXUIElementCopyAttributeValue,
                )
            except ImportError:
                from HIServices import (
                    AXIsProcessTrusted,
                    AXUIElementCreateApplication,
                    AXUIElementCreateSystemWide,
                    AXUIElementCopyAttributeValue,
                )
        except ImportError:
            return  # 非 macOS 环境

        try:
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                self._last_ax_state = "no_front_app"
                return
            pid = app.processIdentifier()
            self._last_target = str(app.localizedName() or "")
            bundle_id = str(app.bundleIdentifier() or "")
            is_worktrace = bundle_id == "cn.worktrace.app"
            # 先读取输入源并在切换 App 时重置基线。屏幕 OCR 不依赖辅助功能，
            # 因此即使 AX 授权暂未被系统识别，也不能让它失去工作机会。
            source = _monitored_input_source(self._current_input_source_id())
            self._last_source = source
            if pid != self._last_pid:
                self._last_pid = pid
                self._last_value = None
                self._last_value_attribute = ""
                # 切换到其他 App 时允许立即建立一次 OCR 基线；同一 App 内则遵守节流。
                self._last_screen_ocr_at = 0.0
                self._last_ax_state = "baseline"
            if not AXIsProcessTrusted():
                if source and self._screen_ocr_enabled and not is_worktrace:
                    screen_value = self._read_screen_input_text(pid)
                    if screen_value is not None:
                        self._last_value_attribute = "screen_ocr"
                        self._consume_value(screen_value, source, "screen_ocr")
                        return
                # OCR 读取失败时保留它自己的精确状态（例如 screen_image_unavailable），
                # 不要用 AX 未授权覆盖掉可操作的屏幕录制诊断。
                if self._last_ax_state not in {
                    "screen_permission_required",
                    "screen_window_unavailable",
                    "screen_image_unavailable",
                    "screen_ocr_error",
                }:
                    self._last_ax_state = "not_trusted"
                return

            # 即使目标 App 不公开 AXValue，也要持续更新当前输入法来源，供
            # CGEventTap 的 Unicode 最终提交作为后备通道使用。
            app_ref = AXUIElementCreateApplication(pid)
            # pywebview、Electron 和部分浏览器不会把网页焦点挂在应用 AX 根节点。
            # 因此同时读取系统级焦点；应用级读取失败时仍可拿到真正焦点控件。
            elements = []
            err, focused = AXUIElementCopyAttributeValue(app_ref, "AXFocusedUIElement", None)
            if err == 0 and focused:
                elements.append(focused)
            try:
                system_ref = AXUIElementCreateSystemWide()
                err, system_focused = AXUIElementCopyAttributeValue(system_ref, "AXFocusedUIElement", None)
                if err == 0 and system_focused:
                    elements.append(system_focused)
                # 部分 App 的真实焦点只会挂在系统级 AXFocusedApplication 上，
                # 而不是 NSWorkspace 返回的应用根节点。继续向其读取聚焦元素与根节点。
                err, system_app = AXUIElementCopyAttributeValue(system_ref, "AXFocusedApplication", None)
                if err == 0 and system_app:
                    err2, app_focused = AXUIElementCopyAttributeValue(system_app, "AXFocusedUIElement", None)
                    if err2 == 0 and app_focused:
                        elements.append(app_focused)
                    elements.append(system_app)
            except Exception:
                logger.debug("读取系统级 AX 焦点失败", exc_info=True)
            elements.append(app_ref)

            # 原生输入框一般暴露 AXValue；个别网页编辑器只暴露 AXSelectedText。
            # AXValue 优先，避免把仍在组合中的拼音候选片段误当成已确认文本。
            value = None
            value_attribute = ""
            # Electron/浏览器编辑器常让焦点元素的 AXValue 恒为空，但把已确认
            # 的文本暴露在 AXSelectedText，或只在应用根元素上暴露。优先非空的
            # AXSelectedText，再尝试 AXValue；均为空时才保留空 AXValue 作基线。
            empty_value = None
            for element in elements:
                for attribute in ("AXValue", "AXSelectedText"):
                    err, candidate = AXUIElementCopyAttributeValue(element, attribute, None)
                    if err != 0 or candidate is None:
                        continue
                    candidate_text = str(candidate)
                    if candidate_text:
                        value = candidate_text
                        value_attribute = attribute
                        break
                    if attribute == "AXValue" and empty_value is None:
                        empty_value = (candidate_text, attribute)
                if value is not None:
                    break
            # 微信会在应用根节点暴露一个恒为空的 AXValue，但真实聊天编辑框并不
            # 公开。空值不能阻断屏幕 OCR 回退；只有读到非空 AX 文本才优先 AX。
            needs_screen_fallback = value is None
            if value is None and empty_value is not None:
                needs_screen_fallback = True

            if needs_screen_fallback and source and self._screen_ocr_enabled and not is_worktrace:
                # 微信等桌面 App 只暴露窗口/菜单而不暴露编辑框。经用户授权后，
                # 仅 OCR 前台窗口底部输入区作为兼容回退；任何截图均不落盘。
                screen_value = self._read_screen_input_text(pid)
                if screen_value is not None:
                    value = screen_value
                    value_attribute = "screen_ocr"
                    self._last_ax_state = "screen_ocr"

            if value is None and empty_value is not None:
                # OCR 未取得文字时，仍保留真实空输入框作为 AX 基线。
                value, value_attribute = empty_value

            if value is None:
                if self._last_ax_state not in {
                    "screen_permission_required",
                    "screen_window_unavailable",
                    "screen_image_unavailable",
                    "screen_ocr_error",
                }:
                    self._last_ax_state = "focused_unavailable" if not focused else "value_unavailable"
                return

            cur = str(value)
            if value_attribute != self._last_value_attribute:
                # 不同 AX 属性的文本不能直接做 diff，切换时重新建立基线。
                self._last_value = None
                self._last_value_attribute = value_attribute

            # 仅在豆包/搜狗输入法启用时读取确认后的文字；切换到其他输入法
            # 只更新基线，避免其文本在切回时被误记为豆包/搜狗输入。
            if value_attribute != "screen_ocr":
                self._last_ax_state = "ready" if source else "other_input_method"
            self._consume_value(cur, source, value_attribute)
        except Exception:
            self._last_ax_state = "error"
            logger.debug("ImeWatcher 单次轮询异常", exc_info=True)

    def status(self) -> dict[str, str]:
        """返回不含文本内容的监听健康状态，供界面现场确认。"""
        return {
            "source": self._last_source,
            "state": self._last_ax_state,
            # 仅返回应用名，帮助定位是哪一个外部 App 没有公开 AX 文本；不返回标题或内容。
            "target": self._last_target,
        }

    def _read_screen_input_text(self, pid: int) -> str | None:
        """识别前台窗口底部输入区；无屏幕录制权限时请求一次系统授权。

        返回 None 表示无法取得图像/权限不足，空字符串表示已 OCR 但输入区为空。
        仅在已锁定豆包/搜狗输入法且 AX 输入框不可读时由调用方触发。
        """
        try:
            import Quartz
            from src.processor.image_text import ImageTextError, recognize_cgimage_text

            # Vision Accurate OCR 成本高；同一输入框无需高频截图。屏幕 OCR
            # 已作为当前基线时，复用上次结果，避免空 AXValue 反复覆盖该基线。
            now = time.monotonic()
            if now - self._last_screen_ocr_at < self._screen_ocr_interval:
                if self._last_value_attribute == "screen_ocr" and self._last_value is not None:
                    return self._last_value
                return None
            self._last_screen_ocr_at = now

            # 不以 CGPreflightScreenCaptureAccess 作为硬性拦截。macOS 在应用
            # 更新、重新签名或刚从设置页返回时可能继续返回旧缓存，即使用户已
            # 为 WorkTrace 开启“屏幕录制与系统录音”。实际创建当前窗口图像才是
            # OCR 是否可用的可靠判定；失败时再结合预检给出权限提示。
            preflight_granted = bool(Quartz.CGPreflightScreenCaptureAccess())

            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID,
            ) or []
            window = next(
                (
                    info for info in windows
                    if int(info.get(Quartz.kCGWindowOwnerPID, -1)) == int(pid)
                    and int(info.get(Quartz.kCGWindowLayer, 0)) == 0
                    and float((info.get(Quartz.kCGWindowBounds, {}) or {}).get("Height", 0)) >= 200
                ),
                None,
            )
            if not window:
                self._set_screen_state("screen_window_unavailable")
                return None
            # 使用目标窗口的实际屏幕边界。CGWindowListCreateImage 配合 CGRectNull
            # 在部分 Electron/微信窗口上会无图返回，而本窗口边界能稳定取得图像。
            bounds = window.get(Quartz.kCGWindowBounds, {}) or {}
            capture_rect = Quartz.CGRectMake(
                float(bounds.get("X", 0)),
                float(bounds.get("Y", 0)),
                float(bounds.get("Width", 0)),
                float(bounds.get("Height", 0)),
            )
            image = Quartz.CGWindowListCreateImage(
                capture_rect,
                Quartz.kCGWindowListOptionIncludingWindow,
                window[Quartz.kCGWindowNumber],
                Quartz.kCGWindowImageDefault,
            )
            if image is None:
                if not preflight_granted:
                    self._set_screen_state("screen_permission_required")
                    if not self._screen_permission_prompted:
                        self._screen_permission_prompted = True
                        Quartz.CGRequestScreenCaptureAccess()
                else:
                    self._set_screen_state("screen_image_unavailable")
                return None
            height = Quartz.CGImageGetHeight(image)
            width = Quartz.CGImageGetWidth(image)
            # 仅取最下方 30%（至少 180px）：聊天消息区不会交给 OCR。
            crop_y = int(height * 0.70)
            crop = Quartz.CGImageCreateWithImageInRect(
                image,
                Quartz.CGRectMake(0, crop_y, width, height - crop_y),
            )
            if crop is None:
                self._set_screen_state("screen_image_unavailable")
                return None
            try:
                text = recognize_cgimage_text(crop)
                self._set_screen_state("screen_ocr", len(text))
                return text
            except ImageTextError:
                self._set_screen_state("screen_ocr", 0)
                return ""
        except Exception:
            self._set_screen_state("screen_ocr_error")
            logger.debug("输入区本地 OCR 回退失败", exc_info=True)
            return None

    def _set_screen_state(self, state: str, chars: int | None = None) -> None:
        """更新 OCR 健康状态，并在状态变化时留下不含内容的诊断日志。"""
        self._last_ax_state = state
        # OCR 字符数会随光标、候选词与界面微小变化而波动；按字符数写日志会造成
        # 不必要的磁盘 I/O。只在目标 App 或健康状态变化时记录一次。
        key = f"{self._last_target}:{state}"
        if key == self._last_screen_ocr_log_key:
            return
        self._last_screen_ocr_log_key = key
        if chars is None:
            logger.info("外部 App 本地屏幕识别状态: app=%s state=%s", self._last_target, state)
        else:
            logger.info("外部 App 本地屏幕识别状态: app=%s state=%s chars=%d", self._last_target, state, chars)

    def _consume_value(self, cur: str, source: str, value_attribute: str = "AXValue") -> None:
        """处理一次已读取的 AXValue；便于覆盖空文本框的真实监听路径。"""
        if cur == self._last_value:
            return
        if not source:
            self._last_value = cur
            return
        if self._last_value is None:
            # 首次可访问的值仅用于建立基线，避免将切入前已有正文误记。
            self._last_value = cur
            return

        # 无论是键入选词还是豆包/搜狗语音转文字，最终都会写入 AXValue，
        # 因而走同一条可审计的本地记录路径。
        new_text = _extract_new_text(self._last_value, cur)
        self._last_value = cur
        if not new_text:
            return
        # AXSelectedText 在部分应用里会短暂暴露拼音组合串（例如 "youjian"），
        # 它不是用户最终确认的内容。只有可确认的中文结果才走该降级通道。
        if value_attribute in {"AXSelectedText", "screen_ocr"} and not is_plausible_ime_commit(new_text):
            return

        logger.info("IME 确认文本检测: chars=%d source=%s", len(new_text), source)
        event = KeyEvent(
            KeyEventType.PRESS,
            key=None,
            char=new_text,
            is_ime_composition=True,
            is_final_ime_result=True,
        )
        event.input_source = source
        # IME 轮询与主线程的窗口轮询是异步的。把检测到文字当刻的前台应用
        # 一起交给引擎，避免用户切走窗口后文本被归到下一应用。
        event.origin_context = {
            "pid": self._last_pid,
            "process_name": self._last_target.lower(),
            "window_title": "",
        }
        self._on_event(event)

    @staticmethod
    def _current_input_source_id() -> str:
        """返回当前输入法标识；优先已选输入源，避免 Carbon 仅返回 ABC 键盘布局。"""
        selected_source = ""
        try:
            result = subprocess.run(
                ["defaults", "read", "com.apple.HIToolbox", "AppleSelectedInputSources"],
                capture_output=True, text=True, timeout=1, check=False,
            )
            selected_source = result.stdout
            if _monitored_input_source(selected_source):
                return selected_source
        except Exception:
            pass
        try:
            from Carbon import TISCopyCurrentKeyboardInputSource, TISGetInputSourceProperty, kTISPropertyInputSourceID

            source = TISCopyCurrentKeyboardInputSource()
            value = TISGetInputSourceProperty(source, kTISPropertyInputSourceID)
            source_id = str(value or "")
            if source_id:
                return source_id
        except Exception:
            pass
        return selected_source
