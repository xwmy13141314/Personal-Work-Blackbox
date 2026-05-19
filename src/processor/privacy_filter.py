"""隐私过滤器 — 三层过滤架构，保护敏感信息"""

from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)


class PrivacyFilter:
    """隐私过滤器

    三层过滤架构：
    Level 1: 应用级黑名单 — 完全不记录黑名单应用的键盘输入
    Level 2: 内容级过滤 — 对记录内容进行正则脱敏
    Level 3: 用户自定义规则 — 配置文件中的自定义过滤规则
    """

    # 预定义正则规则
    NUMBER_PATTERN = re.compile(r'\d{6,}')                          # 连续6位+数字
    ID_CARD_PATTERN = re.compile(r'\d{17}[\dXx]')                  # 身份证号
    PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')                     # 手机号
    EMAIL_PATTERN = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')       # 邮箱
    BANK_CARD_PATTERN = re.compile(r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}')  # 银行卡号

    # 密码上下文关键词
    PASSWORD_CONTEXT_KEYWORDS = {
        '密码', 'password', 'passwd', 'pwd', 'pin', 'secret',
        '口令', 'passphrase', 'token',
    }

    def __init__(self, config: dict):
        """
        Args:
            config: privacy 配置字典
        """
        self._app_blacklist = set(
            name.lower().strip() for name in config.get("app_blacklist", [])
        )
        self._title_keywords = config.get("title_filter_keywords", [])
        self._privacy_mode_duration = config.get("privacy_mode_duration", 30)

        # 编译用户自定义正则
        custom_patterns = config.get("custom_filter_patterns", [])
        self._custom_patterns = [re.compile(p) for p in custom_patterns]

        # 隐私模式状态
        self._privacy_mode_until: float = 0.0

    def should_pause_recording(self, process_name: str, window_title: str) -> bool:
        """Level 1: 判断是否应暂停当前窗口的键盘记录

        当黑名单应用为前台窗口时，返回 True。
        """
        process_lower = process_name.lower().strip()
        if process_lower in self._app_blacklist:
            return True
        title_lower = window_title.lower()
        if any(kw.lower() in title_lower for kw in self._title_keywords):
            return True
        return False

    def filter_text(self, text: str, context: str = "") -> Tuple[str, bool]:
        """Level 2+3: 过滤文本中的敏感信息

        Args:
            text: 待过滤文本
            context: 上下文信息（如窗口标题、前一段文本）

        Returns:
            (过滤后的文本, 是否发生了过滤)
        """
        if not text:
            return text, False

        filtered = False
        result = text

        # 密码上下文检测
        context_lower = context.lower()
        if any(kw in context_lower for kw in self.PASSWORD_CONTEXT_KEYWORDS):
            return "[FILTERED_PWD]", True

        # 身份证号（18位，优先级最高）
        if self.ID_CARD_PATTERN.search(result):
            result = self.ID_CARD_PATTERN.sub('[FILTERED_ID]', result)
            filtered = True

        # 银行卡号（16-19位带分隔符）
        if self.BANK_CARD_PATTERN.search(result):
            result = self.BANK_CARD_PATTERN.sub('[FILTERED_BANK]', result)
            filtered = True

        # 手机号（优先于纯数字规则）
        if self.PHONE_PATTERN.search(result):
            result = self.PHONE_PATTERN.sub('[FILTERED_PHONE]', result)
            filtered = True

        # 邮箱
        if self.EMAIL_PATTERN.search(result):
            result = self.EMAIL_PATTERN.sub('[FILTERED_EMAIL]', result)
            filtered = True

        # 连续纯数字（疑似验证码/密码）— 放在最后
        if self.NUMBER_PATTERN.search(result):
            result = self.NUMBER_PATTERN.sub('[FILTERED_NUM]', result)
            filtered = True

        # 用户自定义规则
        for pattern in self._custom_patterns:
            if pattern.search(result):
                result = pattern.sub('[FILTERED_CUSTOM]', result)
                filtered = True

        return result, filtered

    def filter_clipboard(self, content: str) -> Tuple[str, bool]:
        """过滤剪贴板内容（应用同样的内容级规则）"""
        return self.filter_text(content)

    def activate_privacy_mode(self, duration_minutes: float | None = None):
        """激活隐私模式（临时停止所有记录）"""
        import time
        minutes = duration_minutes or self._privacy_mode_duration
        self._privacy_mode_until = time.time() + minutes * 60
        logger.info("隐私模式已激活，持续 %d 分钟", minutes)

    @property
    def is_privacy_mode(self) -> bool:
        """是否处于隐私模式"""
        import time
        return time.time() < self._privacy_mode_until
