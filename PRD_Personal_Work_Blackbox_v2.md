# 产品需求文档 (PRD)：Personal Work Blackbox（个人工作黑匣子）

> **版本：** V2.0（优化版）
> **状态：** 技术方案就绪 / 待开发
> **产品经理：** Wei Xia
> **日期：** 2026-05-13
> **基于：** V1.0 草案 + 技术可行性分析优化

---

## 1. 产品概述

### 1.1 背景与痛点

作为产品经理，每天在飞书、邮件、Jira、文档工具、AI 对话工具间频繁切换。大量决策和信息碎片散落在不同沟通记录中，事后回溯成本极高。现有的全量录屏方案数据量大、隐私风险高且难以检索。

**核心矛盾：** 需要完整记录每日工作轨迹，但不想承受录屏的高存储成本和隐私风险。

### 1.2 产品定位

一款基于 **键盘输入流（Key-stream）+ 应用上下文（Context）+ 剪贴板（Clipboard）** 的轻量化、本地化个人日志自动化采集与 AI 摘要工具。

**一句话描述：** 把你每天在电脑上做的事情自动变成结构化日报。

### 1.3 核心价值主张

```
零干预采集 → 结构化存储 → AI 智能摘要 → 可直接使用的日报
```

---

## 2. 目标与范围

### 2.1 目标

| 类型 | 描述 |
|------|------|
| **核心目标** | 以极低的数据成本（纯文本）完整复现每日工作产出，并通过 AI 生成可直接使用的日报 |
| **体验目标** | 安装后完全无感运行，用户唯一的操作是"打开今日日报" |
| **技术目标** | CPU < 1%，内存 < 100MB，每日数据 < 1MB |

### 2.2 非目标（明确排除）

- ❌ 监控他人（本工具仅限个人本地使用）
- ❌ 高清录屏或截图存储
- ❌ 实时协作或远程同步
- ❌ 移动端采集
- ❌ 任何形式的数据上传

---

## 3. 系统架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Personal Work Blackbox                           │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   Layer 1: 系统采集层 (Collector)              │  │
│  │                                                               │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │  │
│  │  │ KeyboardHook │ │ WindowTracker│ │ ClipboardMonitor     │  │  │
│  │  │ (pynput)     │ │ (Win32 API)  │ │ (win32clipboard)     │  │  │
│  │  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘  │  │
│  │         │                │                     │              │  │
│  │  ┌──────┴────────────────┴─────────────────────┴───────────┐  │  │
│  │  │                  IdleDetector (Win32 API)                │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │ 原始事件流                          │
│  ┌────────────────────────────┴──────────────────────────────────┐  │
│  │                  Layer 2: 处理管道 (Processor)                  │  │
│  │                                                               │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │  │
│  │  │ InputBuffer  │ │PrivacyFilter │ │ ContextEnricher      │  │  │
│  │  │ (退格状态机) │ │ (敏感过滤)   │ │ (上下文关联)         │  │  │
│  │  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘  │  │
│  │         │                │                     │              │  │
│  │  ┌──────┴────────────────┴─────────────────────┴───────────┐  │  │
│  │  │                  SessionManager (会话管理)                │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │ 结构化数据                          │
│  ┌────────────────────────────┴──────────────────────────────────┐  │
│  │                  Layer 3: 存储层 (Storage)                      │  │
│  │                                                               │  │
│  │  ┌──────────────────────┐ ┌────────────────────────────────┐  │  │
│  │  │ SQLite (结构化存储)   │ │ MarkdownExporter (每日导出)    │  │  │
│  │  └──────────────────────┘ └────────────────────────────────┘  │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │ 查询接口                            │
│  ┌────────────────────────────┴──────────────────────────────────┐  │
│  │                  Layer 4: AI 摘要层 (Intelligence)              │  │
│  │                                                               │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │  │
│  │  │ PromptEngine │ │  LLMClient   │ │  ReportGenerator    │  │  │
│  │  │ (模板管理)   │ │ (模型调用)   │ │  (报告生成)         │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────────┘  │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │ 生成报告                            │
│  ┌────────────────────────────┴──────────────────────────────────┐  │
│  │                  Layer 5: 交互层 (UI)                           │  │
│  │                                                               │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │  │
│  │  │ SystemTray   │ │ ConfigManager│ │  Notification        │  │  │
│  │  │ (托盘图标)   │ │ (YAML配置)  │ │  (Toast通知)         │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 技术选型

