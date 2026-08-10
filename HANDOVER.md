# HANDOVER — 职迹 WorkTrace 当前快照

> 新会话第一步：读本文件。当前快照，每次收尾覆盖更新，不堆历史。

## 1. 项目是什么
职迹 WorkTrace：纯本地、隐私优先的个人 AI 工作日志工具。三层采集（键盘含中文 IME + 窗口切换 + 剪贴板）→ 隐私过滤 → LLM 日报/周报/月报 + 待办闭环 + 报告可视化 + 导出。工作目录（唯一主线，v4.2.0，git main）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`。

## 2. 当前任务
v4.2.0 全交付（报告可视化 + 导出 / 待办闭环 / windowed exe / 关于页 / GitHub README 截图，见 §3）。**本会话（2026-08-10）**：报告「时间分布环形图」数据源切换——从「LLM 从报告文本提取」改为「**DB 分类统计优先 + LLM 降级**」。探索发现 category DB 基础设施早已完整（sessions.category 列 / 写入时分类 / `query_category_stats` / `backfill_categories` 全在），但环形图没接上、仍走 LLM（`get_category_stats` 前端 bridge 定义了却无组件调用）。本次接线：新增纯函数 `category_stats_to_timedist`（`timedist_extractor.py`）+ 改 `extract_timedist_from_report`（`main.py`）DB 优先、无数据降级 LLM；报告页环形图与导出 HTML 自动受益，**无报告也能出图**。测试 298 passed（+6）。**同会话后续**：① 修草稿区来源显示 bug（`TodoView.tsx:373` 写死「日报」且无日期 → 动态 `sourceMeta(drafts[0]).label`，周报/月报也正确）；② 规划「待办看板增强 v4.3」——与 AI+采集融合的「任务镜像」（非独立通用看板），完整 PRD 落 `docs/PRD_待办看板_v4.3.md`，分 P1-P4。**用户已审 PRD 基本通过**，并增补「任务统计总览」（看板顶部 4 指标：总任务 / 今日待办 / 已延期 / 已完成）纳入 **P1**，口径已对齐（**今日待办=未逾期未完成；已延期=逾期未完成**，两者互斥）。**下一步**：实现 P1（看板视图 + 拖拽 + 来源下钻 + 统计总览），见 PRD §7；另用户可起 app 验证环形图 + 决定是否轮换 key（§4.0）。

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

**测试基线：** 298 passed（v4.2.0 发布时 291，CHANGELOG/README 仍记 291 为发布口径未改；本会话 +6 时间分布 DB 单测）

**文档与资料整理：**
- [x] CHANGELOG/README/PRD_v4/使用说明 补 v4.2.0；CLAUDE.md 重写为 v4.2；本 HANDOVER
- [x] docs/ 归整：分析报告（市场分析+优化报告）入 `docs/归档/`，品牌与图标独立保留，personal_recorder 示例回归 `src/personal_recorder/`；顶层子目录 6→3
- [x] 删除旧版主目录（v3.1 旧快照，data 已 zip 备份至 `职迹\轻量化键盘记录工具_v3.1旧版_数据备份_20260808.zip`，零损失）

**打包 + windowed（2026-08-08）：**
- [x] 修复 toast 弹终端元凶：`src/ui/notification.py` 调 PowerShell 发通知缺 `CREATE_NO_WINDOW`，windowed exe 每次闪黑窗；已加 `creationflags=_CREATE_NO_WINDOW`
- [x] 打包 v4.2.0 windowed exe：`dist/WorkTrace.exe`（32MB onefile，后端+前端全内嵌，`console=False` + runw.exe bootloader）
- [x] warn 检查：203 个 missing 全无害（.NET 动态命名空间 / 跨平台可选后端 / 静态分析误报）

**关于页修正（2026-08-08）：**
- [x] 邮箱 `xwmy134@gmail.com` → `xwmy1314@gmail.com`（关于页显示 + mailto 链接）
- [x] 全项目版本号同步 4.2.0：前端 `APP_VERSION`（`AboutView.tsx`）4.0.0→4.2.0、后端 `_APP_VERSION`（`web_api.py` /ping 返回）4.1.0→4.2.0；已排查 `src/` + 前端 `src/` + `config/` + `blackbox.spec` 确认无其他过时版本号
- [x] exe 已重打包（31.5MB）— commit `886716d`

**GitHub README 截图更新（2026-08-08）：**
- [x] README「界面预览」换 v4.2.0 实拍图廊：活动明细 / 待办跟进 / 关于（用户确认真实工作数据可公开）+ 时间分布环形图（`render_donut_svg` demo 数据 SVG，零敏感）
- [x] 五视图→六视图（补待办视图）；左栏导航列表与特性描述同步修正
- [x] 删除旧 `docs/screenshots/settings.jpg`（泄露 `sk-` 前缀）与过时 `overview.jpg`
- [x] 推送 main（commit `0b99918`，公开生效，已线上验证）；`data/` 全程 gitignore，7 张源截图未进仓库

**时间分布环形图 DB 优先（本会话 2026-08-10）：**
- [x] 新增纯函数 `category_stats_to_timedist`（`src/ai/timedist_extractor.py`）：`query_category_stats` 的 active_seconds → `{category,minutes,percent}`，过滤 0、归一百分、minutes 至少 1
- [x] 改 `extract_timedist_from_report`（`src/main.py`）为 **DB 优先 + LLM 降级**：新增 `_timedist_from_db` 辅助（复用 `_week_range`/`_month_range` + `query_category_stats`），DB 有数据返回 `source:db`，无数据降级原 LLM 链路返回 `source:llm`；DB 提取前置（无报告也能出图）
- [x] `tests/test_export.py` +6 纯函数单测（`TestDbTimedist`）；未改 database.py（`query_category_stats` 已就绪）/ 前端（接口契约不变）/ web_api.py

**待办看板增强规划 + 草稿区修复（本会话 2026-08-10 后续）：**
- [x] 草稿区来源显示 bug 修复（`TodoView.tsx:373`）：原写死「日报」且无日期 → 动态显示「日报/周报/月报 + MM/DD」，周报/月报提取不再误显「日报」
- [x] 新增 `docs/PRD_待办看板_v4.3.md`：待办看板增强完整 PRD（融合 AI+采集，非独立看板），核心理念=任务镜像，分 P1-P4，P1 详写范围+验收
- [x] PRD 定稿调整（用户审查后）：① 任务统计总览（§4.7）从 P3 提前纳入 P1（4 指标：总任务/今日待办/已延期/已完成），口径=今日待办(未逾期未完成)/已延期(逾期未完成)，互斥；② P3 改为「在 P1 统计基础上叠加工作实况」；③ 修正项目 `CLAUDE.md` 过时条目「时间分布数据源」（原误记 sessions 无 category 列 → 已改 DB 优先+LLM 降级）

## 4. 下一步计划
**📌 当前最高优先级**：待办看板增强 v4.3 P1（见 `docs/PRD_待办看板_v4.3.md` §7）—— AI 驱动状态看板（看板视图 + 拖拽 + 来源下钻），todos 加 `sort_order` 字段。

0. ⚠️ **安全遗留**：旧 `settings.jpg` 的 `sk-` 片段仍残留在 git 历史（`c3690f3` 及之前）。最有效修复 = 去智谱控制台轮换该 API key（让历史泄露的 key 失效）；清理 git 历史（BFG / filter-repo）会重写提交 + 影响 v4.2.0 release tag，须用户确认才动
1. ~~文件夹改名~~ **已完成（2026-08-08）**：目录已从「轻量化键盘记录工具 - 副本」改名为「轻量化键盘记录工具」；残留路径引用（项目 CLAUDE.md / 本文件 §1§5 / 全局记忆 worktrace / 全局 CLAUDE.md 项目索引）已同步。
2. 数据备份 `职迹\轻量化键盘记录工具_v3.1旧版_数据备份_20260808.zip`（7.6 MB）：确认 v4.2.0 运行正常后可删
3. 第三期规划项（见 `docs/PRD_WorkTrace_v4.md` §2）：跨平台 macOS / 浏览器扩展 / IDE 插件 / 自动更新 / i18n —— 均未实施
4. ~~既有 bug：sessions 表缺 category 列（时间分布走 LLM 绕开）~~ **已解决（2026-08-10）**：sessions.category 列本就存在（含迁移），`query_category_stats`/`backfill_categories` 也早实现，缺的只是环形图没接——本次 `extract_timedist_from_report` 改 DB 优先（见 §3），时间分布不再绕 LLM。另：~~前端 production build rollup 崩溃~~ **已修复（2026-08-08）**——vite `emptyOutDir` 中文路径失效，`build:desktop` 已前置 PowerShell `Remove-Item` 清空 `web_frontend`
5. ~~可选优化：周/月报时间分布~~ **已验证可用（2026-08-08）**：链路本就完整（`extract_timedist_from_report` daily/weekly/monthly 三分支齐全，前端 `analyze()` 透传 reportType），weekly 实测端到端通过（2026-05-25 周报 → 4 类别提取 + SVG 渲染正常）；本会话 DB 优先路径同样 daily/weekly/monthly 三分支覆盖（`_timedist_from_db`）
6. 可选后续：前端 `get_category_stats` bridge 仍悬空（无组件调用），可接首页/活动页分类统计图；本次未动（控制范围）

## 5. 关键文件 & 环境
- 技术栈：Python 3.13（ctypes WH_KEYBOARD_LL / pywebview / pywin32）+ React18/TS/Tailwind4/Vite6 + SQLite(WAL) + OpenAI 兼容 LLM（默认智谱 GLM，降级链 ollama→glm→deepseek→openai）
- 工作目录（唯一主线，v4.2.0）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`
- 运行：`python -m src.main`（Web GUI 默认）；打包：`pyinstaller --noconfirm blackbox.spec` → `dist/WorkTrace.exe`
- 前端：`cd 界面优化/优化图设计为macOS风格 && npm run dev`（dev）/ `npm run build:desktop`（→ `web_frontend/`）
- 数据：`data/blackbox.db`（sessions/text_segments/clipboard_records/window_events/daily_reports/period_reports/todos）；导出 `data/exports/`
- 测试：`python -m pytest -q`（298 passed）
- 前端别名 `@/`→`src/`；前端项目未装 typescript 依赖，靠 vite/esbuild 转译，无独立 tsc 类型检查

