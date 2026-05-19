"""默认配置常量"""

DEFAULTS = {
    "collection": {
        "window_poll_interval": 1,
        "keyboard_enabled": True,
        "capture_hotkeys": True,
        "clipboard_enabled": True,
        "clipboard_max_length": 10240,
        "idle_threshold": 300,
    },
    "privacy": {
        "app_blacklist": [
            "1password.exe",
            "bitwarden.exe",
            "dashlane.exe",
            "keepass.exe",
            "keepassxc.exe",
        ],
        "title_filter_keywords": ["银行", "bank", "登录", "login"],
        "custom_filter_patterns": [],
        "privacy_mode_duration": 30,
    },
    "storage": {
        "db_path": "./data/blackbox.db",
        "markdown_export_dir": "./data/logs",
        "retention_days": 90,
        "auto_archive": True,
    },
    "ai": {
        "default_provider": "glm",
        "auto_report_time": "18:00",
        "glm": {
            "api_key": "",
            "model": "glm-4-flash",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "qwen2.5:7b",
            "temperature": 0.3,
        },
        "deepseek": {
            "api_key": "",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
        },
        "openai": {
            "api_key": "",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
        },
    },
    "performance": {
        "input_buffer_max_length": 5000,
        "input_buffer_timeout": 30,
        "journal_mode": "WAL",
    },
    "notification": {
        "on_report_generated": True,
        "on_privacy_mode": True,
    },
}
