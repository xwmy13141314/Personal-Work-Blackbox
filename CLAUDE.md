# 职迹 WorkTrace — AI 项目上下文

> 本文件记录**稳定的项目事实与约定**。当前任务进度、近期变更见 `HANDOVER.md`（每次会话先读它）。

## 项目概述
职迹 WorkTrace — 隐私优先的个人 AI 工作日志工具。三层采集（输入活动 + 窗口上下文 + 剪贴板）→ 隐私过滤 → LLM 生成日报/周报/月报 + 时间分布可视化 + 报告/待办导出。纯本地运行，数据只存本机。当前版本 v4.2.0。

## 关键技术决策
- **键盘捕获**：ctypes 直接调用 Windows API（WH_KEYBOARD_LL）+ 专用线程独立消息泵，**不用 pynput**（打包环境静默回退 _dummy 后端）。v4.1 重构
- **中文 IME**：WH_GETMESSAGE 钩子 + ImmGetCompositionStringW 主动轮询组合结果
- **图表方案**：**纯 SVG 环形图，不用 ECharts**。PDF 走 window.print()，静态 SVG 必显示；单文件 HTML 不内联约 1MB JS；后端一处生成，导出 HTML 与 app 内共用
- **时间分布数据源**：**DB 分类统计优先 + LLM 降级**（`query_category_stats` → `category_stats_to_timedist`，sessions.category 列本就存在；DB 无数据才回退 LLM 从报告文本提取，无报告也能出图）
- **LLM 结构化输出**：纯文本 + "prompt 要求 JSON + 后端容错解析"，**不依赖 response_format**
- **存储**：SQLite WAL + 每日 Markdown 导出；可选 SQLCipher 加密
- **生命周期**：stop() 停采集但留 DB 连接（支持后续报告生成），shutdown() 才完全关闭（仅应用退出时）

## 运行
```bash
python -m src.main            # Web GUI（默认，pywebview + React）
python -m src.main --gui-tk   # tkinter 旧 GUI（回退）
python -m src.main --no-tray  # 命令行模式
```
或双击 `启动.bat` / `dist/WorkTrace.exe`。

API Key 优先用环境变量（`GLM_API_KEY` / `DEEPSEEK_API_KEY` 等），避免明文落盘；未配置时 AI 报告功能不可用。

## 打包
```bash
cd 界面优化/优化图设计为macOS风格 && npm install && npm run build:desktop   # 前端 → web_frontend/
cd ../.. && pyinstaller --noconfirm blackbox.spec                            # → dist/WorkTrace.exe
```
重新打包需先关闭运行中的 WorkTrace.exe（Windows 文件锁）。

## 测试
`python -m pytest -q`，292 passed。导出/可视化测试在 `tests/test_export.py`。

## 目录结构（关键）
```
src/                  # 后端：collector / processor / storage / ai / ui / config
  collector/          # keyboard_hook(ctypes) / window / clipboard / idle
  processor/          # input_buffer / privacy_filter / session_manager / app_classifier / focus_mode
  storage/            # database / models / data_exporter / report_exporter(单文件 HTML+SVG)
  ai/                 # llm_client / prompt_engine / report_generator / todo_extractor / timedist_extractor
  ui/                 # web_ui / web_api / rest_api / notification
界面优化/优化图设计为macOS风格/  # React 前端源码（Vite + TS + Tailwind 4）
web_frontend/         # 前端构建产物（打包输入）
config/               # config.yaml
data/                 # blackbox.db + logs/ + exports/ + backup_历史库_*/（归档永不删）
docs/                 # PRD / 使用说明 / 截图 / 归档
tests/                # pytest
```

## 重要约定（务必遵守）
- **唯一工作目录**：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`（v4.2.0 主线；原「- 副本」已改名去后缀，旧版 v3.1 主目录已删）
- **会话交接**：收尾时更新 `HANDOVER.md`（7 节固定结构，覆盖不堆历史）；新会话第一步读 HANDOVER.md
- **新 DB 表**通过 SCHEMA_SQL；**新字段**通过 `_migrate_schema`（ADD COLUMN）
- 长时 LLM 操作用 task_id + 轮询模式（见 web_api `_tasks`）
- 单文件 HTML 偏好：内联 CSS/JS，转义 `</script>`→`<\/script>`，无外部 src/href
- 文档/注释/commit 全用中文
- **Windows 中文路径删除用 PowerShell / bash `rm`，别用 node fs**：node `fs.rmSync` 与 vite `emptyOutDir` 对 `E:\工作\...` 这类中文路径静默失败（不报错、不删除）；详见 HANDOVER §6
