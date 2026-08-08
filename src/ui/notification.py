"""Windows Toast 通知"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

# 阻止子进程弹出控制台窗口：windowed exe（console=False）下调用 PowerShell 等
# 控制台程序若不加此标志，每次都会闪一个黑窗。非 Windows 平台无此常量则取 0。
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def send_toast(title: str, message: str):
    """发送 Windows Toast 通知

    使用 PowerShell 的 BurntToast 模块或原生方式发送。
    """
    try:
        # 方案1: 使用 PowerShell 原生 Toast
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
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        # 降级: 写入日志
        logger.info("[通知] %s: %s", title, message)
