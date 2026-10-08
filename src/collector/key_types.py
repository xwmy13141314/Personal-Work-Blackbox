"""应用内部使用的键盘键类型。

采集已经由 Quartz 实现；这里仅提供事件解释和输入缓冲所需的键值，
避免为了几个常量在桌面 App 启动时加载 pynput 的 AppKit 后端。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Key(Enum):
    enter = "enter"
    backspace = "backspace"
    delete = "delete"
    tab = "tab"
    esc = "esc"
    space = "space"
    left = "left"
    right = "right"
    up = "up"
    down = "down"
    home = "home"
    end = "end"
    ctrl = "ctrl"
    ctrl_l = "ctrl_l"
    ctrl_r = "ctrl_r"
    alt = "alt"
    alt_l = "alt_l"
    alt_r = "alt_r"


@dataclass(frozen=True)
class KeyCode:
    """普通字符键，保留与原先 pynput.KeyCode 相同的 ``char`` 属性。"""

    char: str | None = None
