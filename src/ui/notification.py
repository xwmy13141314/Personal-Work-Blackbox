"""系统通知（Windows Toast / macOS osascript）"""

from __future__ import annotations

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def _osa_quote(s: str) -> str:
    """转义 osascript 字符串字面量"""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def send_toast(title: str, message: str):
    """发送系统通知：macOS 用 osascript，Windows 用 PowerShell Toast"""
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f"display notification {_osa_quote(message)} with title {_osa_quote(title)}"],
                capture_output=True,
                timeout=5,
            )
            return
        # Windows: PowerShell 原生 Toast
        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
        $template = @"
        <toast>
            <visual>
                <binding template="ToastText02">
                    <text id="1">{title}</text>
                    <text id="2">{message}</text>
                </binding>
            </visual>
        </toast>
"@
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Personal Work Blackbox").Show($toast)
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        # 降级: 写入日志
        logger.info("[通知] %s: %s", title, message)