| 组件 | 技术方案 | 选型理由 |
|------|---------|---------|
| **开发语言** | Python 3.11+ | 快速验证、丰富生态、pywin32 原生支持 Win32 API |
| **键盘监听** | `pynput` 库 | 封装了 `WH_KEYBOARD_LL`，API 简洁，稳定可靠 |
| **窗口追踪** | `ctypes` + Win32 API | 零依赖，直接调用 `GetForegroundWindow` 等 |
| **剪贴板** | `win32clipboard` (pywin32) | 支持监听剪贴板变化事件 |
| **空闲检测** | `GetLastInputInfo` (Win32 API) | 系统级准确判断 |
| **本地存储** | SQLite 3 | 单文件、零配置、查询灵活 |
| **日志导出** | 每日自动生成 Markdown | 符合人类阅读习惯，可被 AI 直接处理 |
| **AI 摘要** | Ollama (本地) / DeepSeek API (云端) | 本地优先，云端备选 |
| **系统托盘** | `pystray` + Pillow | 轻量级托盘图标 |
| **配置管理** | YAML 配置文件 | 人类可读可编辑 |
| **打包分发** | PyInstaller → 单 exe | 零安装，双击即用 |

### 3.3 数据流

```
[键盘输入] ──→ pynput Hook ──→ 键码流 ──┐
                                         │
[窗口切换] ──→ Win32 轮询  ──→ 切换事件 ──┼──→ InputBuffer (状态机)
                                         │      │
[剪贴板]   ──→ 剪贴板监听 ──→ 复制内容 ──┘      │ 退格处理 + 文本还原
                                                │
                                          PrivacyFilter
                                          (敏感信息过滤)
                                                │
                                          ContextEnricher
                                          (关联窗口上下文)
                                                │
                                          SessionManager
                                          (按应用分组为会话)
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                              SQLite 存储            Markdown 导出
                                    │                       │
                              AI 查询接口            每日 .md 文件
                                    │
                              LLM 摘要生成
                                    │
                              结构化日报输出
```

---

## 4. 功能需求详细设计

### 4.1 环境监测模块 (Environment Monitor)

**职责：** 实时感知用户当前的工作上下文。

#### 4.1.1 窗口追踪器 (WindowTracker)

| 参数 | 值 | 说明 |
|------|-----|------|
| 轮询间隔 | 1 秒 | 平衡精度与性能 |
| 采集字段 | process_name, window_title, timestamp | 每次切换记录 |
| 触发条件 | 前台窗口句柄变化 | 非定时记录，事件驱动 |

```python
# 核心逻辑伪代码
class WindowTracker:
    POLL_INTERVAL = 1  # 秒

    def poll(self):
        hwnd = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, byref(pid))

        process_name = self._get_process_name(pid.value)
        title = self._get_window_title(hwnd)

        if hwnd != self._last_hwnd:
            self._on_window_switch(
                from_window=self._last_context,
                to_window=WindowContext(process_name, title, hwnd),
                duration=now() - self._last_switch_time
            )
        self._last_hwnd = hwnd
        self._last_switch_time = now()
```

#### 4.1.2 空闲检测器 (IdleDetector)

| 参数 | 值 | 说明 |
|------|-----|------|
| 检测方式 | `GetLastInputInfo` | 系统级准确判断 |
| 空闲阈值 | 300 秒（5 分钟） | 可配置 |
| 状态 | `active` / `idle` / `locked` | 三种状态 |

**行为定义：**
- 用户无键盘/鼠标操作超过阈值 → 标记 `idle`
- 系统 `WM_WTSSESSION_CHANGE` 锁屏事件 → 标记 `locked`
- 从 idle 恢复 → 记录 idle 时长，提交当前输入缓冲区

#### 4.1.3 系统事件监听

| 事件 | 处理方式 | 说明 |
|------|---------|------|
| 系统锁屏 | `WM_WTSSESSION_CHANGE` | 暂停所有采集 |
| 系统解锁 | 同上 | 恢复采集 |
| 系统休眠 | `WM_POWERBROADCAST` | 暂停采集，保存状态 |
| 系统唤醒 | 同上 | 恢复采集 |

---

### 4.2 智能输入捕获模块 (Input Capture)

**职责：** 记录用户的键盘输入，还原为可读文本。

#### 4.2.1 键盘监听 (KeyboardHook)

**核心挑战：中文输入法兼容**

Windows 中文输入法的特殊性在于，键盘钩子捕获的是**拼音键码**而非最终**汉字**。这是一个已知的架构限制。

**MVP 策略：分层捕获**

```
Level 1 (MVP):  pynput 键码捕获
  - 英文输入：直接获取字符
  - 中文输入：捕获拼音序列 + Enter 键
  - 快捷键：记录 Ctrl+C/V/S 等组合键
  - 退格/删除：传递给 InputBuffer 处理

Level 2 (V1.1): UI Automation 增强
  - 周期性读取当前焦点文本框内容（每 2-3 秒）
  - diff 前后差异，提取增量文本
  - 适用于：浏览器输入框、飞书聊天框、IDE 编辑器

Level 3 (V1.2): TSF 集成（远期）
  - 注册 Text Services Framework 事件
  - 获取 IME 最终组合结果
  - 需要 C++ 扩展或 ctypes 深度调用
```

