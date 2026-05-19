"""PrivacyFilter 单元测试"""

import pytest

from src.processor.privacy_filter import PrivacyFilter


@pytest.fixture
def default_filter():
    """创建默认配置的隐私过滤器"""
    config = {
        "app_blacklist": [
            "1password.exe",
            "bitwarden.exe",
            "keepass.exe",
        ],
        "title_filter_keywords": ["银行", "bank", "登录", "login"],
        "custom_filter_patterns": [],
        "privacy_mode_duration": 30,
    }
    return PrivacyFilter(config)


@pytest.fixture
def custom_filter():
    """创建自定义规则的隐私过滤器"""
    config = {
        "app_blacklist": [],
        "title_filter_keywords": [],
        "custom_filter_patterns": [r"API_KEY=\w+"],
        "privacy_mode_duration": 30,
    }
    return PrivacyFilter(config)


class TestAppBlacklist:
    """Level 1: 应用黑名单测试"""

    def test_blacklisted_process(self, default_filter):
        """测试黑名单应用"""
        assert default_filter.should_pause_recording("1password.exe", "1Password") is True
        assert default_filter.should_pause_recording("bitwarden.exe", "Bitwarden") is True

    def test_normal_process(self, default_filter):
        """测试正常应用"""
        assert default_filter.should_pause_recording("chrome.exe", "Google Chrome") is False
        assert default_filter.should_pause_recording("code.exe", "main.py - VS Code") is False

    def test_case_insensitive(self, default_filter):
        """测试进程名大小写不敏感"""
        assert default_filter.should_pause_recording("1Password.exe", "1Password") is True
        assert default_filter.should_pause_recording("BITWARDEN.EXE", "Bitwarden") is True

    def test_title_keyword_filter(self, default_filter):
        """测试窗口标题关键词过滤"""
        assert default_filter.should_pause_recording("chrome.exe", "工商银行 - 个人网银") is True
        assert default_filter.should_pause_recording("app.exe", "用户登录页面") is True
        assert default_filter.should_pause_recording("chrome.exe", "Google Search") is False


class TestContentFilter:
    """Level 2: 内容级过滤测试"""

    def test_six_digit_numbers(self, default_filter):
        """测试连续6位数字过滤"""
        text, filtered = default_filter.filter_text("验证码 123456 已发送")
        assert filtered is True
        assert "123456" not in text
        assert "[FILTERED_NUM]" in text

    def test_phone_number(self, default_filter):
        """测试手机号过滤"""
        text, filtered = default_filter.filter_text("联系手机 13800138000")
        assert filtered is True
        assert "13800138000" not in text
        assert "[FILTERED_PHONE]" in text

    def test_id_card(self, default_filter):
        """测试身份证号过滤"""
        text, filtered = default_filter.filter_text("身份证 110101199001011234")
        assert filtered is True
        assert "110101199001011234" not in text
        assert "[FILTERED_ID]" in text

    def test_email(self, default_filter):
        """测试邮箱过滤"""
        text, filtered = default_filter.filter_text("邮箱 test@example.com")
        assert filtered is True
        assert "test@example.com" not in text
        assert "[FILTERED_EMAIL]" in text

    def test_bank_card(self, default_filter):
        """测试银行卡号过滤"""
        text, filtered = default_filter.filter_text("卡号 6222 0000 1234 5678")
        assert filtered is True
        assert "[FILTERED_BANK]" in text

    def test_normal_text(self, default_filter):
        """测试正常文本不过滤"""
        text, filtered = default_filter.filter_text("今天完成了用户认证模块的开发")
        assert filtered is False
        assert text == "今天完成了用户认证模块的开发"

    def test_short_numbers_not_filtered(self, default_filter):
        """测试短数字不过滤"""
        text, filtered = default_filter.filter_text("完成 TASK-1234 的开发")
        assert filtered is False
        assert "1234" in text

    def test_empty_text(self, default_filter):
        """测试空文本"""
        text, filtered = default_filter.filter_text("")
        assert filtered is False

    def test_password_context(self, default_filter):
        """测试密码上下文过滤"""
        text, filtered = default_filter.filter_text("mySecretPass123", context="请输入密码")
        assert filtered is True
        assert text == "[FILTERED_PWD]"

    def test_password_context_english(self, default_filter):
        """测试英文密码上下文"""
        text, filtered = default_filter.filter_text("abc123", context="Password:")
        assert filtered is True
        assert text == "[FILTERED_PWD]"

    def test_multiple_filters(self, default_filter):
        """测试多重过滤"""
        text, filtered = default_filter.filter_text(
            "联系 test@example.com 或手机 13800138000"
        )
        assert filtered is True
        assert "test@example.com" not in text
        assert "13800138000" not in text


class TestCustomFilter:
    """Level 3: 自定义规则测试"""

    def test_custom_pattern(self, custom_filter):
        """测试自定义正则规则"""
        text, filtered = custom_filter.filter_text("配置 API_KEY=sk1234567890")
        assert filtered is True
        assert "sk1234567890" not in text
        assert "[FILTERED_CUSTOM]" in text

    def test_custom_pattern_no_match(self, custom_filter):
        """测试自定义规则不匹配"""
        text, filtered = custom_filter.filter_text("正常文本内容")
        assert filtered is False


class TestPrivacyMode:
    """隐私模式测试"""

    def test_privacy_mode_activate(self, default_filter):
        """测试隐私模式激活"""
        import time
        assert default_filter.is_privacy_mode is False
        default_filter.activate_privacy_mode(0.01)  # 0.01 分钟
        assert default_filter.is_privacy_mode is True
        time.sleep(1)
        assert default_filter.is_privacy_mode is False

    def test_clipboard_filter(self, default_filter):
        """测试剪贴板过滤"""
        content, filtered = default_filter.filter_clipboard("手机号 13800138000")
        assert filtered is True
