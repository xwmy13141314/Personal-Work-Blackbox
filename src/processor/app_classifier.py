"""应用自动分类器

基于进程名和窗口标题，将应用会话自动归类到预设分类。
支持自定义正则规则扩展。
"""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 预置分类规则：按优先级排序，先匹配先返回
DEFAULT_RULES: list[dict] = [
    {
        "category": "开发工具",
        "icon": "💻",
        "patterns": {
            "process": [
                r"(?i)(code|vscode|devenv|idea|pycharm|webstorm|phpstorm|sublime|atom|vim|neovim|notepad\+\+|cursor|fleet|goland|clion|rider|datagrip)",
                r"(?i)(git|github|gitkraken|sourcetree|tower|fork)",
                r"(?i)(terminal|cmd|powershell|pwsh|wsl|bash|iterm|conhost|WindowsTerminal)",
                r"(?i)(docker|kitematic|podman)",
                r"(?i)(postman|insomnia|fiddler|charles|wireshark)",
                r"(?i)(navicat|dbeaver|heidisql|tableplus|mysql|pgadmin|mongo|redis)",
            ],
            "title": [
                r"(?i)(\.py|\.js|\.ts|\.tsx|\.jsx|\.go|\.rs|\.java|\.cpp|\.c|\.h|\.rb|\.php|\.vue|\.svelte)",
                r"(?i)(visual studio code|intellij|pycharm|webstorm)",
                r"(?i)(git hub|gitlab|bitbucket|stack overflow)",
                r"(?i)(docker|kubernetes|terminal|命令提示符|powershell)",
            ],
        },
    },
    {
        "category": "浏览器",
        "icon": "🌐",
        "patterns": {
            "process": [
                r"(?i)(chrome|firefox|msedge|safari|opera|brave|vivaldi|arc|chromium)",
                r"(?i)(maxthon|360se|360chrome|qqbrowser|ubrowser|liebao)",
            ],
            "title": [
                r"(?i)(google|baidu|bing|duckduckgo|yahoo search)",
                r"(?i)(chrome|firefox|edge)",
            ],
        },
    },
    {
        "category": "通讯社交",
        "icon": "💬",
        "patterns": {
            "process": [
                r"(?i)(wechat|weixin|qq|tim|dingtalk|lark|feishu|teams|slack|discord|telegram|skype|zoom|webex|tencent_meeting|wemeet)",
                r"(?i)(whatsapp|signal|line|messenger|outlook|foxmail|网易邮箱)",
            ],
            "title": [
                r"(?i)(微信|qq|钉钉|飞书|teams|slack|discord|telegram|zoom|腾讯会议)",
                r"(?i)(outlook|gmail|foxmail|邮箱|mail)",
            ],
        },
    },
    {
        "category": "办公文档",
        "icon": "📄",
        "patterns": {
            "process": [
                r"(?i)(winword|excel|powerpnt|outlook|onenote|wps|et|wpp|typora|obsidian|notion|evernote|印象笔记)",
                r"(?i)(acrobat|foxit|sumatrapdf|pdfxchange|cajviewer)",
                r"(?i)(visio|project|microsoft teams|mindmaster|xmind|freeplane)",
            ],
            "title": [
                r"(?i)(\.docx?|\.xlsx?|\.pptx?|\.pdf|\.odt|\.ods|\.odp)",
                r"(?i)(word|excel|powerpoint|wps|notion|obsidian|typora|onedrive)",
            ],
        },
    },
    {
        "category": "设计创作",
        "icon": "🎨",
        "patterns": {
            "process": [
                r"(?i)(photoshop|illustrator|indesign|premiere|afterfx|lightroom|gimp|inkscape|krita|blender|cinema4d|3dsmax|maya|figma|sketch|framer|zeplin)",
                r"(?i)(davinci|resolve|obs|streamlabs|audacity|flstudio|ableton|cubase)",
            ],
            "title": [
                r"(?i)(photoshop|illustrator|premiere|after effects|figma|sketch|blender)",
                r"(?i)(\.psd|\.ai|\.sketch|\.fig|\.blend|\.prproj)",
            ],
        },
    },
    {
        "category": "娱乐休闲",
        "icon": "🎮",
        "patterns": {
            "process": [
                r"(?i)(steam|epicgames|battle\.net|riotclient|origin|ubisoft|gog|wechatgame)",
                r"(?i)(bilibili|douyin|tiktok|kugou|netease_cloudmusic|qqmusic|spotify|netflix|youtube|mango_tv|iqiyi|youku|tencent_video)",
                r"(?i)(minecraft|csgo|dota2|league|valorant|genshin|starcraft|overwatch|wow|diablo)",
            ],
            "title": [
                r"(?i)(b站|bilibili|抖音|tiktok|youtube|netflix|spotify|网易云|酷狗|腾讯视频|爱奇艺|优酷|芒果)",
                r"(?i)(steam|游戏|game|minecraft|league of legends)",
            ],
        },
    },
    {
        "category": "系统工具",
        "icon": "⚙️",
        "patterns": {
            "process": [
                r"(?i)(explorer|taskmgr|regedit|mmc|control|settings|systemsettings|snippingtool|sniptool|ms-paint|mspaint)",
                r"(?i)(everything|listary|wox|powertoys|autoruns|procmon|procexp|ccleaner|geekuninstaller)",
                r"(?i)(7z|winrar|bandizip|haozip|peazip)",
                r"(?i)(rclone|filezilla|winscp|cyberduck)",
            ],
            "title": [
                r"(?i)(文件资源管理器|任务管理器|注册表|控制面板|设置|systemsettings)",
                r"(?i)(everything|7-zip|winrar|bandizip|powertoys)",
            ],
        },
    },
    {
        "category": "数据库",
        "icon": "🗄️",
        "patterns": {
            "process": [
                r"(?i)(sqlserver|mysql|postgres|pgadmin|sqlitebrowser|dbeaver|navicat|heidisql|tableplus|mongocompass|redis-desktop|robomongo)",
            ],
            "title": [
                r"(?i)(sql server|mysql|postgresql|sqlite|mongodb|redis|navicat|dbeaver)",
                r"(?i)(\.sql|\.db|\.sqlite)",
            ],
        },
    },
    {
        "category": "AI 工具",
        "icon": "🤖",
        "patterns": {
            "process": [
                r"(?i)(chatgpt|claude|cursor|copilot|tabnine|kite|codeium|continue|ollama|lmstudio)",
            ],
            "title": [
                r"(?i)(chatgpt|claude|ai|gpt|copilot|cursor|ollama|huggingface|midjourney|stable diffusion)",
                r"(?i)(openai|anthropic|bard|gemini|文心一言|通义千问|讯飞星火|kimi|deepseek)",
            ],
        },
    },
]


