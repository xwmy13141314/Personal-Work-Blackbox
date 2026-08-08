# HANDOVER — 职迹 WorkTrace 当前快照

> 新会话第一步：读本文件。当前快照，每次收尾覆盖更新，不堆历史。

## 1. 项目是什么
职迹 WorkTrace：纯本地、隐私优先的个人 AI 工作日志工具。三层采集（键盘含中文 IME + 窗口切换 + 剪贴板）→ 隐私过滤 → LLM 日报/周报/月报 + 待办闭环 + 报告可视化 + 导出。工作目录（唯一主线，v4.2.0，git main）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`。

## 2. 当前任务
v4.2.0（报告可视化 + 导出）已完成并提交；待办闭环（v4.1.x）已完成。上轮收尾：文档更新到 v4.2、资料合并（docs 子目录 6→3）、旧版 v3.1 主目录清理（已删，零损失，数据 zip 备份）、两 HANDOVER 合并。本会话：完成「- 副本」改名收尾——目录已去后缀，残留路径引用（项目 CLAUDE.md / 本文件 / 全局记忆 worktrace / 全局 CLAUDE.md 项目索引）已同步。下一步待用户定。

## 3. 已完成进展

**v4.2.0 报告可视化 + 导出：**
- [x] 报告导出 HTML（macOS 卡片化 + 时间分布环形图 SVG）— `src/storage/report_exporter.py`
- [x] 待办 CSV 导出（UTF-8 BOM，Excel 兼容）— `src/storage/data_exporter.py: export_todos_csv`
- [x] 时间分布环形图（LLM 提取 + 纯 SVG，导出与 app 内共用）— `src/ai/timedist_extractor.py` + `render_donut_svg`
- [x] app 内报告页环形图 + 导出按钮 — `界面优化/优化图设计为macOS风格/src/app/App.tsx`
- [x] 桥接 `analyze_report`（task 轮询）/ 增强 `export_report` — `src/ui/web_api.py`
- [x] `tests/test_export.py` +18 测试

**待办闭环（v4.1.x）：**
- [x] `src/storage/models.py` TodoRecord + `src/storage/database.py` todos 表 + CRUD
- [x] `src/ai/todo_extractor.py`（新建，容错 JSON 解析）+ `prompt_engine` 待办提取 prompt
- [x] `src/main.py: extract_todos_from_report`（报告→提取→入草稿）
- [x] `src/ui/web_api.py` 7 个待办桥接 API
- [x] 前端 `TodoView.tsx`（新建）+ Sidebar/utils/pywebview 接入
- [x] `tests/test_todo.py` 26 测试

**测试基线：** 292 passed（实测；CHANGELOG/README 记 291 为 v4.2.0 发布时口径，未改）

**文档与资料整理：**
- [x] CHANGELOG/README/PRD_v4/使用说明 补 v4.2.0；CLAUDE.md 重写为 v4.2；本 HANDOVER
- [x] docs/ 归整：分析报告（市场分析+优化报告）入 `docs/归档/`，品牌与图标独立保留，personal_recorder 示例回归 `src/personal_recorder/`；顶层子目录 6→3
- [x] 删除旧版主目录（v3.1 旧快照，data 已 zip 备份至 `职迹\轻量化键盘记录工具_v3.1旧版_数据备份_20260808.zip`，零损失）

## 4. 下一步计划
1. ~~文件夹改名~~ **已完成（2026-08-08）**：目录已从「轻量化键盘记录工具 - 副本」改名为「轻量化键盘记录工具」；残留路径引用（项目 CLAUDE.md / 本文件 §1§5 / 全局记忆 worktrace / 全局 CLAUDE.md 项目索引）已同步。
2. 数据备份 `职迹\轻量化键盘记录工具_v3.1旧版_数据备份_20260808.zip`（7.6 MB）：确认 v4.2.0 运行正常后可删
3. 第三期规划项（见 `docs/PRD_WorkTrace_v4.md` §2）：跨平台 macOS / 浏览器扩展 / IDE 插件 / 自动更新 / i18n —— 均未实施
4. 既有 bug：sessions 表缺 category 列（分类/时间分布统计走 LLM 提取绕开）；前端 production build rollup 崩溃（`rm -rf node_modules && npm install` 重装可修）
5. 可选优化：周/月报时间分布（当前仅日报验证过）

## 5. 关键文件 & 环境
- 技术栈：Python 3.13（ctypes WH_KEYBOARD_LL / pywebview / pywin32）+ React18/TS/Tailwind4/Vite6 + SQLite(WAL) + OpenAI 兼容 LLM（默认智谱 GLM，降级链 ollama→glm→deepseek→openai）
- 工作目录（唯一主线，v4.2.0）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`
- 运行：`python -m src.main`（Web GUI 默认）；打包：`pyinstaller --noconfirm blackbox.spec` → `dist/WorkTrace.exe`
- 前端：`cd 界面优化/优化图设计为macOS风格 && npm run dev`（dev）/ `npm run build:desktop`（→ `web_frontend/`）
- 数据：`data/blackbox.db`（sessions/text_segments/clipboard_records/window_events/daily_reports/period_reports/todos）；导出 `data/exports/`
- 测试：`python -m pytest -q`（292 passed）
- 前端别名 `@/`→`src/`；前端项目未装 typescript 依赖，靠 vite/esbuild 转译，无独立 tsc 类型检查

## 6. 已知的坑 & 注意事项
- **别用 pynput**：打包 exe 静默回退 _dummy 后端；v4.1 已换 ctypes WH_KEYBOARD_LL + 专用线程
- **别用 ECharts 做报告图**：PDF 走 window.print()，JS 渲染打印会丢图；用纯 SVG
- **DB 无 category 列**：sessions 表缺该列，分类统计/时间分布不能走 DB，用 LLM 从报告提取
- **LLM 纯文本输出**：结构化提取用「prompt 要求 JSON + 后端容错解析」，别依赖 response_format
- **production build 崩溃（既有，与功能无关）**：rollup 阶段 exit 9/127，`rm -rf node_modules && npm install` 重装可修；vite transform 全过 = 代码正确
- **IDE 别名误报**：cwd 不在前端项目根时，TS 语言服务器对 `@/` 报假阳性，以 vite build 为准
- **打包前**先关运行中的 WorkTrace.exe（Windows 文件锁）
- 新 DB 表走 `SCHEMA_SQL`，新字段走 `_migrate_schema`（ADD COLUMN）；长时 LLM 操作用 task_id + 轮询（见 web_api `_tasks`）
- 项目 CLAUDE.md 曾停 v2.3 严重过时，已重写；以本 HANDOVER + 代码为准

## 7. 如何续上
1. 读本文件 + `CLAUDE.md`
2. `python -m pytest -q` 确认 292 passed 基线
3. 看 `docs/PRD_WorkTrace_v4.md` §2 第三期规划，按优先级选一项开干
4. 改前端先 `cd 界面优化/优化图设计为macOS风格 && npm run dev` 起 dev server