**MVP 阶段的实际效果：**

| 输入场景 | 能捕获到什么 | 信息是否足够 |
|----------|------------|-------------|
| 英文打字（IDE 写代码/文档） | 完整英文字符流 | ✅ 足够 |
| 中文打字（飞书/微信聊天） | 拼音序列 + 窗口标题 | ⚠️ 结合上下文可推断 |
| 搜索框输入 | 搜索关键词（通常是英文） | ✅ 足够 |
| 浏览器地址栏 | URL 片段 | ✅ 足够 |
| 复制粘贴 | Ctrl+C/V 事件 + 剪贴板内容 | ✅ 足够 |

**关键结论：** 对于"生成每日日报"这个目标，窗口标题 + 拼音序列 + 英文输入 + 剪贴板内容的组合，已经足够 AI 推断用户做了什么。

#### 4.2.2 输入缓冲区状态机 (InputBuffer)

**职责：** 将原始键码流还原为可读文本。

```
状态机模型：

[EMPTY] ──字符键──→ [TYPING]
[TYPING] ──字符键──→ [TYPING]      → 追加到缓冲区
[TYPING] ──Backspace──→ [TYPING]   → 删除缓冲区末字符
[TYPING] ──Ctrl+A+输入──→ [TYPING] → 清空缓冲区，写入新字符
[TYPING] ──Enter──→ [COMMITTED]    → 提交缓冲区内容
[TYPING] ──方向键──→ [TYPING]      → 标记光标移动（暂停追加）
[TYPING] ──窗口切换──→ [COMMITTED] → 强制提交当前缓冲区
[TYPING] ──空闲超时──→ [COMMITTED] → 超时自动提交
[COMMITTED] ──任意输入──→ [TYPING] → 开始新的缓冲区
```

```python
class InputBuffer:
    """输入缓冲区状态机 — 处理退格等编辑逻辑"""

    def __init__(self, max_length: int = 5000):
        self._buffer: str = ""
        self._max_length = max_length
        self._cursor_pos: int = 0
        self._last_commit: str = ""

    def on_char(self, char: str):
        """处理普通字符输入"""
        if self._cursor_pos == len(self._buffer):
            self._buffer += char
        else:
            # 光标不在末尾 → 在中间插入
            self._buffer = self._buffer[:self._cursor_pos] + char + self._buffer[self._cursor_pos:]
        self._cursor_pos += 1

    def on_backspace(self):
        """处理退格键"""
        if self._cursor_pos > 0:
            self._cursor_pos -= 1
            self._buffer = self._buffer[:self._cursor_pos] + self._buffer[self._cursor_pos + 1:]

    def on_delete(self):
        """处理 Delete 键"""
        if self._cursor_pos < len(self._buffer):
            self._buffer = self._buffer[:self._cursor_pos] + self._buffer[self._cursor_pos + 1:]

    def on_ctrl_a(self):
        """Ctrl+A 全选 → 后续输入会替换全部"""
        self._select_all = True

    def on_enter(self) -> str | None:
        """Enter → 提交当前缓冲区"""
        return self.commit()

    def commit(self) -> str:
        """提交缓冲区内容，返回处理后的文本"""
        text = self._buffer.strip()
        self._last_commit = text
        self._buffer = ""
        self._cursor_pos = 0
        return text

    @property
    def current_text(self) -> str:
        return self._buffer
```

#### 4.2.3 剪贴板监控 (ClipboardMonitor)

| 行为 | 说明 |
|------|------|
| 监听方式 | `SetClipboardViewer` / `AddClipboardFormatListener` |
| 触发条件 | 剪贴板内容发生变化 |
| 记录内容 | 复制的文本内容 + 来源进程 + 时间戳 |
| 过滤规则 | 仅记录文本类型，忽略图片和文件 |
| 大小限制 | 单条记录限制 10KB，超长内容截断并标记 |

#### 4.2.4 隐私过滤器 (PrivacyFilter)

**这是键盘记录方案的核心安全组件，必须在数据写入存储之前执行。**

**过滤层级：**

