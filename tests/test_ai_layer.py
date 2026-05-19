"""AI 层单元测试 — PromptEngine + LLMClient"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ai.prompt_engine import PromptEngine, BUILTIN_SYSTEM_PROMPT, BUILTIN_USER_TEMPLATE
from src.ai.llm_client import LLMClient, OllamaProvider, DeepSeekProvider, OpenAIProvider, GLMProvider


# ==================== PromptEngine 测试 ====================


class TestPromptEngine:
    """Prompt 模板引擎测试"""

    def test_build_daily_prompt_basic(self):
        """测试基本日报 Prompt 构建"""
        engine = PromptEngine()

        data = {
            "app_usage_stats": [
                {"process_name": "chrome.exe", "active_seconds": 3600, "session_count": 10},
                {"process_name": "code.exe", "active_seconds": 7200, "session_count": 5},
            ],
            "sessions": [
                {
                    "start_time": "2026-05-13T09:00:00",
                    "end_time": "2026-05-13T09:45:00",
                    "process_name": "code.exe",
                    "window_title": "main.py - VS Code",
                    "text_segments": [
                        {"text": "def hello_world():", "source": "keyboard", "is_filtered": False},
                    ],
                    "clipboard_items": [
                        {"text": "https://example.com"},
                    ],
                },
            ],
        }

        messages = engine.build_daily_prompt(data)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == BUILTIN_SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert "chrome.exe" in messages[1]["content"]
        assert "code.exe" in messages[1]["content"]
        assert "def hello_world():" in messages[1]["content"]
        assert "https://example.com" in messages[1]["content"]

    def test_build_daily_prompt_empty_data(self):
        """测试空数据的 Prompt"""
        engine = PromptEngine()
        data = {"app_usage_stats": [], "sessions": []}
        messages = engine.build_daily_prompt(data)

        assert len(messages) == 2
        assert "（无数据）" in messages[1]["content"]
        assert "（无文本输入记录）" in messages[1]["content"]

    def test_build_weekly_prompt(self):
        """测试周报 Prompt 构建"""
        engine = PromptEngine()

        daily_reports = [
            {"date": "2026-05-12", "structured_report": "完成了认证模块"},
            {"date": "2026-05-13", "structured_report": "修复了 Bug"},
        ]

        messages = engine.build_weekly_prompt(daily_reports)

        assert len(messages) == 2
        assert "2026-05-12" in messages[1]["content"]
        assert "2026-05-13" in messages[1]["content"]

    def test_app_stats_formatting(self):
        """测试应用统计格式化"""
        stats = [
            {"process_name": "chrome.exe", "active_seconds": 3600, "session_count": 10},
            {"process_name": "code.exe", "active_seconds": 7200, "session_count": 5},
        ]
        result = PromptEngine._format_app_stats(stats)
        assert "chrome.exe" in result
        assert "code.exe" in result
        assert "1h 00m" in result
        assert "2h 00m" in result

    def test_timeline_formatting(self):
        """测试时间线格式化"""
        sessions = [
            {
                "start_time": "2026-05-13T09:00:00",
                "end_time": "2026-05-13T09:45:00",
                "process_name": "code.exe",
                "window_title": "main.py",
            },
        ]
        result = PromptEngine._format_timeline(sessions)
        assert "09:00-09:45" in result
        assert "code.exe" in result
        assert "main.py" in result


# ==================== LLMClient 测试 ====================


class TestLLMClient:
    """LLM 客户端测试"""

    def test_init_with_providers(self):
        """测试初始化多个提供商"""
        config = {
            "default_provider": "glm",
            "glm": {
                "api_key": "test-glm-key",
                "model": "glm-4-flash",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
            },
            "deepseek": {
                "api_key": "sk-test-key",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "qwen2.5:7b",
            },
        }
        client = LLMClient(config)
        assert client.has_provider is True
        assert "glm" in client._providers
        assert "deepseek" in client._providers
        assert "ollama" in client._providers

    def test_init_empty(self):
        """测试无提供商"""
        client = LLMClient({"default_provider": "ollama"})
        assert client.has_provider is False

    @pytest.mark.asyncio
    async def test_complete_with_specified_provider(self):
        """测试指定提供商调用"""
        config = {
            "default_provider": "deepseek",
            "deepseek": {
                "api_key": "sk-test",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
            },
        }
        client = LLMClient(config)

        # Mock the provider
        mock_provider = AsyncMock()
        mock_provider.complete.return_value = "这是测试回复"
        client._providers["deepseek"] = mock_provider

        result, provider = await client.complete(
            [{"role": "user", "content": "test"}],
            provider="deepseek",
        )
        assert result == "这是测试回复"
        assert provider == "deepseek"

    @pytest.mark.asyncio
    async def test_complete_fallback(self):
        """测试降级机制"""
        config = {
            "default_provider": "ollama",
            "ollama": {"base_url": "http://localhost:11434", "model": "test"},
            "deepseek": {"api_key": "sk-test", "model": "deepseek-chat"},
        }
        client = LLMClient(config)

        # Mock: ollama 失败，deepseek 成功
        mock_ollama = AsyncMock()
        mock_ollama.complete.side_effect = Exception("Ollama 不可用")

        mock_deepseek = AsyncMock()
        mock_deepseek.complete.return_value = "降级成功"

        client._providers["ollama"] = mock_ollama
        client._providers["deepseek"] = mock_deepseek

        result, provider = await client.complete(
            [{"role": "user", "content": "test"}],
        )
        assert result == "降级成功"
        assert provider == "deepseek"

    @pytest.mark.asyncio
    async def test_complete_all_fail(self):
        """测试所有提供商均失败"""
        config = {
            "default_provider": "ollama",
            "ollama": {"base_url": "http://localhost:11434", "model": "test"},
        }
        client = LLMClient(config)

        mock_ollama = AsyncMock()
        mock_ollama.complete.side_effect = Exception("不可用")
        client._providers["ollama"] = mock_ollama

        with pytest.raises(RuntimeError, match="所有 LLM 提供商均不可用"):
            await client.complete([{"role": "user", "content": "test"}])


class TestProviderAvailability:
    """提供商可用性测试"""

    def test_glm_available_with_key(self):
        provider = GLMProvider({"api_key": "test-key"})
        assert provider.is_available() is True

    def test_glm_not_available_without_key(self):
        provider = GLMProvider({"api_key": ""})
        assert provider.is_available() is False

    def test_glm_default_config(self):
        provider = GLMProvider({})
        assert provider._model == "glm-4-flash"
        assert provider._base_url == "https://open.bigmodel.cn/api/paas/v4"

    def test_deepseek_available_with_key(self):
        provider = DeepSeekProvider({"api_key": "sk-test"})
        assert provider.is_available() is True

    def test_deepseek_not_available_without_key(self):
        provider = DeepSeekProvider({"api_key": ""})
        assert provider.is_available() is False

    def test_openai_available_with_key(self):
        provider = OpenAIProvider({"api_key": "sk-test"})
        assert provider.is_available() is True

    def test_openai_not_available_without_key(self):
        provider = OpenAIProvider({"api_key": ""})
        assert provider.is_available() is False

    @pytest.mark.asyncio
    async def test_glm_fallback_from_ollama(self):
        """测试 Ollama 失败后降级到 GLM"""
        config = {
            "default_provider": "ollama",
            "ollama": {"base_url": "http://localhost:11434", "model": "test"},
            "glm": {"api_key": "test-key", "model": "glm-4-flash"},
        }
        client = LLMClient(config)

        mock_ollama = AsyncMock()
        mock_ollama.complete.side_effect = Exception("Ollama 不可用")

        mock_glm = AsyncMock()
        mock_glm.complete.return_value = "GLM 回复"

        client._providers["ollama"] = mock_ollama
        client._providers["glm"] = mock_glm

        result, provider = await client.complete(
            [{"role": "user", "content": "test"}],
        )
        assert result == "GLM 回复"
        assert provider == "glm"
