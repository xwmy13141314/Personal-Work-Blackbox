# Personal Work Blackbox

<<<<<<< HEAD
> 轻量化个人工作日志自动化采集与 AI 报告工具，现已扩展为可独立运行的 `Personal Recorder` 个人记录器升级版。

这个仓库现在包含两条能力线：

- 原始 `Blackbox` 主应用：Windows 端窗口、键盘、剪贴板采集，生成日报、周报、月报
- 新增 `Personal Recorder` 模块：统一事件模型、历史数据迁移、实时 inbox 接入、重要事项提取、待办提取、日历导出、隐私分层存储

## 当前结构

### 1. Blackbox 主应用

保留原有结构和入口：

```bash
python -m src.main --gui
python -m src.main --no-tray
```

它适合：

- Windows 桌面行为采集
- 原有 GUI 使用方式
- 直接生成 Blackbox 风格日报、周报、月报

### 2. Personal Recorder 升级模块

新增模块位置：

- `src/personal_recorder`

它适合：

- 统一事件化存储
- 从原 Blackbox SQLite 历史数据迁移
- 通过 inbox 接更多来源
- 重点事项、待办、日程候选提取
- 更明确的隐私边界

## 快速开始

### 方式一：运行原 Blackbox

```bash
pip install -r requirements.txt
python -m src.main --gui
```

### 方式二：运行 Personal Recorder

建议在仓库根目录执行：

```bash
PYTHONPATH=src python3 -m personal_recorder init-db
PYTHONPATH=src python3 -m personal_recorder import-sample
PYTHONPATH=src python3 -m personal_recorder build-day --date 2026-06-07
PYTHONPATH=src python3 -m personal_recorder build-week --week-start 2026-06-01
PYTHONPATH=src python3 -m personal_recorder export-ics --date 2026-06-07
```

如果你用 `pip install -e .` 安装，也可以直接运行：

```bash
personal-recorder init-db
```

## Personal Recorder 功能

### 已实现

- SQLite 数据库初始化
- 统一 `events` 模型
- 手动事件记录
- Blackbox SQLite 历史数据迁移
- inbox 实时接入
- Windows Blackbox 实时桥接
- 键盘事件缓冲提交
- 重要事项提取
- 待办和日期提取
- 日报、周报生成
- `.ics` 日历导出
- 敏感信息规则脱敏
- 原始文本与脱敏文本分层存储

### 命令示例

```bash
PYTHONPATH=src python3 -m personal_recorder add-manual \
  --title "今天和客户确认上线计划" \
  --content "周二 15:00 复盘，上线前补测试" \
  --tags work,meeting

PYTHONPATH=src python3 -m personal_recorder import-blackbox-db \
  --db-path /path/to/blackbox.db

PYTHONPATH=src python3 -m personal_recorder push-event \
  --source manual \
  --content "今天确认周报结构，明天补日程同步" \
  --tags important,todo

PYTHONPATH=src python3 -m personal_recorder watch-inbox --once
```

### Windows 实时桥接

如果你在 Windows 上运行原始 Blackbox 采集器，可以直接桥接到新模块：

```bash
PYTHONPATH=src python3 -m personal_recorder bridge-blackbox \
  --blackbox-src D:/Personal-Work-Blackbox/src \
  --keyboard-buffer-timeout 3 \
  --keyboard-buffer-max-length 120
```

当前桥接范围：

- `WindowTracker`
- `ClipboardMonitor`
- `KeyboardHook` 键盘事件缓冲提交
- 手工文本桥接 `emit-blackbox-text`

## 隐私与存储

Personal Recorder 当前已经加入第一版隐私保护：

- `content` 保存原始文本，仅本地保留
- `content_redacted` 保存规则脱敏后的文本
- `content_summary` 默认基于脱敏文本生成
- `storage_tier` 标记为 `private` 或 `restricted`
- 报告和待办提取默认使用脱敏文本

当前会脱敏的内容包括：

- 手机号
- 邮箱
- 银行卡号样式文本
- 身份证号样式文本
- 常见 `token`、`secret`、`password`、`api_key` 键值
- 带敏感查询参数的 URL

## 项目结构

```text
src/
├── main.py
├── collector/
├── processor/
├── storage/
├── ai/
├── ui/
└── personal_recorder/
    ├── bridges/
    ├── collectors/
    ├── config/
    ├── exporters/
    ├── models/
    ├── processors/
    ├── reports/
    ├── repositories/
    └── services/
```

示例数据：

- `examples/sample_events.json`
- `examples/inbox_event.json`

## 原 Blackbox 保留能力

原仓库能力仍然保留：

- Windows 桌面采集
- GUI 与托盘
- 周报/月报生成
- PyInstaller 打包
- 既有测试集

原入口、配置、打包文件均未删除。

