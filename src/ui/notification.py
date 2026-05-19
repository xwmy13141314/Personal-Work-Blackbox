"""Windows Toast 通知"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)


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
        )
    except Exception:
        # 降级: 写入日志
        logger.info("[通知] %s: %s", title, message)
