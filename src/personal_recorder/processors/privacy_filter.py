from __future__ import annotations

import re


PATTERN_REPLACEMENTS = [
    (re.compile(r"\b1[3-9]\d{9}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[REDACTED_CARD]"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "[REDACTED_ID]"),
    (re.compile(r"(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE), r"\1=[REDACTED_SECRET]"),
    (re.compile(r"\bhttps?://[^\s]*?(token|code|key|secret)=[^\s&]+\b", re.IGNORECASE), "[REDACTED_URL_WITH_SECRET]"),
]

HIGH_SENSITIVITY_HINTS = {
    "password",
    "token",
    "secret",
    "验证码",
    "身份证",
    "银行卡",
    "手机号",
    "邮箱",
}


class PrivacyFilter:
    def redact(self, text: str) -> str:
        redacted = text
        for pattern, replacement in PATTERN_REPLACEMENTS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    def detect_storage_tier(self, text: str, sensitivity: str) -> str:
        lowered = text.lower()
        if sensitivity == "high":
            return "restricted"
        if any(hint.lower() in lowered for hint in HIGH_SENSITIVITY_HINTS):
            return "restricted"
        if redaction_changed(text, self.redact(text)):
            return "restricted"
        return "private"


def redaction_changed(original: str, redacted: str) -> bool:
    return original != redacted