## 建议使用方式

如果你只是继续用原 Windows 采集 GUI：

- 继续使用 `src.main`

如果你想把这个仓库升级成个人知识和行为记录器：

- 用 `src.main` 或原采集器采集
- 用 `personal_recorder import-blackbox-db` 迁移历史
- 用 `push-event` / `watch-inbox` 接更多来源
- 用 `build-day` / `build-week` 生成更结构化的日报周报

## 当前边界

当前升级版还没有完成这些部分：

- 更强的敏感应用黑名单联动
- 原始文本单独加密存储
- 项目自动分类训练
- 人工纠偏界面
- 本地模型摘要层

## 兼容说明

- `src.main` 仍是原应用入口
- `personal_recorder` 是并行新增模块，不覆盖原 GUI 工作流
- 新模块默认把数据写到它自己的 `data/` 目录结构中

## 更新日志

### v3.0 (2026-06-07) — Personal Recorder 升级模块接入

新增：

- `src/personal_recorder` 事件化记录模块
- Blackbox SQLite 历史数据迁移
- inbox 实时接入与 watcher
- Windows 实时桥接
- 键盘事件缓冲提交
- 日报、周报、`.ics` 日历导出
- 规则化重要事项与待办提取
- 脱敏文本和原始文本分层存储

保留：

- 原 Blackbox Windows GUI 采集能力
- 原有周报/月报生成链路
- 原有仓库结构和入口

### v2.3 (2026-05-27) — 周报/月报 + 目录整理 + 安全加固

- 周报与月报功能
- 目录整理
- 数据库合并
- 打包与安全加固
=======
> 轻量化个人工作日志自动化采集与 AI 报告工具

基于键盘输入流（Key-stream）+ 窗口上下文（Context）+ 剪贴板（Clipboard）的个人活动记录器，通过 AI（智谱 GLM）自动生成每日工作日报、周报和月报。

## 快速开始

### 方式一：直接运行 EXE（推荐）

1. 进入 `Personal_Work_Blackbox_v2.2/` 目录，双击 `PersonalWorkBlackbox.exe`
2. 首次运行会在 exe 同级目录自动生成 `config/config.yaml`（编辑它配置 API Key）
3. 点击「▶ 启动」开始采集

### 方式二：源码运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 GUI
python -m src.main --gui

# 3. 命令行模式（无 GUI）
python -m src.main --no-tray
```

## 使用说明

1. **启动采集** — 点击「▶ 启动」按钮，程序开始记录键盘输入、窗口切换和剪贴板
2. **生成报告** — 选择报告类型（日报/周报/月报），选择日期，点击「生成报告」调用 AI 生成结构化报告
3. **查看报告** — 点击「查看报告」用默认编辑器打开生成的 Markdown 报告
4. **隐私模式** — 点击「隐私模式」暂停所有记录 30 分钟
5. **快捷键** — `Ctrl+Alt+P` 暂停/恢复，`Ctrl+Alt+R` 生成报告

### 报告类型

| 类型 | 说明 | 文件命名 |
|------|------|----------|
| 日报 | 分析单日活动数据，生成工作日报 | `2026-05-22_091156_report.md` |
| 周报 | 汇总该自然周（周一~周日）的所有日报，生成周报 | `2026-05-19_weekly.md` |
| 月报 | 汇总该自然月的所有日报，生成月报 | `2026-05_monthly.md` |

> **提示**: 周报和月报基于已有的日报汇总生成，请确保对应日期范围内已生成过日报。

## 数据存储

- **数据库**: `data/blackbox.db`（SQLite WAL 模式，6 张表）
- **Markdown 日志**: `data/logs/`
- **运行日志**: `blackbox.log`
- **配置文件**: `config/config.yaml`

## 项目结构

```
src/
├── main.py                  # 主入口（BlackboxEngine）
├── collector/               # 采集层
│   ├── window_tracker.py    #   Win32 窗口追踪 (GetForegroundWindow)
│   ├── keyboard_hook.py     #   pynput 键盘监听
│   ├── idle_detector.py     #   空闲检测 (GetLastInputInfo)
│   └── clipboard_monitor.py #   剪贴板监控 (win32clipboard)
├── processor/               # 处理管道
│   ├── input_buffer.py      #   输入缓冲区状态机（退格处理）
│   ├── privacy_filter.py    #   三层隐私过滤（应用黑名单/内容脱敏/自定义规则）
│   └── session_manager.py   #   会话管理（按应用分组）
├── storage/                 # 存储层
│   ├── database.py          #   SQLite (6 表 + 索引)
│   ├── models.py            #   数据模型（含 PeriodReportRecord）
│   └── markdown_exporter.py #   Markdown 日志导出
├── ai/                      # AI 摘要层
│   ├── prompt_engine.py     #   Prompt 模板引擎（日报/周报/月报）
│   ├── llm_client.py        #   统一 LLM 客户端 (Ollama/GLM/DeepSeek/OpenAI + 自动降级)
│   └── report_generator.py  #   日报/周报/月报生成
├── ui/                      # 交互层
│   ├── gui.py               #   tkinter GUI 操作面板
│   ├── system_tray.py       #   系统托盘
│   ├── hotkey_manager.py    #   全局快捷键
│   └── notification.py      #   Windows Toast 通知
└── config/
    ├── settings.py          #   YAML 配置加载
    └── defaults.py          #   默认配置常量