```
Level 1: 应用级黑名单（完全不记录）
┌──────────────────────────────────────────────────────────┐
│  默认黑名单进程：                                         │
│  - 1password.exe, bitwarden.exe, dashlane.exe            │
│  - keepass.exe, keepassxc.exe                            │
│  - 银行相关应用进程名                                      │
│  - Windows 凭据管理器 (credwiz.exe)                       │
│                                                          │
│  行为：当黑名单应用为前台窗口时，暂停所有键盘记录          │
│  状态变更事件仍然记录（用于计算空闲时间）                  │
└──────────────────────────────────────────────────────────┘

Level 2: 内容级过滤（对记录内容进行脱敏）
┌──────────────────────────────────────────────────────────┐
│  规则 1: 连续 ≥6 位纯数字 → 替换为 [FILTERED_NUM]        │
│  规则 2: 匹配密码字段模式 → 替换为 [FILTERED_PWD]        │
│    - 紧跟 "密码"/"password"/"pwd" 之后的输入              │
│    - Tab 切换到密码字段后的输入                            ││
│  规则 3: 邮箱地址 → 保留域名，脱敏用户名部分              │
│  规则 4: 身份证号模式 → 替换为 [FILTERED_ID]             │
│  规则 5: 手机号模式 → 替换为 [FILTERED_PHONE]            │
└──────────────────────────────────────────────────────────┘

Level 3: 用户自定义规则
┌──────────────────────────────────────────────────────────┐
│  配置文件中支持用户自定义：                                │
│  - 追加黑名单应用                                         │
│  - 追加窗口标题关键词过滤（如包含"银行"的窗口）           │
│  - 追加内容正则过滤规则                                    │
│  - 设置"隐私模式"快捷键：按下后暂停记录 N 分钟            │
└──────────────────────────────────────────────────────────┘
```

```python
class PrivacyFilter:
    """隐私过滤器 — 在数据写入存储前执行"""

    # 连续6位以上纯数字（疑似密码/验证码/银行卡号）
    NUMBER_PATTERN = re.compile(r'\d{6,}')
    # 邮箱
    EMAIL_PATTERN = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    # 身份证号
    ID_CARD_PATTERN = re.compile(r'\d{17}[\dXx]')
    # 手机号
    PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')

    # 密码上下文关键词（用于识别密码输入场景）
    PASSWORD_CONTEXT = {'密码', 'password', 'passwd', 'pwd', 'pin', 'secret'}

    def __init__(self, config: PrivacyConfig):
        self._blacklist = set(config.app_blacklist)
        self._title_keywords = config.title_filter_keywords
        self._custom_patterns = [re.compile(p) for p in config.custom_filter_patterns]

    def should_pause_recording(self, process_name: str, window_title: str) -> bool:
        """判断是否应暂停当前窗口的键盘记录"""
        process_lower = process_name.lower()
        if process_lower in self._blacklist:
            return True
        if any(kw in window_title for kw in self._title_keywords):
            return True
        return False

    def filter_text(self, text: str, context: str = "") -> tuple[str, bool]:
        """过滤文本中的敏感信息，返回 (过滤后文本, 是否发生了过滤)"""
        filtered = False
        result = text

        # 密码上下文检测
        if any(kw in context.lower() for kw in self.PASSWORD_CONTEXT):
            return "[FILTERED_PWD]", True

        # 正则替换
        if self.NUMBER_PATTERN.search(result):
            result = self.NUMBER_PATTERN.sub('[FILTERED_NUM]', result)
            filtered = True
        if self.EMAIL_PATTERN.search(result):
            result = self.EMAIL_PATTERN.sub('[FILTERED_EMAIL]', result)
            filtered = True
        if self.ID_CARD_PATTERN.search(result):
            result = self.ID_CARD_PATTERN.sub('[FILTERED_ID]', result)
            filtered = True
        if self.PHONE_PATTERN.search(result):
            result = self.PHONE_PATTERN.sub('[FILTERED_PHONE]', result)
            filtered = True

        # 用户自定义规则
        for pattern in self._custom_patterns:
            if pattern.search(result):
                result = pattern.sub('[FILTERED_CUSTOM]', result)
                filtered = True

        return result, filtered
```

---

### 4.3 数据存储模块 (Storage)

#### 4.3.1 SQLite 数据库 Schema