class AppClassifier:
    """应用分类器

    基于预置规则和自定义规则，将进程名/窗口标题映射到分类。
    """

    def __init__(self, custom_rules: list[dict] | None = None):
        self._rules = list(DEFAULT_RULES)
        if custom_rules:
            # 自定义规则插入到最前面（优先级最高）
            self._rules = custom_rules + self._rules

        # 预编译正则
        self._compiled: list[dict] = []
        for rule in self._rules:
            compiled_patterns = {}
            for key in ("process", "title"):
                patterns = rule.get("patterns", {}).get(key, [])
                compiled_patterns[key] = [
                    re.compile(p, re.IGNORECASE) for p in patterns
                ]
            self._compiled.append({
                "category": rule["category"],
                "icon": rule.get("icon", "📦"),
                "patterns": compiled_patterns,
            })

        logger.info("AppClassifier 初始化完成，规则数: %d", len(self._compiled))

    def classify(self, process_name: str, window_title: str = "") -> tuple[str, str]:
        """分类应用

        Args:
            process_name: 进程名（如 "chrome.exe"）
            window_title: 窗口标题

        Returns:
            (category, icon) 分类名和图标 emoji
        """
        process_name = process_name or ""
        window_title = window_title or ""

        for rule in self._compiled:
            patterns = rule["patterns"]
            # 先匹配进程名
            for regex in patterns.get("process", []):
                if regex.search(process_name):
                    return rule["category"], rule["icon"]
            # 再匹配窗口标题
            for regex in patterns.get("title", []):
                if regex.search(window_title):
                    return rule["category"], rule["icon"]

        return "其他", "📦"

    def get_all_categories(self) -> list[dict]:
        """获取所有预置分类列表"""
        seen = set()
        result = []
        for rule in self._rules:
            cat = rule["category"]
            if cat not in seen:
                seen.add(cat)
                result.append({
                    "category": cat,
                    "icon": rule.get("icon", "📦"),
                })
        # 确保"其他"在最后
        if "其他" not in seen:
            result.append({"category": "其他", "icon": "📦"})
        return result
