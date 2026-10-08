"""剪贴板监控器 — macOS 原生实现（AppKit NSPasteboard）

通过轮询 NSPasteboard.generalPasteboard().changeCount 检测剪贴板变化。
与 Windows 版 ClipboardRecord / ClipboardMonitor 接口一致。

权限要求：无（读取剪贴板不需要特殊权限）。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Callable

logger = logging.getLogger(__name__)

# ==================== macOS AppKit 绑定 ====================
try:
    from AppKit import NSPasteboard, NSStringPboardType
    _HAS_MAC_API = True
except Exception:
    _HAS_MAC_API = False
    logger.warning("AppKit 不可用，将回退到 pbpaste 轮询")


@dataclass
class ClipboardRecord:
    """剪贴板记录（与 Windows 版字段一致）"""
    content: str
    timestamp: float = field(default_factory=time.time)
    source_process: str = ""
    source_window: str = ""


class ClipboardMonitor:
    """剪贴板变化监控器（macOS NSPasteboard 轮询）

    通过对比 NSPasteboard.changeCount 判断剪贴板是否变化，
    变化时读取字符串内容。比 Windows 版更高效（无需逐字节对比）。
    """

    def __init__(
        self,
        on_change: Callable[[ClipboardRecord], None],
        max_length: int = 10240,
        poll_interval: float = 0.5,
    ):
        """
        Args:
            on_change: 剪贴板内容变化回调
            max_length: 单条记录最大长度
            poll_interval: 轮询间隔（秒）
        """
        self._on_change = on_change
        self._max_length = max_length
        self._poll_interval = poll_interval
        self._stop_event = Event()
        self._thread: Thread | None = None

        self._last_content: str = ""
        self._last_change_count: int = -1

    def start(self):
        """启动监控"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        # 初始化基线：记录当前 changeCount 与内容
        self._last_change_count = self._get_change_count()
        self._last_content = self._read_clipboard() or ""
        self._thread = Thread(target=self._poll_loop, daemon=True, name="ClipboardMonitor")
        self._thread.start()
        logger.info("ClipboardMonitor 已启动（NSPasteboard 轮询），间隔 %.1f 秒", self._poll_interval)

    def stop(self):
        """停止监控"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("ClipboardMonitor 已停止")

    def _poll_loop(self):
        """轮询主循环"""
        while not self._stop_event.is_set():
            try:
                current_count = self._get_change_count()
                # changeCount 变化 = 剪贴板被写入
                if current_count != self._last_change_count:
                    self._last_change_count = current_count
                    content = self._read_clipboard()
                    if content and content != self._last_content:
                        self._last_content = content
                        truncated = content[:self._max_length]
                        record = ClipboardRecord(
                            content=truncated,
                            timestamp=time.time(),
                        )
                        self._on_change(record)
            except Exception:
                logger.exception("剪贴板轮询异常")
            self._stop_event.wait(self._poll_interval)

    @staticmethod
    def _get_change_count() -> int:
        """获取剪贴板 changeCount（每次写入自增）"""
        if not _HAS_MAC_API:
            return -1
        try:
            pb = NSPasteboard.generalPasteboard()
            return pb.changeCount()
        except Exception:
            return -1

    @staticmethod
    def _read_clipboard() -> str:
        """读取剪贴板内容；图片优先转为本地 OCR 文字，原图不保存。"""
        if _HAS_MAC_API:
            try:
                pb = NSPasteboard.generalPasteboard()
                image_text = ClipboardMonitor._read_clipboard_image_text(pb)
                if image_text:
                    return f"【剪贴板图片识别】\n{image_text}"
                content = pb.stringForType_(NSStringPboardType)
                return content or ""
            except Exception:
                return ""
        # 回退：pbpaste
        import subprocess
        try:
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2,
            )
            return result.stdout
        except Exception:
            return ""

    @staticmethod
    def _read_clipboard_image_text(pasteboard) -> str:
        """将 PNG/TIFF 剪贴板图片临时交给 Vision OCR；识别完立即删除临时文件。"""
        path = ""
        try:
            from AppKit import NSPasteboardTypePNG, NSPasteboardTypeTIFF
            from tempfile import NamedTemporaryFile
            from src.processor.image_text import ImageTextError, recognize_image_text

            data = pasteboard.dataForType_(NSPasteboardTypePNG)
            suffix = ".png"
            if not data:
                data = pasteboard.dataForType_(NSPasteboardTypeTIFF)
                suffix = ".tiff"
            if not data:
                return ""
            with NamedTemporaryFile(suffix=suffix, delete=False) as file:
                file.write(bytes(data))
                path = file.name
            return recognize_image_text(path)
        except ImageTextError:
            return ""
        except Exception:
            logger.debug("剪贴板图片文字识别失败", exc_info=True)
            return ""
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