```sql
-- ============================================================
-- Personal Work Blackbox - 数据库 Schema V2.0
-- ============================================================

-- 应用会话表：用户在一个应用窗口中的连续活动
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time  DATETIME NOT NULL,
    end_time    DATETIME,
    process_name TEXT NOT NULL,
    window_title TEXT,
    idle_seconds  INTEGER DEFAULT 0,   -- 会话内空闲总时长
    active_seconds INTEGER DEFAULT 0,  -- 会话内活跃总时长
    is_filtered INTEGER DEFAULT 0      -- 是否触发了隐私过滤
);

-- 窗口切换事件
CREATE TABLE window_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   DATETIME NOT NULL,
    event_type  TEXT NOT NULL,          -- 'switch' | 'idle_start' | 'idle_end' | 'lock' | 'unlock' | 'suspend' | 'resume'
    process_name TEXT,
    window_title TEXT,
    duration_seconds INTEGER,           -- 在上一个窗口停留的秒数
    session_id  INTEGER REFERENCES sessions(id)
);

-- 输入文本片段（经过退格处理和隐私过滤后的文本）
CREATE TABLE text_segments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id),
    timestamp   DATETIME NOT NULL,
    raw_text    TEXT NOT NULL,          -- 处理后的文本
    source      TEXT NOT NULL,          -- 'keyboard' | 'clipboard' | 'ime'
    is_filtered INTEGER DEFAULT 0,      -- 是否被隐私过滤器处理过
    char_count  INTEGER DEFAULT 0       -- 原始字符数（用于统计）
);

-- 剪贴板记录
CREATE TABLE clipboard_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      DATETIME NOT NULL,
    content        TEXT NOT NULL,
    content_length INTEGER NOT NULL,
    source_process TEXT,
    source_window  TEXT,
    is_filtered    INTEGER DEFAULT 0
);

-- AI 生成的日报
CREATE TABLE daily_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date       DATE NOT NULL UNIQUE,
    raw_data_summary  TEXT,             -- AI 输入的原始数据摘要
    structured_report TEXT NOT NULL,     -- AI 生成的结构化报告
    model_used        TEXT NOT NULL,     -- 'ollama:llama3' | 'deepseek:chat' 等
    generated_at      DATETIME NOT NULL,
    format            TEXT DEFAULT 'markdown',
    token_count       INTEGER DEFAULT 0
);

-- 索引
CREATE INDEX idx_sessions_start ON sessions(start_time);
CREATE INDEX idx_sessions_process ON sessions(process_name);
CREATE INDEX idx_window_events_timestamp ON window_events(timestamp);
CREATE INDEX idx_text_segments_session ON text_segments(session_id);
CREATE INDEX idx_text_segments_timestamp ON text_segments(timestamp);
CREATE INDEX idx_clipboard_timestamp ON clipboard_records(timestamp);
CREATE INDEX idx_reports_date ON daily_reports(report_date);
```

#### 4.3.2 每日 Markdown 导出格式

```markdown
# 📋 工作日志 - 2026-05-13（周三）

## 📊 今日概览

| 应用 | 活跃时长 | 会话数 |
|------|---------|--------|
| VS Code | 3h 25m | 12 |
| 飞书 | 2h 10m | 28 |
| Chrome | 1h 45m | 15 |
| Outlook | 0h 40m | 6 |

**总活跃时间：** 8h 15m
**空闲/休息：** 1h 20m

---

## 📝 活动时间线

### 09:00 - 09:45 | VS Code — project-x/src/main.py
> 编写了用户认证模块，实现了 JWT token 验证逻辑...
> [剪贴板] 复制了 API 文档中的认证示例代码

### 09:45 - 10:30 | 飞书 — 研发讨论组
> 讨论了 RugOne Xlink7 天线防水等级问题
> [剪贴板] 复制了 IP68 测试标准文档链接

### 10:30 - 11:15 | Chrome — Jira Board
> 查看了 Sprint 看板，更新了 3 个任务状态
> [剪贴板] 复制了 TASK-1234 的工单描述

---

## 🤖 AI 每日总结

### 已完成事项
- ✅ 完成用户认证模块（JWT）的开发
- ✅ 确认 Xlink7 天线防水等级为 IP68

### 沟通结论
- 研发组确认天线方案可行，下周可进入测试阶段

### 待办跟进
- ⏳ TASK-1234: 需要补充单元测试
- ⏳ 飞书中提到的 API 接口文档需要更新
```

---

### 4.4 AI 摘要模块 (Intelligence Layer)

#### 4.4.1 Prompt 模板设计

```yaml
# config/prompts/daily_report.yaml
system_prompt: |
  你是一个个人工作日志分析助手。你的任务是分析用户一天的电脑活动记录，
  生成结构化的工作日报。

  规则：
  1. 基于实际记录的窗口活动、输入内容和剪贴板数据生成报告
  2. 不要编造未记录的信息
  3. 对于无法确定的内容，标注"（信息不足）"
  4. 敏感信息（标记为 [FILTERED_*]）不要尝试还原
  5. 使用简洁的中文
  6. 输出 Markdown 格式

user_prompt_template: |
  请分析以下今日活动记录，生成工作日报：

  ## 今日应用使用统计
  {app_usage_stats}

  ## 活动时间线
  {activity_timeline}

  ## 输入内容摘要
  {text_segments_summary}

  ## 剪贴板记录
  {clipboard_records}

  请生成包含以下部分的日报：
  1. 今日概览（一段话总结今天做了什么）
  2. 已完成事项（按重要程度排序）
  3. 沟通结论（从聊天和邮件中提取的关键决策）
  4. 待办跟进（尚未完成的任务）
  5. 时间分布分析（各类工作的时间占比）
```

#### 4.4.2 LLM 接入方案

