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
            # 密码管理器
            "1password.exe",
            "bitwarden.exe",
            "dashlane.exe",
            "keepass.exe",
            "keepassxc.exe",
            # API key/凭据管理工具
            "cc-switch.exe",
            # 银行/支付钱包
            "alipaywallet.exe",
            "alipaypaywallet.exe",
            # 远程桌面（密码输入风险高）
            "mstsc.exe",
            "anydesk.exe",
            "teamviewer.exe",
            "todesk.exe",
            "sunloginclient.exe",
            # SSH/远程登录客户端
            "putty.exe",
            "mobaxterm.exe",
            "xshell.exe",
            "securecrt.exe",
        ],
        "title_filter_keywords": ["银行", "bank", "登录", "login", "sign in", "网银", "账号密码", "inprivate", "无痕"],
        "custom_filter_patterns": [],
        "privacy_mode_duration": 30,
    },
    "storage": {
        "db_path": "./data/blackbox.db",
        "markdown_export_dir": "./data/logs",
        "retention_days": 90,
        "auto_archive": True,
        "encryption_enabled": False,  # 是否启用数据库加密（需安装 sqlcipher3）
        "encryption_key_env": "WORKTRACE_DB_KEY",  # 加密密钥的环境变量名
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
    "rest_api": {
        "enabled": False,        # 默认关闭，用户需手动开启
        "port": 19527,           # 默认端口
        "host": "127.0.0.1",     # 仅本地访问
    },
}
