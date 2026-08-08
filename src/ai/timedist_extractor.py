"""时间分布提取器 — 从报告文本中用 LLM 提取各类工作的时间占比

独立的轻量 LLM 调用，不改报告主链路。复用 LLMClient 的重试与降级，
并直接复用 todo_extractor 的容错 JSON 解析（_strip_code_fence / _extract_json_array）。
LLM 全是纯文本输出（OpenAI 兼容），返回 JSON 数组靠 prompt 约束 + 后端容错解析。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from .llm_client import LLMClient
from .prompt_engine import PromptEngine
from .todo_extractor import _extract_json_array, _strip_code_fence

if TYPE_CHECKING:
    from src.storage.database import Database

logger = logging.getLogger(__name__)

# 单次提取最多接受的类别数（防止 LLM 失控刷屏）
_MAX_CATEGORIES = 10
# 类别名称最大长度
_MAX_CATEGORY_LEN = 12


class TimeDistExtractor:
    """时间分布提取器（仿 TodoExtractor）

    职责：
    1. 用 PromptEngine 构建提取提示词
    2. 调用 LLMClient 获取 JSON 文本
    3. 容错解析为 [{"category","minutes","percent"}, ...]
    """

    def __init__(self, db: Database, llm_client: LLMClient, prompt_engine: PromptEngine):
        self._db = db
        self._llm = llm_client
        self._prompt = prompt_engine

    async def extract(self, report_text: str) -> list[dict]:
        """从报告文本提取时间分布（异步）

        Returns:
            [{"category","minutes","percent"}, ...]，提取失败或无数据返回空列表
        """
        if not report_text or not report_text.strip():
            logger.info("报告内容为空，跳过时间分布提取")
            return []

        messages = self._prompt.build_timedist_extract_prompt(report_text)
        try:
            content, model_used = await self._llm.complete(messages)
            logger.info("时间分布提取完成，使用模型: %s", model_used)
        except Exception as exc:
            logger.exception("时间分布提取 LLM 调用失败（已耗尽重试和降级）: %s", exc)
            return []

        result = self.parse_timedist_json(content)
        logger.info("从报告解析出 %d 个时间分布类别", len(result))
        return result

    def extract_sync(self, report_text: str) -> list[dict]:
        """同步包装（便于在非异步上下文中调用）"""
        return asyncio.run(self.extract(report_text))

    @staticmethod
    def parse_timedist_json(content: str) -> list[dict]:
        """容错解析 LLM 输出的时间分布 JSON 数组

        处理：
        - 剥离 ```json ... ``` / ``` ... ``` 代码块包裹
        - 提取首个 JSON 数组片段（LLM 可能输出多余文字）
        - 字段校验与清洗（category 必填、minutes/percent 非负）
        - 百分比归一化（总和严重偏离 100 时按比例缩放）
        """
        if not content or not content.strip():
            return []

        text = _strip_code_fence(content.strip())
        array_text = _extract_json_array(text)
        if array_text is None:
            logger.warning("未能从 LLM 输出中解析出 JSON 数组: %s", content[:200])
            return []

        try:
            data = json.loads(array_text)
        except json.JSONDecodeError as exc:
            logger.warning("时间分布 JSON 解析失败: %s；原始片段: %s", exc, array_text[:200])
            return []

        if not isinstance(data, list):
            return []

        cleaned = []
        for item in data:
            entry = _clean_timedist_item(item)
            if entry:
                cleaned.append(entry)
            if len(cleaned) >= _MAX_CATEGORIES:
                break

        return _normalize_percent(cleaned)


def _clean_timedist_item(item) -> dict | None:
    """清洗单条时间分布：category 必填，minutes/percent 归一化为非负数"""
    if not isinstance(item, dict):
        return None
    category = str(item.get("category", "")).strip()
    if not category:
        return None
    category = category[:_MAX_CATEGORY_LEN]

    try:
        minutes = int(round(float(item.get("minutes", 0))))
    except (TypeError, ValueError):
        minutes = 0
    if minutes < 0:
        minutes = 0

    try:
        percent = float(item.get("percent", 0))
    except (TypeError, ValueError):
        percent = 0.0
    if percent < 0:
        percent = 0.0

    return {"category": category, "minutes": minutes, "percent": round(percent, 1)}


def _normalize_percent(items: list[dict]) -> list[dict]:
    """若各 percent 之和严重偏离 100，按比例缩放归一到 100

    - 总和在 90~110：合理，不调整
    - 总和全 0：退而用 minutes 比例分配
    - 其他：按 percent 比例缩放到 100
    """
    if not items:
        return items
    total = sum(it["percent"] for it in items)
    if 90 <= total <= 110:
        return items
    if total <= 0:
        total_min = sum(it["minutes"] for it in items)
        if total_min <= 0:
            return items
        for it in items:
            it["percent"] = round(it["minutes"] / total_min * 100, 1)
        return items
    for it in items:
        it["percent"] = round(it["percent"] / total * 100, 1)
    return items