```python
class LLMClient:
    """统一的 LLM 调用客户端，支持本地和云端"""

    def __init__(self, config: LLMConfig):
        self._providers = {
            'ollama': OllamaProvider(config.ollama),
            'deepseek': DeepSeekProvider(config.deepseek),
            'openai': OpenAIProvider(config.openai),
        }
        self._default_provider = config.default_provider

    async def generate_report(self, data: DailyData) -> str:
        """生成日报"""
        prompt = self._build_prompt(data)
        provider = self._providers[self._default_provider]
        return await provider.complete(prompt)

# 优先级：本地 Ollama → 云端 DeepSeek → 云端 OpenAI
# 本地模型不可用时自动降级到云端
```

| 模型 | 场景 | 预估效果 |
|------|------|---------|
| Ollama + Qwen2.5 7B | 本地运行 | 日报质量中等，隐私最优 |
| DeepSeek Chat | 云端 API | 日报质量高，成本低 |
| Claude / GPT-4o | 云端 API | 日报质量最高，成本较高 |

#### 4.4.3 触发机制

| 触发方式 | 时间 | 说明 |
|----------|------|------|
| **自动触发** | 每天 18:00 | 定时生成当日日报草稿 |
| **手动触发** | 托盘菜单 → "生成本日报告" | 用户随时可触发 |
| **补生成** | 托盘菜单 → "补生成历史报告" | 为过去未生成报告的日期补生成 |

---

### 4.5 用户交互模块 (UI)

#### 4.5.1 系统托盘

```
┌─────────────────────────────────┐
│  🔴 Personal Work Blackbox      │  ← 托盘图标（绿色=运行中，红色=暂停）
├─────────────────────────────────┤
│  📊 今日概览                     │  ← 打开今日活动摘要
│  📋 查看今日报告                 │  ← 打开 AI 生成的日报
│  ⏸ 暂停采集 / ▶ 恢复采集        │  ← 临时暂停/恢复
│  🔇 隐私模式 (30分钟)           │  ← 临时完全停止记录
│  📁 打开数据目录                 │  ← 打开存储文件夹
│  ⚙️ 设置                        │  ← 打开配置文件
│  ❌ 退出                        │
└─────────────────────────────────┘
```

#### 4.5.2 快捷键

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `Ctrl+Alt+P` | 暂停/恢复采集 | 快速切换 |
| `Ctrl+Alt+R` | 生成本日报告 | 手动触发 AI 摘要 |
| `Ctrl+Alt+N` | 隐私模式 (30分钟) | 临时停止所有记录 |

#### 4.5.3 配置文件 (config.yaml)

```yaml
# Personal Work Blackbox 配置文件
# 修改后需重启应用生效

# ==================== 采集设置 ====================
collection:
  # 窗口追踪
  window_poll_interval: 1          # 窗口轮询间隔（秒）

  # 键盘记录
  keyboard_enabled: true           # 是否启用键盘记录
  capture_hotkeys: true            # 是否记录快捷键

  # 剪贴板
  clipboard_enabled: true          # 是否启用剪贴板监控
  clipboard_max_length: 10240      # 单条剪贴板记录最大长度（字节）

  # 空闲检测
  idle_threshold: 300              # 空闲阈值（秒）

# ==================== 隐私设置 ====================
privacy:
  # 应用黑名单（这些应用的键盘输入不会被记录）
  app_blacklist:
    - "1password.exe"
    - "bitwarden.exe"
    - "dashlane.exe"
    - "keepass.exe"
    - "keepassxc.exe"

  # 窗口标题过滤关键词（包含这些关键词的窗口不记录键盘输入）
  title_filter_keywords:
    - "银行"
    - "bank"
    - "登录"
    - "login"

  # 自定义内容过滤正则
  custom_filter_patterns: []

  # 隐私模式持续时间（分钟）
  privacy_mode_duration: 30

# ==================== 存储设置 ====================
storage:
  # 数据库路径（默认在应用目录下）
  db_path: "./data/blackbox.db"

  # Markdown 导出目录
  markdown_export_dir: "./data/logs"

  # 数据保留天数（0 = 永久保留）
  retention_days: 90

  # 超过保留天数的旧数据自动压缩为 gzip 归档
  auto_archive: true

# ==================== AI 设置 ====================
ai:
  # 默认使用的 LLM 提供商: 'ollama' | 'deepseek' | 'openai'
  default_provider: "ollama"

  # 日报自动生成时间（24小时制，空字符串则不自动生成）
  auto_report_time: "18:00"

  ollama:
    base_url: "http://localhost:11434"
    model: "qwen2.5:7b"
    temperature: 0.3

  deepseek:
    api_key: ""                    # 在此填写 API Key
    model: "deepseek-chat"
    base_url: "https://api.deepseek.com/v1"

  openai:
    api_key: ""
    model: "gpt-4o-mini"
    base_url: "https://api.openai.com/v1"

# ==================== 性能设置 ====================
performance:
  # 输入缓冲区最大长度
  input_buffer_max_length: 5000

  # 输入缓冲区超时提交时间（秒）
  input_buffer_timeout: 30

  # SQLite WAL 模式（推荐开启）
  journal_mode: "WAL"

# ==================== 通知设置 ====================
notification:
  # 日报生成完成后是否发送 Toast 通知
  on_report_generated: true

  # 隐私模式激活时是否通知
  on_privacy_mode: true
```

