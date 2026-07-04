"""配置加载与管理"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .defaults import DEFAULTS


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base"""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class Settings:
    """全局配置管理器（单例模式）"""

    _instance: Settings | None = None

    def __init__(self, config_path: str | Path | None = None):
        self._config_path = Path(config_path) if config_path else None
        # 推导应用根目录：配置文件所在目录的上级（config/config.yaml → app_root/）
        if self._config_path:
            self._app_root = self._config_path.parent.parent.resolve()
        else:
            self._app_root = Path.cwd()
        self._data: dict[str, Any] = deepcopy(DEFAULTS)
        self._load()

    @classmethod
    def get_instance(cls, config_path: str | Path | None = None) -> Settings:
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    def _load(self):
        """加载配置文件，与默认配置合并"""
        if self._config_path and self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            self._data = _deep_merge(DEFAULTS, user_config)

    def reload(self):
        """重新加载配置文件"""
        self._load()

    # ==================== 便捷访问方法 ====================

    @property
    def collection(self) -> dict:
        return self._data["collection"]

    @property
    def privacy(self) -> dict:
        return self._data["privacy"]

    @property
    def storage(self) -> dict:
        return self._data["storage"]

    @property
    def ai(self) -> dict:
        return self._data["ai"]

    @property
    def performance(self) -> dict:
        return self._data["performance"]

    @property
    def notification(self) -> dict:
        return self._data["notification"]

    def get(self, dot_path: str, default: Any = None) -> Any:
        """通过点号路径获取配置值，如 'collection.window_poll_interval'"""
        keys = dot_path.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def _resolve_path(self, raw_path: str) -> Path:
        """将配置中的路径解析为绝对路径（相对路径基于应用根目录）"""
        p = Path(raw_path)
        if p.is_absolute():
            return p
        return (self._app_root / p).resolve()

    @property
    def db_path(self) -> Path:
        return self._resolve_path(self.storage["db_path"])

    @property
    def markdown_dir(self) -> Path:
        return self._resolve_path(self.storage["markdown_export_dir"])

    def ensure_dirs(self):
        """确保所有必要目录存在"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
