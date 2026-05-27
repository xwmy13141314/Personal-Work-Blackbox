"""统一 LLM 调用客户端 — 支持 Ollama / DeepSeek / OpenAI / GLM（智谱AI）

特性：
- 多提供商自动降级
- 网络故障指数退避重试
- 网络连通性预检（区分"配置错误"和"临时断网"）
"""

from __future__ import annotations

import asyncio
import logging
import socket
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 默认超时设置
DEFAULT_TIMEOUT = 120.0  # 秒（LLM 生成可能较慢）

# 重试配置
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]  # 秒，指数退避


class LLMProvider(ABC):
    """LLM 提供商抽象基类"""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """调用 LLM 生成回复"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查提供商是否可用（仅检查配置完整性，不做网络请求）"""
        ...

    @abstractmethod
    def test_connectivity(self) -> tuple[bool, str]:
        """测试网络连通性

        Returns:
            (是否连通, 说明信息)
        """
        ...


def _check_tcp_reachable(host: str, port: int = 443, timeout: float = 5.0) -> tuple[bool, str]:
    """TCP 连通性检测（DNS 解析 + TCP 握手）"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} 可达"
    except socket.gaierror as e:
        return False, f"DNS 解析失败: {host} ({e})"
    except (socket.timeout, ConnectionError, OSError) as e:
        return False, f"连接失败: {host}:{port} ({type(e).__name__}: {e})"


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
        return True  # Ollama 始终视为可用（本地服务）

    def test_connectivity(self) -> tuple[bool, str]:
        # Ollama 默认 localhost，用 HTTP 检测
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                if resp.status_code == 200:
                    return True, "Ollama 服务可达"
                return False, f"Ollama 返回异常状态码: {resp.status_code}"
        except httpx.ConnectError:
            return False, "Ollama 未运行（无法连接 localhost:11434）"
        except Exception as e:
            return False, f"Ollama 检测失败: {type(e).__name__}: {e}"


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

    def test_connectivity(self) -> tuple[bool, str]:
        if not self._api_key:
            return False, "DeepSeek: API Key 未配置"
        return _check_tcp_reachable("api.deepseek.com")


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

    def test_connectivity(self) -> tuple[bool, str]:
        if not self._api_key:
            return False, "OpenAI: API Key 未配置"
        return _check_tcp_reachable("api.openai.com")


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

    def test_connectivity(self) -> tuple[bool, str]:
        if not self._api_key:
            return False, "GLM: API Key 未配置"
        return _check_tcp_reachable("open.bigmodel.cn")


# ==================== 统一客户端 ====================

PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "glm": GLMProvider,
    "deepseek": DeepSeekProvider,
    "openai": OpenAIProvider,
}

# 降级顺序：本地优先 → 国内云端 → 海外云端
FALLBACK_ORDER = ["ollama", "glm", "deepseek", "openai"]


def _is_retryable_error(exc: Exception) -> bool:
    """判断异常是否值得重试（网络类错误重试，配置类错误不重试）"""
    if isinstance(exc, ValueError):
        # "API Key 未配置" 等配置错误，不应重试
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        # 4xx 客户端错误一般不重试（除 429 限流）
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    # ConnectionError, TimeoutException, socket error 等 → 重试
    return True


class LLMClient:
    """统一的 LLM 调用客户端

    支持多提供商、自动降级、指数退避重试：
    - 默认使用配置的提供商
    - 单个提供商失败时自动重试（最多 MAX_RETRIES 次）
    - 重试耗尽后降级到下一个提供商
    - 所有提供商失败后抛出异常
    """

    def __init__(self, config: dict):
        self._default_provider = config.get("default_provider", "ollama")
        self._providers: dict[str, LLMProvider] = {}
        self._max_retries = config.get("max_retries", MAX_RETRIES)
        self._retry_delays = config.get("retry_delays", RETRY_DELAYS)

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
        # 指定提供商 → 直接调用，不降级
        if provider:
            if provider not in self._providers:
                raise ValueError(f"未配置的提供商: {provider}")
            result = await self._call_with_retry(provider, messages)
            return result, provider

        # 尝试默认提供商
        default = self._default_provider
        if default in self._providers:
            try:
                result = await self._call_with_retry(default, messages)
                return result, default
            except Exception as exc:
                logger.warning("默认提供商 %s 重试耗尽后仍失败: %s", default, exc)

        # 降级到其他可用提供商
        for name in FALLBACK_ORDER:
            if name == default or name not in self._providers:
                continue
            try:
                result = await self._call_with_retry(name, messages)
                logger.info("降级使用提供商: %s", name)
                return result, name
            except Exception as exc:
                logger.warning("降级提供商 %s 也失败: %s", name, exc)

        raise RuntimeError("所有 LLM 提供商均不可用")

    async def _call_with_retry(self, provider_name: str, messages: list[dict[str, str]]) -> str:
        """带指数退避重试的单提供商调用"""
        provider = self._providers[provider_name]
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                return await provider.complete(messages)
            except Exception as exc:
                last_exc = exc

                if not _is_retryable_error(exc):
                    logger.warning("提供商 %s 配置错误，不重试: %s", provider_name, exc)
                    raise

                if attempt < self._max_retries - 1:
                    delay = self._retry_delays[min(attempt, len(self._retry_delays) - 1)]
                    logger.warning(
                        "提供商 %s 第 %d/%d 次调用失败: %s — %d 秒后重试",
                        provider_name, attempt + 1, self._max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "提供商 %s 第 %d/%d 次调用失败: %s — 重试耗尽",
                        provider_name, attempt + 1, self._max_retries, exc,
                    )

        raise last_exc  # type: ignore[misc]

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

    def diagnose(self) -> list[dict[str, str]]:
        """诊断所有提供商状态

        Returns:
            [{"provider": 名称, "configured": 是否已配置, "connectivity": 连通性说明}]
        """
        results = []
        for name, provider in self._providers.items():
            ok, msg = provider.test_connectivity()
            results.append({
                "provider": name,
                "configured": provider.is_available(),
                "reachable": str(ok),
                "detail": msg,
            })
        return results