## 6. 已知的坑 & 注意事项
- **别用 pynput**：打包 exe 静默回退 _dummy 后端；v4.1 已换 ctypes WH_KEYBOARD_LL + 专用线程
- **别用 ECharts 做报告图**：PDF 走 window.print()，JS 渲染打印会丢图；用纯 SVG
- ~~**DB 无 category 列**：sessions 表缺该列，分类统计/时间分布不能走 DB~~ **已解决（2026-08-10）**：sessions.category 列本就存在（含 `_migrate_schema`），时间分布环形图已切 DB 优先（`query_category_stats` → `category_stats_to_timedist`，见 §3），不再绕 LLM；LLM 仅作降级保底
- **LLM 纯文本输出**：结构化提取用「prompt 要求 JSON + 后端容错解析」，别依赖 response_format
- **Windows 中文路径下 node fs 删除静默失败**：node `fs.rmSync` 与 vite `emptyOutDir` 对含中文路径（本项目 `E:\工作\...`）静默失败——不报错、不删除，致 build 产物死文件堆积进 exe。已修：`build:desktop` 前置 PowerShell `Remove-Item`（.NET 原生，对中文路径有效）+ `; exit 0`（不加则 `SilentlyContinue` 使退出码=1，会阻断 `&&` 后的 vite）。**Windows 删中文路径一律用 PowerShell / bash `rm`，别用 node fs**
- **IDE 别名误报**：cwd 不在前端项目根时，TS 语言服务器对 `@/` 报假阳性，以 vite build 为准
- **打包前先关运行中的 WorkTrace.exe**：pyinstaller `--noconfirm` 会 `os.remove` 旧 exe 再写新 exe，若旧 exe 正在运行（含用户验证时双击打开）则 `PermissionError: [WinError 5] 拒绝访问`。先 `Stop-Process` 再打包
- **windowed exe 下控制台子进程必须加 `CREATE_NO_WINDOW`**：`console=False` 只压主进程终端；`subprocess` 调 powershell/cmd 等控制台程序若不加 `creationflags=subprocess.CREATE_NO_WINDOW`，每次都闪黑窗（见 `notification.py`）。GUI 程序（notepad/explorer）无需此标志
- 新 DB 表走 `SCHEMA_SQL`，新字段走 `_migrate_schema`（ADD COLUMN）；长时 LLM 操作用 task_id + 轮询（见 web_api `_tasks`）
- 项目 CLAUDE.md 曾停 v2.3 严重过时，已重写；以本 HANDOVER + 代码为准
- **公开仓库（GitHub）勿含真实数据 / API key**：截图含真实工作内容（日报正文 / 真实文件名 / 待办）或 `sk-` key 一律不上传；`data/` 已 gitignore。本次删除了泄露 `sk-` 的旧 `settings.jpg`（当前版本已清，git 历史残留未清，见 §4）

## 7. 如何续上
1. 读本文件 + `CLAUDE.md`
2. `python -m pytest -q` 确认 298 passed 基线
3. 看 `docs/PRD_WorkTrace_v4.md` §2 第三期规划，按优先级选一项开干
4. 改前端先 `cd 界面优化/优化图设计为macOS风格 && npm run dev` 起 dev server
