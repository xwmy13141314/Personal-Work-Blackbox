"""待办事项提取器 — 从报告文本中用 LLM 提取结构化待办

独立的轻量 LLM 调用，不改报告主链路。复用 LLMClient 的重试与降级。
LLM 全是纯文本输出（OpenAI 兼容），返回 JSON 数组靠 prompt 约束 + 后端容错解析。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING

from .llm_client import LLMClient
from .prompt_engine import PromptEngine

if TYPE_CHECKING:
    from src.storage.database import Database

logger = logging.getLogger(__name__)

# 允许的优先级取值
_VALID_PRIORITIES = {"urgent", "high", "normal", "low"}
# 单次提取最多接受的待办数（防止 LLM 失控刷屏）
_MAX_TODOS = 50
# 单个 title 最大长度
_MAX_TITLE_LEN = 200

# 推进建议（P2 §4.6）
_VALID_ADVICE_TYPES = {"start", "progress", "stall"}
_MAX_ADVICES = 30


class TodoExtractor:
    """待办提取器

    职责：
    1. 用 PromptEngine 构建提取提示词
    2. 调用 LLMClient 获取 JSON 文本
    3. 容错解析为待办字典列表
    """

    def __init__(self, db: Database, llm_client: LLMClient, prompt_engine: PromptEngine):
        self._db = db
        self._llm = llm_client
        self._prompt = prompt_engine

    async def extract(self, report_text: str) -> list[dict]:
        """从报告文本提取待办（异步）

        Returns:
            待办字典列表 [{"title","priority","due_date","note"}, ...]，
            提取失败或无待办返回空列表
        """
        if not report_text or not report_text.strip():
            logger.info("报告内容为空，跳过待办提取")
            return []

        messages = self._prompt.build_todo_extract_prompt(report_text)
        try:
            content, model_used = await self._llm.complete(messages)
            logger.info("待办提取完成，使用模型: %s", model_used)
        except Exception as exc:
            logger.exception("待办提取 LLM 调用失败（已耗尽重试和降级）: %s", exc)
            return []

        todos = self.parse_todos_json(content)
        logger.info("从报告解析出 %d 条待办", len(todos))
        return todos

    def extract_sync(self, report_text: str) -> list[dict]:
        """同步包装（便于在非异步上下文中调用）"""
        return asyncio.run(self.extract(report_text))

    async def recognize_one(self, raw_text: str) -> dict | None:
        """将用户输入的自然语言整理为一条可编辑的待办标题和内容。"""
        value = (raw_text or "").strip()
        if not value:
            return None
        messages = [
            {"role": "system", "content": """你是待办整理助手。将用户输入整理成一条待办。
