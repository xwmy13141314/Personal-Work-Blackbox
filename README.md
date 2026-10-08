# 职迹 WorkTrace（macOS 版）

> 让每一分努力都有迹可循 · 您的私有工作黑盒
> 隐私优先的个人 AI 工作日志 · 本地存储 · 开源可审计

轻量化个人工作日志采集与 AI 报告工具的 **macOS 版本**。由 Windows 版（v4.3）迁移而来，采集层使用 macOS 原生 API 重写，核心处理/存储/AI/前端全部复用。

**纯本地运行（Local Only）· 不联网、不上传、数据只存本机。**

---

## 系统要求

- macOS 12+（Monterey 及以上，推荐 macOS 13/14）
- Python 3.11+（建议 3.12/3.13）
- 需授予「辅助功能」权限（键盘监听 + 窗口标题采集必需）

## 与 Windows 版的关系

| 模块 | 处理方式 |
|------|---------|
| 采集层（键盘/窗口/空闲/剪贴板） | 🔴 macOS 原生重写（Quartz CGEventTap / AppKit NSWorkspace / NSPasteboard / CGEventSource） |
| 通知 | 🔴 重写（osascript display notification） |
| 托盘 / GUI | 🟢 复用（pystray / pywebview 跨平台） |
| 存储 / AI / 处理 / 前端 | 🟢 直接复用（待办看板/导出/可视化/专注模式/REST API 全保留） |
| 打包 | 🟡 后置（py2app 生成 .app，首版先源码运行） |

## 权限要求（重要）

macOS 对输入监控有严格权限控制，首次启动需手动授权：

1. **辅助功能（Accessibility）** — 键盘监听（CGEventTap）+ 窗口标题（AXUIElement）
   - 路径：`系统设置 > 隐私与安全性 > 辅助功能`
   - 将运行本程序的终端 / Python / .app 勾选启用
   - 未授权时：键盘钩子无法安装（CGEventTapCreate 返回 None），窗口标题为空
2. 空闲检测 / 剪贴板 / 通知 — 无需特殊权限

> 授权后需重启程序生效。程序首次启动会在日志中提示权限状态。

## 快速开始

### 源码运行（推荐，首版）

```bash
# 1. 安装依赖
pip3 install -r requirements-mac.txt

# 2. 配置 API Key（推荐环境变量）
export GLM_API_KEY="你的智谱密钥"   # 写入 ~/.zshrc 持久化

# 3. 启动
python3 -m src.main            # Web GUI（默认，pywebview + React）
python3 -m src.main --no-tray  # 命令行模式
```

或双击 `启动.command`（自动检查依赖并启动；首次需 `chmod +x 启动.command`）。

### 配置 API Key

为避免密钥明文落盘，推荐通过环境变量提供（优先级高于 `config.yaml`）。命名规则 `{PROVIDER}_API_KEY`：

```bash
# 写入 ~/.zshrc（zsh 默认）
export GLM_API_KEY="你的真实密钥"
export DEEPSEEK_API_KEY="你的真实密钥"
```

也可在「设置」页 GUI 表单中填写后保存（写入 `config/config.yaml`，重启生效）。

> 支持 OpenAI 兼容协议的任意模型：智谱 GLM / DeepSeek / 通义 / Kimi / OpenAI / Ollama / 自定义。

## 已知限制（首版）

- **中文输入法（IME）**：首版仅捕获按键流，中文输入时记录的是拼音字母。IME 确认后的最终汉字文本将在后续版本通过 AXUIElement 监听补充（`is_ime_composition` 通道已预留）。
- **打包**：首版以源码运行为主，py2app 打包 `.app` 为后续工作。
- **窗口标题**：部分应用未暴露 AX 标题，可能为空（不影响应用名采集）。

## 功能特性（与 Windows v4.3 对齐）

- 三层采集：键盘（含功能键/字符）+ 窗口切换 + 剪贴板
- AI 报告：日报 / 周报 / 月报（Markdown 渲染）
- 待办看板：三列拖拽（@dnd-kit）+ 进度跟踪 + AI 推进建议 + 逾期顺延 + toast 提醒 + 多维视图
- 应用分类：10 类自动分类（含 macOS 独有应用：Xcode/Finder/Pages/Messages 等）
- 专注模式：娱乐应用检测提醒 + 每日效率目标
- 数据导出：活动 CSV/JSON + 待办 CSV
- 报告导出：单文件 HTML（内联 CSS/SVG，可离线/微信直发，Ctrl+P 转 PDF）
- 时间分布可视化：纯 SVG 环形图
- 全文搜索：跨日期检索历史输入
- 隐私保护：首次告知 + 应用黑名单 + 内容脱敏 + 一键隐私模式 + 可选 SQLCipher 加密
- REST API：本地 HTTP 接口（127.0.0.1:19527）

## 配置

`config/config.yaml`（也可在「设置」页 GUI 编辑，保存后重启生效）。应用黑名单使用 macOS 应用名（小写，如 `1password`、`keychain access`）。

## 目录结构

```text
src/
├── main.py              # 主入口 / BlackboxEngine / get_app_root（macOS 适配）
├── collector/           # macOS 原生采集
│   ├── keyboard_hook.py     # Quartz CGEventTap（专用线程 + CFRunLoop）
│   ├── window_tracker.py    # AppKit NSWorkspace + AXUIElement
│   ├── idle_detector.py     # CGEventSourceSecondsSinceLastEventType
│   └── clipboard_monitor.py # NSPasteboard.changeCount 轮询
├── processor/           # 输入缓冲 / 隐私过滤 / 会话管理 / 应用分类（含 Mac 规则）
├── storage/             # SQLite + Markdown 导出 + 报告 HTML 导出
├── ai/                  # LLM 客户端 / 提示词 / 报告生成 / 待办提取
├── ui/                  # web_ui / web_api / rest_api / notification(osascript) / system_tray
└── config/
界面优化/优化图设计为macOS风格/   # React 前端源码（Vite + TS + Tailwind 4）
web_frontend/                    # 前端构建产物
config/  data/  docs/  tests/
```

## 数据

- `data/blackbox.db` — SQLite 主库（sessions / text_segments / clipboard_records / window_events / daily_reports / todos 等）
- `data/logs/` — 每日 Markdown 导出 + AI 报告
- 所有数据仅存本机，不联网上传

## 隐私保护

四层架构：
1. **首次启动告知** — 隐私告知弹窗
2. **应用黑名单** — 密码管理器等应用前台时不记录
3. **内容脱敏** — 身份证 / 银行卡 / 手机号 / 邮箱 / JWT / API Key / IPv4 → `[FILTERED_*]`
4. **隐私模式** — 一键开关，开启期间全部停录

可选 SQLCipher 加密：`pip install sqlcipher3-binary` + 设置 `WORKTRACE_DB_KEY` 环境变量。

## 打包（后续）

```bash
# 1. 构建前端
cd 界面优化/优化图设计为macOS风格
npm install && npm run build:desktop      # 输出到项目根 web_frontend/

# 2. py2app 打包（后续实现）
cd ../..
python3 setup.py py2app                   # 产物：dist/WorkTrace.app
```

## 更新日志

详见 `CHANGELOG.md`（继承自 Windows 版 v4.3，Mac 版迁移记录见 `HANDOVER.md`）。
