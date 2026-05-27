# Personal Work Blackbox

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

### v2.3 (2026-05-27)
- **新增**: 周报生成功能 — 汇总自然周（周一~周日）内所有日报，AI 生成周报
- **新增**: 月报生成功能 — 汇总自然月内所有日报，AI 生成月报
- **新增**: GUI 报告类型选择器（日报/周报/月报下拉切换）
- **新增**: `period_reports` 数据库表，持久化周报/月报
- **新增**: 跨日期范围应用使用统计 `query_app_usage_stats_range()`
- **改进**: 周报 Prompt 填充真实跨日统计数据（原为占位文本）
- **改进**: 自定义模板支持 `monthly_report.yaml`
- **测试**: 新增 18 个测试用例（总计 164 个）

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
