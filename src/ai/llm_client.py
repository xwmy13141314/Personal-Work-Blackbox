"""统一 LLM 调用客户端 — 支持 Ollama / DeepSeek / OpenAI / GLM（智谱AI）"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 默认超时设置
DEFAULT_TIMEOUT = 120.0  # 秒（LLM 生成可能较慢）


class LLMProvider(ABC):
    """LLM 提供商抽象基类"""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """调用 LLM 生成回复"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查提供商是否可用"""
        ...


class OllamaProvider(LLMProvider):
    """Ollama 本地模型提供商"""

    def __init__(self, config: dict):
        self._base_url = config.get("base_url", "http://localhost:11434").rstrip("/")
        self._model = config.get("model", "qwen2.5:7b")
        self._temperature = config.get("temperature", 0.3)

    async def complete(self, messages: list[dict[str, str]]) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self._temperature,
            },
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


class DeepSeekProvider(LLMProvider):
    """DeepSeek API 提供商（OpenAI 兼容接口）"""

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "deepseek-chat")
        self._base_url = config.get("base_url", "https://api.deepseek.com/v1").rstrip("/")

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self._api_key:
            raise ValueError("DeepSeek API Key 未配置")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def is_available(self) -> bool:
        return bool(self._api_key)


class OpenAIProvider(LLMProvider):
    """OpenAI API 提供商"""

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "gpt-4o-mini")
        self._base_url = config.get("base_url", "https://api.openai.com/v1").rstrip("/")

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self._api_key:
            raise ValueError("OpenAI API Key 未配置")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def is_available(self) -> bool:
        return bool(self._api_key)


class GLMProvider(LLMProvider):
    """智谱 AI (GLM) 提供商

    智谱 API 兼容 OpenAI 接口格式。
    Base URL: https://open.bigmodel.cn/api/paas/v4
    """

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "glm-4-flash")
        self._base_url = config.get(
            "base_url", "https://open.bigmodel.cn/api/paas/v4"
        ).rstrip("/")

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self._api_key:
            raise ValueError("GLM API Key 未配置")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def is_available(self) -> bool:
        return bool(self._api_key)


# ==================== 统一客户端 ====================

PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "glm": GLMProvider,
    "deepseek": DeepSeekProvider,
    "openai": OpenAIProvider,
}

# 降级顺序：本地优先 → 国内云端 → 海外云端
FALLBACK_ORDER = ["ollama", "glm", "deepseek", "openai"]


class LLMClient:
    """统一的 LLM 调用客户端

    支持多提供商和自动降级：
    - 默认使用配置的提供商
    - 如果默认不可用，按优先级降级
    """

    def __init__(self, config: dict):
        self._default_provider = config.get("default_provider", "ollama")
        self._providers: dict[str, LLMProvider] = {}

        # 初始化所有已配置的提供商
        for name, provider_cls in PROVIDER_REGISTRY.items():
            if name in config and isinstance(config[name], dict):
                self._providers[name] = provider_cls(config[name])

    async def complete(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
    ) -> tuple[str, str]:
        """调用 LLM 生成回复

        Args:
            messages: 消息列表
            provider: 指定提供商（None 则使用默认 + 降级）

        Returns:
            (生成的文本, 使用的提供商名称)
        """
        # 指定提供商
        if provider:
            if provider not in self._providers:
                raise ValueError(f"未配置的提供商: {provider}")
            result = await self._providers[provider].complete(messages)
            return result, provider

        # 尝试默认提供商
        default = self._default_provider
        if default in self._providers:
            try:
                result = await self._providers[default].complete(messages)
                return result, default
            except Exception:
                logger.warning("默认提供商 %s 调用失败，尝试降级", default)

        # 降级到其他可用提供商
        for name in FALLBACK_ORDER:
            if name == default or name not in self._providers:
                continue
            try:
                result = await self._providers[name].complete(messages)
                logger.info("降级使用提供商: %s", name)
                return result, name
            except Exception:
                logger.warning("提供商 %s 调用失败", name)

        raise RuntimeError("所有 LLM 提供商均不可用")

    def get_available_providers(self) -> list[str]:
        """获取可用的提供商列表"""
        available = []
        for name, provider in self._providers.items():
            if provider.is_available():
                available.append(name)
        return available

    @property
    def has_provider(self) -> bool:
        """是否有至少一个提供商"""
        return len(self._providers) > 0