---

## 5. 非功能需求

### 5.1 性能约束

| 指标 | 目标值 | 监控方式 |
|------|--------|---------|
| CPU 占用 | < 1%（平均） | 任务管理器 / 性能监视器 |
| 内存占用 | < 100MB | 进程内存监控 |
| 每日数据量 | < 1MB（纯文本） | 文件大小监控 |
| 窗口追踪延迟 | < 2 秒 | 切换窗口后日志记录时间差 |
| SQLite 写入性能 | < 10ms/次 | 慢查询日志 |

### 5.2 可靠性要求

| 要求 | 实现方式 |
|------|---------|
| 数据不丢失 | SQLite WAL 模式 + 合理的 sync 频率 |
| 崩溃恢复 | 启动时检查数据库完整性，修复损坏的会话记录 |
| 异常重启 | 注册为 Windows 开机自启服务（可选） |

### 5.3 安全要求

| 要求 | 实现方式 |
|------|---------|
| 数据库加密 | SQLCipher 或应用层 AES 加密敏感字段（V1.1 考虑） |
| 配置文件安全 | API Key 等敏感配置支持环境变量覆盖 |
| 进程保护 | 防止其他进程读取数据库文件（文件权限设置） |

---

## 6. 风险分析与规避方案

### 6.1 杀毒软件误报

**风险等级：** 🔴 高
**概率：** 极高（几乎必然发生）

**规避方案：**

```
策略 1: 白名单引导（MVP 必做）
  ├── 安装时提供详细的白名单添加指南
  ├── 覆盖主流杀毒软件（Windows Defender、360、火绒、卡巴斯基）
  └── 提供一键批处理脚本自动添加白名单

策略 2: 应用签名（V1.1）
  ├── 使用自签名证书签名 exe
  └── 降低 SmartScreen 警告级别

策略 3: Windows Store 分发（远期）
  ├── 通过 Microsoft Store 分发
  └── Store 应用默认受信任
```

### 6.2 中文输入法兼容性

**风险等级：** 🟡 中
**概率：** 确定发生

**规避方案：**

```
MVP: 依赖拼音序列 + 窗口上下文 + 剪贴板数据
  └── AI 可从拼音序列和上下文中推断大意

V1.1: 集成 UI Automation 增强捕获
  └── 周期性 diff 文本框内容，获取最终中文文本
```

### 6.3 数据量控制

**风险等级：** 🟢 低
**概率：** 可能

**规避方案：**

```
- 纯文本存储，天然体积小
- 超过 90 天的数据自动归档（gzip 压缩）
- SQLite VACUUM 定期执行
- 大文本段截断（单条记录上限 10KB）
```

### 6.4 隐私泄露

**风险等级：** 🟡 中
**概率：** 取决于过滤准确性

**规避方案：**

```
- 三层隐私过滤（应用黑名单 + 内容正则 + 用户自定义）
- 隐私模式快捷键（一键暂停 30 分钟）
- 所有过滤操作记录日志（方便审计）
- 默认配置偏保守（宁可多过滤，不可漏过滤）
```

---

## 7. 项目结构