只输出 JSON 对象，不要解释：
{"title":"不超过30字的可执行标题","note":"保留上下文、要求、时间和细节的完整内容","steps":["可执行事项1","可执行事项2"],"priority":"urgent|high|normal|low","due_date":"YYYY-MM-DD或空字符串"}
steps 必须按执行顺序拆成 1 至 4 项，每项简洁可执行；不得编造信息。标题为空时输出原文前30字；note 必须保留原始信息。"""},
            {"role": "user", "content": value[:6000]},
        ]
        try:
            content, model_used = await self._llm.complete(messages)
            logger.info("单条待办 AI 识别完成，使用模型: %s", model_used)
        except Exception:
            # AI 服务暂时不可用时，仍返回可编辑的本地整理结果，避免用户已输入的
            # 待办内容只能丢弃或手动重填。
            logger.exception("单条待办 AI 识别失败，改用本地规则整理")
            return self._local_one_todo(value)
        todo = self.parse_one_todo_json(content, fallback_note=value)
        return todo or self._local_one_todo(value)

    def recognize_one_sync(self, raw_text: str) -> dict | None:
        return asyncio.run(self.recognize_one(raw_text))

    @staticmethod
    def _local_one_todo(value: str) -> dict:
        """无网络时的保底整理：保留全文，给出可编辑标题和谨慎的优先级建议。"""
        compact = re.sub(r"\s+", " ", value).strip()
        first = re.split(r"[。！？!?；;\n]", compact, maxsplit=1)[0].strip()
        title = (first or compact)[:30]
        high_words = ("紧急", "立即", "今天", "评审", "审批", "客户", "交付", "上线", "截止")
        priority = "high" if any(word in compact for word in high_words) else "normal"
        return {
            "title": title,
            "note": compact,
            "steps": [first or compact],
            "priority": priority,
            "due_date": "",
            "local_fallback": True,
        }

    async def advise(self, active_todos: list, app_stats: list[dict]) -> list[dict]:
        """结合当日活动对未完成待办给推进建议（异步，P2 §4.6）

        Args:
            active_todos: 未完成待办（TodoRecord 列表，pending/in_progress）
            app_stats: 当日应用使用统计（query_app_usage_stats 结果）

        Returns:
            建议字典列表 [{"todo_id","type","reason","suggested_progress"?}, ...]，
            LLM 失败返回空列表
        """
        if not active_todos:
            logger.info("无未完成待办，跳过推进建议")
            return []
        messages = self._prompt.build_todo_progress_prompt(active_todos, app_stats)
        try:
            content, model_used = await self._llm.complete(messages)
            logger.info("待办推进建议完成，使用模型: %s", model_used)
        except Exception as exc:
            logger.exception("待办推进建议 LLM 调用失败: %s", exc)
            return []
        valid_ids = {t.id for t in active_todos}
        advices = self.parse_advices_json(content, valid_ids)
        logger.info("生成 %d 条待办推进建议", len(advices))
        return advices

    def advise_sync(self, active_todos: list, app_stats: list[dict]) -> list[dict]:
        """同步包装（便于在非异步上下文中调用）"""
        return asyncio.run(self.advise(active_todos, app_stats))

    @staticmethod
    def parse_todos_json(content: str) -> list[dict]:
        """容错解析 LLM 输出的待办 JSON 数组

        处理：
        - 剥离 ```json ... ``` / ``` ... ``` 代码块包裹
        - 提取首个 JSON 数组片段（LLM 可能输出多余文字）
        - 字段校验与清洗（title 必填、priority 归一化、due_date 格式）
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
            logger.warning("待办 JSON 解析失败: %s；原始片段: %s", exc, array_text[:200])
            return []

        if not isinstance(data, list):
            return []

        cleaned = []
        for item in data:
            todo = _clean_todo_item(item)
            if todo:
                cleaned.append(todo)
            if len(cleaned) >= _MAX_TODOS:
                break
        return cleaned

    @staticmethod
    def parse_advices_json(content: str, valid_ids: set | None = None) -> list[dict]:
        """容错解析推进建议 JSON 数组（复用提取器的 fence/array 解析，P2 §4.6）

        Args:
            valid_ids: 合法的 todo_id 集合；LLM 编造的 id 被过滤（None 则不过滤）
        """
        if not content or not content.strip():
            return []
        text = _strip_code_fence(content.strip())
        array_text = _extract_json_array(text)
        if array_text is None:
            logger.warning("未能从 LLM 输出解析出建议 JSON 数组: %s", content[:200])
            return []
        try:
            data = json.loads(array_text)
        except json.JSONDecodeError as exc:
            logger.warning("建议 JSON 解析失败: %s", exc)
            return []
        if not isinstance(data, list):
            return []
        cleaned = []
        valid = set(valid_ids or [])
        for item in data:
            a = _clean_advice_item(item, valid)
            if a:
                cleaned.append(a)
            if len(cleaned) >= _MAX_ADVICES:
                break
        return cleaned

    @staticmethod
    def parse_one_todo_json(content: str, fallback_note: str = "") -> dict | None:
        """解析 AI 单条待办识别输出，并确保内容字段不会丢失。"""
        text = _strip_code_fence((content or "").strip())
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            item = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
        todo = _clean_todo_item(item)
        if todo:
            todo["note"] = todo["note"] or fallback_note
        return todo


def _strip_code_fence(text: str) -> str:
    """剥离 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）"""
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text


def _extract_json_array(text: str) -> str | None:
    """从文本中提取首个完整的 JSON 数组片段（平衡括号 + 字符串转义感知）"""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def _clean_todo_item(item) -> dict | None:
    """清洗单条待办：校验 + 归一化，不合法返回 None"""
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", "")).strip()
    if not title:
        return None
    title = title[:_MAX_TITLE_LEN]

    priority = str(item.get("priority", "normal")).strip().lower()
    if priority not in _VALID_PRIORITIES:
        priority = "normal"

    due_date = str(item.get("due_date", "") or "").strip()
    if due_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
        due_date = ""  # 不符合 YYYY-MM-DD 的视为无

    note = str(item.get("note", "") or "").strip()

    cleaned = {
        "title": title,
        "priority": priority,
        "due_date": due_date,
        "note": note,
    }
    steps = item.get("steps", [])
    if isinstance(steps, list):
        cleaned_steps = [str(step).strip()[:180] for step in steps if str(step).strip()][:4]
        if cleaned_steps:
            cleaned["steps"] = cleaned_steps
    return cleaned


def _clean_advice_item(item, valid_ids: set) -> dict | None:
    """清洗单条推进建议：校验 + 归一化，不合法返回 None（P2 §4.6）"""
    if not isinstance(item, dict):
        return None
    try:
        todo_id = int(item.get("todo_id"))
    except (TypeError, ValueError):
        return None
    if valid_ids and todo_id not in valid_ids:
        return None  # LLM 编造的 todo_id
    atype = str(item.get("type", "")).strip().lower()
    if atype not in _VALID_ADVICE_TYPES:
        return None
    reason = str(item.get("reason", "") or "").strip()
    if not reason:
        return None
    result = {"todo_id": todo_id, "type": atype, "reason": reason[:300]}
    if atype == "progress":
        try:
            p = int(item.get("suggested_progress"))
        except (TypeError, ValueError):
            return None  # progress 必须有合法 suggested_progress
        result["suggested_progress"] = max(0, min(100, p))
    return result
