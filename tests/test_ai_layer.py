"""AI 层单元测试 — PromptEngine + LLMClient"""

import pytest
import httpx
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

        data = {
            "daily_reports": [
                {"date": "2026-05-12", "structured_report": "完成了认证模块"},
                {"date": "2026-05-13", "structured_report": "修复了 Bug"},
            ],
            "app_usage_stats": [
                {"process_name": "code.exe", "active_seconds": 7200, "session_count": 5},
            ],
            "period_start": "2026-05-11",
            "period_end": "2026-05-17",
            "total_days": 7,
            "report_days": 2,
            "missing_dates": ["2026-05-11", "2026-05-14", "2026-05-15", "2026-05-16", "2026-05-17"],
        }

        messages = engine.build_weekly_prompt(data)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "周报" in messages[0]["content"]
        assert "2026-05-12" in messages[1]["content"]
        assert "2026-05-13" in messages[1]["content"]
        assert "2026-05-11 ~ 2026-05-17" in messages[1]["content"]
        assert "code.exe" in messages[1]["content"]

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
            "max_retries": 1,  # 测试时不重试，避免等待
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
            "max_retries": 1,  # 测试时不重试，避免等待
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
            "max_retries": 1,  # 测试时不重试，避免等待
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


# ==================== 重试机制测试 ====================


class TestRetryMechanism:
    """LLM 重试和诊断功能测试"""

    @pytest.mark.asyncio
    async def test_retry_configurable(self):
        """测试重试次数可配置"""
        config = {
            "default_provider": "glm",
            "max_retries": 1,
            "retry_delays": [0],
            "glm": {"api_key": "test-key", "model": "glm-4-flash"},
        }
        client = LLMClient(config)
        assert client._max_retries == 1
        assert client._retry_delays == [0]

    @pytest.mark.asyncio
    async def test_config_error_not_retried(self):
        """测试配置错误（ValueError）不触发重试，直接抛出"""
        config = {
            "default_provider": "glm",
            "max_retries": 3,
            "retry_delays": [0, 0, 0],
            "glm": {"api_key": "", "model": "glm-4-flash"},  # 空 key
        }
        client = LLMClient(config)

        # 完整流程：ValueError 被捕获 → 无其他提供商 → RuntimeError
        with pytest.raises(RuntimeError, match="所有 LLM 提供商均不可用"):
            await client.complete([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_config_error_no_retry_in_direct_call(self):
        """测试 _call_with_retry 对 ValueError 不重试，立即抛出"""
        config = {
            "default_provider": "glm",
            "max_retries": 3,
            "retry_delays": [0, 0, 0],
            "glm": {"api_key": "", "model": "glm-4-flash"},
        }
        client = LLMClient(config)

        with pytest.raises(ValueError, match="GLM API Key 未配置"):
            await client._call_with_retry("glm", [{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_network_error_retried(self):
        """测试网络错误触发重试"""
        call_count = 0

        class FakeProvider:
            def is_available(self):
                return True
            def test_connectivity(self):
                return False, "fake"
            async def complete(self, messages):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("网络不可达")
                return "重试成功"

        config = {
            "default_provider": "fake",
            "max_retries": 3,
            "retry_delays": [0, 0, 0],
        }
        client = LLMClient(config)
        client._providers["fake"] = FakeProvider()

        result, provider = await client.complete([{"role": "user", "content": "test"}])
        assert result == "重试成功"
        assert call_count == 3  # 第1次失败、第2次失败、第3次成功

    def test_diagnose(self):
        """测试诊断功能"""
        config = {
            "default_provider": "glm",
            "glm": {"api_key": "test-key", "model": "glm-4-flash"},
        }
        client = LLMClient(config)
        results = client.diagnose()

        assert len(results) == 1
        assert results[0]["provider"] == "glm"
        assert results[0]["configured"] is True
        # reachable 可能为 True 或 False（取决于网络环境），只检查字段存在
        assert "reachable" in results[0]
        assert "detail" in results[0]

    def test_is_retryable_error(self):
        """测试错误分类逻辑"""
        from src.ai.llm_client import _is_retryable_error

        # 配置错误 → 不重试
        assert _is_retryable_error(ValueError("API Key 未配置")) is False

        # 网络错误 → 重试
        assert _is_retryable_error(ConnectionError("连接失败")) is True
        assert _is_retryable_error(TimeoutError("超时")) is True
        assert _is_retryable_error(OSError("网络不可达")) is True

        # HTTP 429 限流 → 重试
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        assert _is_retryable_error(httpx.HTTPStatusError("429", request=MagicMock(), response=mock_resp)) is True

        # HTTP 400 客户端错误 → 不重试
        mock_resp.status_code = 400
        assert _is_retryable_error(httpx.HTTPStatusError("400", request=MagicMock(), response=mock_resp)) is False
