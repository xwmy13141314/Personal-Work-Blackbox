# 职迹 WorkTrace macOS 版 — AI 项目上下文

> 本文件记录**稳定的项目事实与约定**。当前任务进度、近期变更见 `HANDOVER.md`（每次会话先读它）。

## 项目概述
职迹 WorkTrace macOS 版 — 隐私优先的个人 AI 工作日志工具的 Mac 移植。由 Windows 版 v4.3 迁移：采集层用 macOS 原生 API 重写，核心处理/存储/AI/前端全部复用。三层采集（键盘 + 窗口 + 剪贴板）→ 隐私过滤 → LLM 日报/周报/月报 + 待办闭环 + 报告可视化 + 导出。纯本地运行，数据只存本机。

## 与 Windows 版的关系
- **独立项目目录**：`E:\工作\AI CLOUDE\职迹\mac版本\`（与 Windows 版「轻量化键盘记录工具」平级，核心代码复制独立演进）
- **复用**：storage / ai / processor / ui(web_api,rest_api,web_ui) / config / 前端 React / 测试 —— 全部从 Windows v4.3 复制
- **重写**：collector 四模块 + notification + system_tray 小改 + main.get_app_root 适配

## 关键技术决策（macOS）
- **键盘捕获**：Quartz CGEventTap（kCGSessionEventTap + ListenOnly），专用线程 + CFRunLoop。需辅助功能权限，未授权 CGEventTapCreate 返回 None
- **KeyEvent 兼容**：完整复用 Windows 版 KeyEvent/KeyEventType 类（含 pynput Key 枚举），确保 InputBuffer 零改动；Mac keycode→pynput Key 硬编码映射 + CGEventKeyboardGetUnicodeString 取字符
- **窗口追踪**：AppKit NSWorkspace.sharedWorkspace().frontmostApplication（.localizedName/.bundleIdentifier/.processIdentifier）；窗口标题用 AXUIElement（kAXFocusedWindowAttribute → kAXTitleAttribute）
- **空闲检测**：CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType)，无需权限
- **剪贴板**：NSPasteboard.generalPasteboard().changeCount 轮询（比 Windows 逐字节对比更高效）
- **通知**：osascript `display notification`（无需授权，最稳；替代 NSUserNotificationCenter/UNUserNotificationCenter）
- **全局热键**：复用 pynput GlobalHotKeys（Mac Quartz 后端，需辅助功能权限）
- **托盘/GUI**：pystray + pywebview 跨平台，复用；system_tray 的 `explorer`→`open`，web_api.reveal_path 的 `explorer /select`→`open -R`
- **get_app_root**：源码运行返回项目根；frozen(.app) 返回 .app 同级目录（.app 内只读）
- **图表方案**：纯 SVG 环形图（沿用 Windows 版，不用 ECharts）
- **LLM 结构化输出**：纯文本 + prompt 要求 JSON + 后端容错解析（不依赖 response_format）
- **存储**：SQLite WAL + 每日 Markdown 导出；可选 SQLCipher 加密

## 中文 IME 策略（首版）
首版仅捕获按键流，**不处理 IME 最终文本**。中文输入时记录拼音字母。`is_ime_composition` 通道已预留，后续 P5 通过 AXUIElement 监听前台文本变化补充。

## 运行
```bash
pip3 install -r requirements-mac.txt
export GLM_API_KEY="你的密钥"      # 推荐，避免明文落盘
python3 -m src.main                 # Web GUI（默认）
python3 -m src.main --no-tray       # 命令行模式
```
或双击 `启动.command`（需 `chmod +x`）。

**权限**：首次启动需在「系统设置 > 隐私与安全性 > 辅助功能」授权运行终端/Python/.app。

## 测试
`python3 -m pytest -q`（测试从 Windows 版复制，部分平台相关测试可能需适配）。

## 目录结构
```
src/                  # 后端
  collector/          # keyboard_hook(CGEventTap) / window_tracker(NSWorkspace) / idle_detector(CGEventSource) / clipboard_monitor(NSPasteboard)
  processor/          # input_buffer / privacy_filter / session_manager / app_classifier(含Mac规则) / focus_mode / pinyin_converter
  storage/            # database / models / data_exporter / report_exporter / markdown_exporter
  ai/                 # llm_client / prompt_engine / report_generator / todo_extractor / timedist_extractor
  ui/                 # web_ui / web_api / rest_api / notification(osascript) / system_tray / hotkey_manager / gui(tk回退)
  config/             # settings / defaults
  personal_recorder/  # 事件化记录器（含 macos_snapshot，可借鉴）
界面优化/优化图设计为macOS风格/  # React 前端源码
web_frontend/         # 前端构建产物
config/               # config.yaml（黑名单为 Mac 应用名）
data/                 # blackbox.db + logs/ + exports/
docs/  tests/
requirements-mac.txt  # Mac 依赖（pyobjc-framework-Quartz/AppKit/ApplicationServices）
启动.command           # Mac 双击启动脚本
```

## 重要约定（务必遵守）
- **唯一工作目录**：`E:\工作\AI CLOUDE\职迹\mac版本\`（Mac 版主线，独立于 Windows 版）
- **会话交接**：收尾更新 `HANDOVER.md`；新会话先读 HANDOVER.md
- **别用 ECharts 做报告图**：纯 SVG（PDF 走 window.print()）
- **LLM 纯文本输出**：结构化提取「prompt 要求 JSON + 后端容错解析」
- **KeyEvent 接口不可变**：InputBuffer 依赖 event.char/is_enter/is_backspace/is_ctrl_a/is_arrow/is_ime_composition 等，Mac 实现必须保持
- 新 DB 表走 SCHEMA_SQL，新字段走 _migrate_schema（ADD COLUMN）；长时 LLM 操作用 task_id + 轮询
- 单文件 HTML 偏好：内联 CSS/JS，转义 `</script>`
- 文档/注释/commit 全用中文
- **Mac 权限**：键盘+窗口标题需辅助功能；剪贴板/空闲/通知无需
- **Mac 打包**：.app 内只读，数据放 .app 同级（后续可优化 ~/Library/Application Support）