```
personal-work-blackbox/
├── src/
│   ├── main.py                     # 入口：启动采集引擎 + 托盘
│   ├── collector/
│   │   ├── __init__.py
│   │   ├── keyboard_hook.py        # pynput 键盘监听
│   │   ├── window_tracker.py       # Win32 窗口追踪
│   │   ├── clipboard_monitor.py    # 剪贴板监控
│   │   └── idle_detector.py        # 空闲检测
│   ├── processor/
│   │   ├── __init__.py
│   │   ├── input_buffer.py         # 输入缓冲区状态机
│   │   ├── privacy_filter.py       # 隐私过滤器
│   │   ├── context_enricher.py     # 上下文关联
│   │   └── session_manager.py      # 会话管理
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py             # SQLite 操作封装
│   │   ├── models.py               # 数据模型定义
│   │   └── markdown_exporter.py    # Markdown 导出
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── llm_client.py           # LLM 统一调用客户端
│   │   ├── prompt_engine.py        # Prompt 模板管理
│   │   └── report_generator.py     # 报告生成
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── system_tray.py          # 系统托盘
│   │   ├── notification.py         # Windows Toast 通知
│   │   └── hotkey_manager.py       # 全局快捷键
│   └── config/
│       ├── __init__.py
│       ├── settings.py             # 配置加载与管理
│       └── defaults.py             # 默认配置常量
├── config/
│   ├── config.yaml                 # 用户配置文件
│   └── prompts/
│       └── daily_report.yaml       # 日报 Prompt 模板
├── data/                           # 运行时数据（gitignore）
│   ├── blackbox.db                 # SQLite 数据库
│   └── logs/                       # Markdown 日志导出目录
├── scripts/
│   ├── setup_whitelist.bat         # Windows Defender 白名单添加脚本
│   └── install_startup.bat         # 开机自启注册脚本
├── tests/
│   ├── test_input_buffer.py
│   ├── test_privacy_filter.py
│   ├── test_window_tracker.py
│   └── test_session_manager.py
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 8. 开发路线图

### Phase 1: 采集核心（第 1 周）

| 任务 | 优先级 | 交付物 |
|------|--------|--------|
| 项目骨架搭建 | P0 | 目录结构 + 依赖管理 |
| WindowTracker 实现 | P0 | 窗口追踪器 |
| KeyboardHook 实现 | P0 | 键盘监听（pynput） |
| InputBuffer 状态机 | P0 | 退格处理 + 文本还原 |
| IdleDetector 实现 | P0 | 空闲检测 |
| SQLite 存储层 | P0 | 数据库 Schema + CRUD |
| 配置文件框架 | P0 | YAML 配置加载 |

### Phase 2: 隐私与处理（第 2 周）

| 任务 | 优先级 | 交付物 |
|------|--------|--------|
| PrivacyFilter 实现 | P0 | 三层隐私过滤 |
| ClipboardMonitor 实现 | P1 | 剪贴板监控 |
| SessionManager 实现 | P1 | 会话聚合逻辑 |
| MarkdownExporter 实现 | P1 | 每日 .md 导出 |
| SystemTray 托盘 | P1 | 后台运行 + 基础菜单 |
| 系统事件监听 | P1 | 锁屏/休眠事件处理 |

### Phase 3: AI 摘要（第 3 周）

| 任务 | 优先级 | 交付物 |
|------|--------|--------|
| Prompt 模板设计 | P0 | 日报/周报模板 |
| Ollama 接入 | P0 | 本地 LLM 调用 |
| DeepSeek API 接入 | P1 | 云端 LLM 备选 |
| ReportGenerator 实现 | P0 | 日报自动生成 |
| Toast 通知 | P2 | 报告生成通知 |
| 定时任务调度 | P1 | 每日定时生成 |

### Phase 4: 打磨交付（第 4 周）

| 任务 | 优先级 | 交付物 |
|------|--------|--------|
| PyInstaller 打包 | P0 | 单 exe 分发 |
| 白名单引导脚本 | P0 | 杀毒软件规避 |
| 性能测试与优化 | P1 | 满足性能约束 |
| 异常恢复机制 | P1 | 崩溃恢复 + 数据修复 |
| 自用测试 | P0 | 连续使用 3 天验证 |
| README 文档 | P2 | 安装使用说明 |

---

## 9. 验收标准

### MVP 验收 Checklist

| # | 验收项 | 通过标准 |
|---|--------|---------|
| 1 | 窗口追踪 | 正确记录应用切换，时间误差 < 2 秒 |
| 2 | 键盘记录 | 英文输入完整还原（含退格处理） |
| 3 | 中文输入 | 记录拼音序列，结合窗口标题可推断内容 |
| 4 | 剪贴板 | 正确捕获 Ctrl+C 的文本内容 |
| 5 | 隐私过滤 | 密码管理器中不记录任何按键 |
| 6 | 敏感过滤 | 连续数字、邮箱、手机号自动脱敏 |
| 7 | 空闲检测 | 5 分钟无操作正确标记为 idle |
| 8 | Markdown 导出 | 每日自动生成格式正确的 .md 文件 |
| 9 | AI 日报 | 生成的日报需包含"已完成事项"和"沟通结论" |
| 10 | 系统托盘 | 后台运行，可通过托盘暂停/恢复 |
| 11 | 资源占用 | CPU < 1%, 内存 < 100MB |
| 12 | 杀毒兼容 | 提供白名单添加引导，添加后正常运行 |

---

## 10. 已知限制（MVP 阶段）

| 限制 | 原因 | 计划解决版本 |
|------|------|-------------|
| 中文输入仅记录拼音序列 | pynput 无法获取 IME 最终输出 | V1.1 (UI Automation) |
| 不支持多显示器独立追踪 | Win32 API 限制 | 不计划支持 |
| 不支持 UWP 应用内容提取 | UWP 沙箱隔离 | V1.2 (有限支持) |
| 无 GUI 设置界面 | MVP 范围控制 | V1.1 (本地 Web) |
| 无数据同步 | 本地优先原则 | 不计划支持 |
| 快捷键可能与其它软件冲突 | 全局快捷键天然冲突 | 提供自定义配置 |
