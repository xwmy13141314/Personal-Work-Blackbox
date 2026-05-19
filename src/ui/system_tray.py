"""系统托盘图标"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _create_icon_image(color: str = "green", size: int = 64) -> Image.Image:
    """生成托盘图标"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 4
    if color == "green":
        fill = (46, 204, 113, 255)
    elif color == "yellow":
        fill = (241, 196, 15, 255)
    else:
        fill = (231, 76, 60, 255)

    draw.ellipse([margin, margin, size - margin, size - margin], fill=fill)

    center = size // 2
    text_size = size // 3
    draw.text((center - text_size // 3, center - text_size // 2), "B", fill=(255, 255, 255, 255))

    return img


class SystemTray:
    """系统托盘管理器"""

    def __init__(
        self,
        on_pause_resume: Callable[[], None],
        on_privacy_mode: Callable[[], None],
        on_export: Callable[[], None],
        on_quit: Callable[[], None],
        on_generate_report: Optional[Callable[[], None]] = None,
        on_view_report: Optional[Callable[[], None]] = None,
    ):
        self._on_pause_resume = on_pause_resume
        self._on_privacy_mode = on_privacy_mode
        self._on_export = on_export
        self._on_quit = on_quit
        self._on_generate_report = on_generate_report
        self._on_view_report = on_view_report
        self._tray = None
        self._is_paused = False

    def run(self):
        """运行托盘（阻塞）"""
        import pystray

        icon_image = _create_icon_image("green")

        # 构建菜单项
        menu_items = [
            pystray.MenuItem("Personal Work Blackbox", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("暂停采集 / 恢复采集", self._toggle_pause_resume),
            pystray.MenuItem("隐私模式 (30分钟)", self._activate_privacy_mode),
            pystray.Menu.SEPARATOR,
        ]

        # AI 报告菜单（如果可用）
        if self._on_generate_report:
            menu_items.append(pystray.MenuItem("生成 AI 日报", self._generate_report))
        if self._on_view_report:
            menu_items.append(pystray.MenuItem("查看今日报告", self._view_report))

        menu_items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("导出今日日志", self._export),
            pystray.MenuItem("打开数据目录", self._open_data_dir),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit),
        ])

        self._tray = pystray.Icon(
            name="Blackbox",
            icon=icon_image,
            title="Personal Work Blackbox",
            menu=pystray.Menu(*menu_items),
        )
        self._tray.run()

    def stop(self):
        """停止托盘"""
        if self._tray:
            self._tray.stop()

    def update_icon(self, state: str):
        """更新图标状态"""
        if not self._tray:
            return
        color_map = {"running": "green", "paused": "red", "privacy": "yellow"}
        color = color_map.get(state, "green")
        self._tray.icon = _create_icon_image(color)

    def _toggle_pause_resume(self, icon, item):
        self._is_paused = not self._is_paused
        self._on_pause_resume()
        self.update_icon("paused" if self._is_paused else "running")

    def _activate_privacy_mode(self, icon, item):
        self._on_privacy_mode()
        self.update_icon("privacy")

    def _export(self, icon, item):
        self._on_export()

    def _generate_report(self, icon, item):
        if self._on_generate_report:
            self._on_generate_report()

    def _view_report(self, icon, item):
        if self._on_view_report:
            self._on_view_report()

    def _open_data_dir(self, icon, item):
        import subprocess
        data_dir = Path("./data")
        data_dir.mkdir(exist_ok=True)
        subprocess.Popen(f'explorer "{data_dir.resolve()}"')

    def _quit(self, icon, item):
        self._on_quit()
        self.stop()
