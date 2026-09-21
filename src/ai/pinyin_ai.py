"""拼音转汉字 LLM 增强转换器

复用 LLMClient 的重试与降级。整段文本批量一次调用（而非逐条），
返回与输入一一对应的转换结果；LLM 不可用或解析失败时返回空列表，
调用方降级到离线引擎结果。
"""

from __future__ import annotations

import asyncio
import json
import logging

from .llm_client import LLMClient
from .todo_extractor import _strip_code_fence, _extract_json_array

logger = logging.getLogger(__name__)

# 单次批量转换的最大条数（防止 prompt 过长）
_MAX_TEXTS = 40
# 单条文本最大长度
_MAX_TEXT_LEN = 500

_SYSTEM_PROMPT = (
    "你是拼音转汉字还原引擎。输入是键盘记录的文本数组，包含中文输入法未上屏时留下的拼音字母。"
    "拼音有两种形态："
    "全拼，如 wojintianhenkaixin（我今天很开心）；"
    "简拼/混拼——用户打字快，很多音节只敲了开头几个字母，"
    "如 jint→今天(jin+tian)、wanc→完成(wan+cheng)、xiangm→项目(xiang+mu)、"
    "hiayou→还有(hai+you)、ceshil→测试(ce+shi+l)。"
    "还原规则："
    "1. 结合中文语感和办公语境（项目、设计、评估、会议等）还原最通顺的句子；"
    "2. 字母+数字组合（如 gr1003）是产品/项目代号，原样保留并规范为大写（GR1003）；"
    "3. 纯数字、英文单词、已有汉字、标点保持原样；"
    "4. 实在无法还原的字母段保留原字母，不要编造；"
    "5. 只输出一个 JSON 字符串数组，与输入一一对应，不要输出任何其他文字。"
    "示例：输入 [\"nihao,jintyaowanca100xiangmdewaiguanjianmopinggu\","
    "\"hiayoua102debeijiapinggu\"]，"
    "输出 [\"你好，今天要完成A100项目的外观建模评估\",\"还有A102的背夹评估\"]。"
)


async def convert_texts_llm(llm_client: LLMClient, texts: list[str]) -> list[str]:
    """批量将文本中的拼音转换为汉字（LLM 增强）

    Args:
        llm_client: 已配置的 LLM 客户端
        texts: 原始文本列表

    Returns:
        转换结果列表（与输入等长）；失败返回空列表
    """
    if not texts:
        return []

    cleaned = [str(t)[:_MAX_TEXT_LEN] for t in texts[:_MAX_TEXTS]]
    user_content = json.dumps(cleaned, ensure_ascii=False)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        content, model_used = await llm_client.complete(messages)
        logger.info("拼音 AI 转换完成，使用模型: %s", model_used)
    except Exception as exc:
        logger.warning("拼音 AI 转换 LLM 调用失败: %s", exc)
        return []

    return _parse_response(content, len(cleaned))


def convert_texts_llm_sync(llm_client: LLMClient, texts: list[str]) -> list[str]:
    """同步包装（工作线程中调用）"""
    return asyncio.run(convert_texts_llm(llm_client, texts))


def _parse_response(content: str, expected_len: int) -> list[str]:
    """容错解析 LLM 输出的 JSON 字符串数组"""
    if not content or not content.strip():
        return []

    text = _strip_code_fence(content.strip())
    array_text = _extract_json_array(text)
    if array_text is None:
        logger.warning("未能从拼音 AI 输出解析 JSON 数组: %s", content[:200])
        return []

    try:
        data = json.loads(array_text)
    except json.JSONDecodeError as exc:
        logger.warning("拼音 AI JSON 解析失败: %s", exc)
        return []

    if not isinstance(data, list) or len(data) != expected_len:
        logger.warning("拼音 AI 输出长度不匹配: 期望 %d 实际 %s",
                       expected_len, len(data) if isinstance(data, list) else type(data))
        return []

    return [str(item) for item in data]
