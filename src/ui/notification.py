"""macOS 通知（osascript display notification）

使用 AppleScript 的 display notification 发送系统通知，无需额外授权，
兼容所有 macOS 版本。比 NSUserNotificationCenter/UNUserNotificationCenter
更简单可靠（后者需请求通知授权）。
"""

from __future__ import annotations

import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


def send_toast(title: str, message: str):
    """发送 macOS 系统通知

    通过 osascript 调用 display notification。失败时降级写日志。
    """
    try:
        # 转义 AppleScript 字符串中的特殊字符（防止注入与语法错误）
        safe_title = _applescript_escape(title)
        safe_message = _applescript_escape(message)
        script = f'display notification "{safe_message}" with title "{safe_title}"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        # 降级：写入日志
        logger.info("[通知] %s: %s", title, message)


def _applescript_escape(text: str) -> str:
    """转义 AppleScript 字符串中的特殊字符"""
    # 反斜杠和双引号需转义
    return text.replace("\\", "\\\\").replace('"', '\\"')