```

## 技术栈

- **语言**: Python 3.11+
- **窗口追踪**: Win32 API (pywin32)
- **键盘监听**: `pynput` (WH_KEYBOARD_LL)
- **剪贴板**: `win32clipboard` (pywin32)
- **存储**: SQLite (WAL 模式)
- **AI**: 智谱 GLM-4.5-flash（默认），支持 Ollama/DeepSeek/OpenAI
- **GUI**: tkinter（内置，无额外依赖）
- **打包**: PyInstaller 6.x

## 配置

编辑 `config/config.yaml`，主要配置项：

- `ai.glm.model` — AI 模型（glm-4-flash / glm-4.5-flash / glm-4.7）
- `ai.glm.api_key` — 智谱 API Key
- `collection.keyboard_enabled` — 键盘记录开关
- `collection.clipboard_enabled` — 剪贴板监控开关
- `privacy.app_blacklist` — 应用黑名单（密码管理器等）
- `privacy.title_filter_keywords` — 窗口标题过滤关键词

## 打包

```bash
pip install pyinstaller
pyinstaller blackbox.spec --clean --noconfirm
# 产物在 dist/PersonalWorkBlackbox.exe
```

## 测试

```bash
python -m pytest tests/ -v    # 164 个测试
```

## 常见问题

### 启动后闪退

1. **杀毒软件拦截** — pynput 使用底层键盘钩子，可能被杀软误报。将 `python.exe` 和本程序加入杀软白名单
2. **从 cmd 运行排查** — 打开 cmd，运行 `python -m src.main --gui`，观察错误信息
3. **缺少依赖** — 运行 `pip install -r requirements.txt`

### 打包后 EXE 闪退

1. 检查 exe 同级目录下是否自动生成了 `config/config.yaml`
2. 查看 `blackbox.log` 日志文件
3. 用 cmd 运行 exe 观察输出：`.\PersonalWorkBlackbox.exe`

## 更新日志

### v2.3 (2026-05-27) — 周报/月报 + 目录整理 + 安全加固

**新功能：**
- 周报生成：汇总自然周（周一~周日）内所有日报，AI 自动生成结构化周报
- 月报生成：汇总自然月内所有日报，AI 自动生成结构化月报（含按周分布、效率趋势）
- GUI 报告类型选择器：日报/周报/月报下拉切换，日期选择器自动适配周期
- `period_reports` 数据库表：独立存储周期报告，同一周期覆盖旧版
- 跨日应用统计 `query_app_usage_stats_range()`：周报/月报包含真实跨日使用数据
- 缺失日报标注：周报/月报中自动标注缺少日报的日期，不阻断生成

**改进：**
- 周报 Prompt 从占位文本升级为填充真实跨日应用统计数据
- 自定义模板目录 `config/prompts/` 新增 `monthly_report.yaml` 支持
- 目录结构整理：文档归 `docs/`，日志归 `data/logs/`，v2.2 精简为纯 exe 运行目录
- 数据库合并：两个数据库（根目录 + v2.2）合并为单一完整库（5/14~5/26，7 份日报）
- `.gitignore` 安全加固：排除 exe、数据库、API key、个人日志等敏感文件
- v2.2 exe 重新打包（含新功能），同步数据库和文档

**测试：** 新增 22 个测试用例，总计 164 个全量通过无回归

---

### v2.2 (2026-05-19)
- **新增**: 4 个数据库查询/统计测试（总计 140 个测试全通过）
- **改进**: 实际使用测试完成，AI 日报生成流程验证通过
- **改进**: 项目初始化 Git 版本控制

### v2.1 (2026-05-14)
- **修复**: 剪贴板监控在 64 位 Python 上的段错误（ctypes 指针截断 → 改用 win32clipboard）
- **修复**: GUI 启动异常未捕获导致闪退
- **修复**: 启动脚本缺少错误提示（添加 pause）
- **修复**: PyInstaller 打包配置错误排除 tkinter
- **改进**: PyInstaller 打包后自动生成默认配置文件
- **改进**: 所有路径引用兼容 frozen exe 模式
- **改进**: 启动脚本添加依赖检查和错误提示
>>>>>>> origin/main
