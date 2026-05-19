"""Settings 配置层单元测试"""

import pytest
from pathlib import Path

import yaml

from src.config.settings import Settings, _deep_merge
from src.config.defaults import DEFAULTS


# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试前后重置单例"""
    Settings.reset()
    yield
    Settings.reset()


@pytest.fixture
def config_file(tmp_path):
    """创建临时配置文件"""
    config = {
        "collection": {
            "keyboard_enabled": False,
            "idle_threshold": 600,
        },
        "ai": {
            "default_provider": "ollama",
        },
    }
    path = tmp_path / "config.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)
    return path


# ==================== _deep_merge 辅助函数 ====================

class TestDeepMerge:
    """深度合并测试"""

    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_override(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 3}}

    def test_deep_nested(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"d": 3, "e": 4}}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 3, "e": 4}}}

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1}}  # 未被修改

    def test_empty_override(self):
        base = {"a": 1}
        result = _deep_merge(base, {})
        assert result == {"a": 1}


# ==================== Settings 类 ====================

class TestSettings:
    """Settings 配置管理器测试"""

    def test_default_values(self):
        """无配置文件时应使用全部默认值"""
        settings = Settings()
        assert settings.collection["window_poll_interval"] == 1
        assert settings.collection["keyboard_enabled"] is True
        assert settings.privacy["privacy_mode_duration"] == 30

    def test_load_from_file(self, config_file):
        """从 YAML 文件加载配置并合并"""
        settings = Settings(config_file)
        # 被覆盖的值
        assert settings.collection["keyboard_enabled"] is False
        assert settings.collection["idle_threshold"] == 600
        assert settings.ai["default_provider"] == "ollama"
        # 未覆盖的值应保留默认
        assert settings.collection["window_poll_interval"] == 1
        assert settings.collection["capture_hotkeys"] is True

    def test_nonexistent_config_uses_defaults(self, tmp_path):
        """不存在的配置文件应使用默认值"""
        settings = Settings(tmp_path / "nonexistent.yaml")
        assert settings.collection["keyboard_enabled"] is True

    def test_singleton_pattern(self, config_file):
        """get_instance 应返回同一实例"""
        s1 = Settings.get_instance(config_file)
        s2 = Settings.get_instance()
        assert s1 is s2

    def test_singleton_reset(self, config_file):
        """reset 后应创建新实例"""
        s1 = Settings.get_instance(config_file)
        Settings.reset()
        s2 = Settings.get_instance(config_file)
        assert s1 is not s2

    def test_db_path_property(self):
        """db_path 属性应返回 Path 对象"""
        settings = Settings()
        assert isinstance(settings.db_path, Path)
        assert settings.db_path.name == "blackbox.db"

    def test_markdown_dir_property(self):
        """markdown_dir 属性应返回 Path 对象"""
        settings = Settings()
        assert isinstance(settings.markdown_dir, Path)

    def test_get_dot_path(self, config_file):
        """点号路径访问配置值"""
        settings = Settings(config_file)
        assert settings.get("collection.keyboard_enabled") is False
        assert settings.get("collection.idle_threshold") == 600

    def test_get_dot_path_default(self):
        """点号路径访问不存在的键应返回默认值"""
        settings = Settings()
        assert settings.get("nonexistent.key", "fallback") == "fallback"

    def test_get_dot_path_nested(self):
        """深层嵌套的点号路径"""
        settings = Settings()
        result = settings.get("ai.glm.model")
        assert result == "glm-4-flash"

    def test_ensure_dirs(self, tmp_path):
        """ensure_dirs 应创建必要目录"""
        config = {"storage": {"db_path": str(tmp_path / "data" / "test.db"), "markdown_export_dir": str(tmp_path / "logs")}}
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        settings = Settings(config_path)
        settings.ensure_dirs()
        assert (tmp_path / "data").exists()
        assert (tmp_path / "logs").exists()

    def test_reload(self, tmp_path):
        """reload 应重新加载配置文件"""
        config_path = tmp_path / "config.yaml"
        # 初始配置
        config = {"collection": {"keyboard_enabled": True}}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        settings = Settings(config_path)
        assert settings.collection["keyboard_enabled"] is True

        # 修改配置
        config["collection"]["keyboard_enabled"] = False
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        settings.reload()
        assert settings.collection["keyboard_enabled"] is False

    def test_all_sections_accessible(self):
        """所有配置分区都应可访问"""
        settings = Settings()
        assert isinstance(settings.collection, dict)
        assert isinstance(settings.privacy, dict)
        assert isinstance(settings.storage, dict)
        assert isinstance(settings.ai, dict)
        assert isinstance(settings.performance, dict)
        assert isinstance(settings.notification, dict)
