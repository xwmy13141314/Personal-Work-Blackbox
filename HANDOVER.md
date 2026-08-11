# HANDOVER — 职迹 WorkTrace 当前快照

> 新会话第一步：读本文件。当前快照，每次收尾覆盖更新，不堆历史。

## 1. 项目是什么
职迹 WorkTrace：纯本地、隐私优先的个人 AI 工作日志工具。三层采集（键盘含中文 IME + 窗口切换 + 剪贴板）→ 隐私过滤 → LLM 日报/周报/月报 + 待办闭环 + 报告可视化 + 导出。工作目录（唯一主线）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`。

## 2. 当前任务
**v4.3 待办看板增强全部完成并实测**（P1 三列看板 / P2 进度+AI建议 / P3 融合实况+逾期顺延+toast / P4-A 数据导入导出 / P4-B 多维视图）。**双库问题已根治**（2026-08-11）：exe 与 python 现在共用项目根唯一库。exe 已重打包（智能检测版 get_app_root，含 v4.3 全部功能）。等用户最终验证。

## 3. 已完成进展

**双库根治（2026-08-11，本会话核心）：**
- [x] 根因：`get_app_root()`（main.py L18-33）对 exe（frozen→`sys.executable`.parent=`dist/`）和 python（→项目根）返回不同路径 → `_app_root` 不同 → db_path 分叉（exe 用 dist/data，python 用项目根/data）
- [x] 修复：`get_app_root` 改为**智能检测**——exe 启动时检测 `exe.parent.parent/src` 是否存在：存在=开发者场景（exe 在项目内 dist/）→ 返回项目根；不存在=外部用户场景（exe 单独分发）→ 返回 exe 旁。开发者 exe 与 python 共用项目根库，外部用户场景不破坏
- [x] 移除 `_migrate_legacy_data` 过渡函数（双库期产物，根治后恒等 return）+ 其调用
- [x] `system_tray.py` / `gui.py` 的 `Path("./data")`（相对 cwd）→ `get_app_root()/"data"`（延迟 import 避免循环导入）
- [x] 数据：项目根 `data/blackbox.db` 为权威完整库（11140 sessions/43 日报/7 待办，最新 8-11 18:20）；dist 旧库（11032，滞后）归档至 `data/backup_双库根治归档_20260811/` 后删除
- [x] config：项目根 `config/config.yaml` 为最新（glm-4.5-flash）；dist 旧 config（glm-4-flash）归档后删除
- [x] exe 重打包（智能检测版，2026-08-11 18:36），验证：日志确认 `数据库已初始化: ...项目根/data/blackbox.db`，dist/ 不再产生 data/
- [x] 353 passed 无回归

**v4.3 待办看板（§4.1-4.10）：**
- [x] **P1** 三列看板（@dnd-kit 拖拽）+ sort_order + 来源下钻 + 4 统计卡片
- [x] **P2** 进度（progress + 100%↔done 联动，clamp [0,100]）/ **P2-C** AI 推进建议（start/progress/stall，日报后自动触发，todo_advices 去重）
- [x] **P3-A** 融合工作实况（MiniDonut 纯 SVG + category_stats）/ **P3-B** 逾期顺延（红色提示条 + 批量顺延）/ **P3-C** toast 提醒（todo_notify_log 去重 + 后台线程每小时 + send_toast）
- [x] **P4-A** 数据导入导出（`export_todos_json`/`import_todos_json`，后端 + pywebview 接口保留；前端按用户要求只留 CSV 导出，去掉备份/导入按钮）
- [x] **P4-B** 多维视图（status 三列可拖 / source 四列只读，看板上方 segmented 切换器）

**v4.2.0 报告可视化 + 导出（更早）：** 报告 HTML 导出（macOS 卡片化 + 时间分布环形图 SVG）+ 待办 CSV 导出

## 4. 下一步计划
**✅ v4.3 全部完成；双库根治完成；exe 已重打包（智能检测版，2026-08-11 18:36）。**

1. 用户最终验证 exe（数据完整性 11140 sessions / 43 日报 / 7 待办；P3/P4 功能；双库已合一）
2. **排序口径决策**（仍待用户定）：列内现用 sort_order 主序，偏离 PRD §4.4 优先级优先
3. ⚠️ **安全遗留**：旧 `settings.jpg` 的 `sk-` 片段仍残留 git 历史（`c3690f3` 及之前）；最有效修复 = 去智谱控制台轮换 key
4. 第三期规划项（`docs/PRD_WorkTrace_v4.md` §2）：跨平台 macOS / 浏览器扩展 / IDE 插件 / 自动更新 / i18n —— 均未实施

## 5. 关键文件 & 环境
- 技术栈：Python 3.13（ctypes WH_KEYBOARD_LL / pywebview 6.2.1 / pywin32）+ React18/TS/Tailwind4/Vite6 + SQLite(WAL) + OpenAI 兼容 LLM（默认智谱 GLM，降级链 ollama→glm→deepseek→openai）
- 工作目录（唯一主线）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`
- 运行：`python -m src.main`（Web GUI 默认）；打包：`pyinstaller --noconfirm blackbox.spec` → `dist/WorkTrace.exe`
- 前端：`cd 界面优化/优化图设计为macOS风格 && npm run dev`（dev）/ `npm run build:desktop`（→ `web_frontend/`）
- **数据库（唯一）：`data/blackbox.db`**（exe 与 python 共用，项目根；11140 sessions）
- 导出 `data/exports/`；日志 `data/logs/`；归档 `data/backup_*/`
- 测试：`python -m pytest -q`（**353 passed**）

## 6. 已知的坑 & 注意事项
- **✅ 双库问题已根治**：`get_app_root`（main.py L18-33）智能检测——开发者 exe（dist/，上级有 src/）→ 项目根；外部用户 exe（单独分发）→ exe 旁；python → 项目根。开发者场景三者统一到项目根库。旧双库（dist/data vs 项目根/data）已合并，归档 `data/backup_双库根治归档_20260811/`
- **别用 pynput**：打包 exe 静默回退 _dummy；v4.1 换 ctypes WH_KEYBOARD_LL
- **别用 ECharts 做报告图**：PDF 走 window.print()，JS 渲染打印丢图；用纯 SVG
- **LLM 纯文本输出**：结构化提取一律「prompt 要求 JSON + 后端容错解析」，别依赖 response_format
- **Windows 中文路径下 node fs 删除静默失败**：删中文路径一律用 PowerShell / bash `rm`，别用 node fs
- **打包前先关运行中的 WorkTrace.exe**：否则 WinError 5 拒绝访问
- **windowed exe 下控制台子进程必须加 CREATE_NO_WINDOW**
- 新 DB 表走 SCHEMA_SQL，新字段走 _migrate_schema（ADD COLUMN）；长时 LLM 操作用 task_id + 轮询（web_api `_tasks`）
- **公开仓库（GitHub）勿含真实数据 / API key**：`data/` 已 gitignore
- **看板列内排序 = sort_order 主序**（非 PRD §4.4 优先级优先）
- **progress ↔ status 联动**（P2）：`web_api.update_todo` 仅显式传 progress 时触发；纯拖拽改 status 不动 progress
- **AI 推进建议只建议不改**（P2-C）：建议入 `todo_advices` pending；「采纳」才改待办 + 标 applied
- **多维视图**（P4-B）：viewMode status（三列可拖）/ source（四列只读：手动/日报/周报/月报）；切换器在看板上方 segmented control

## 7. 如何续上
1. 读本文件 + `CLAUDE.md` + `docs/PRD_待办看板_v4.3.md`（P1-P4 全实现，双库已根治）
2. `python -m pytest -q` 确认 **353 passed** 基线
3. **当前状态**：双库根治完成 + exe 重打包（智能检测版，18:36）+ 应用可起；数据库统一为项目根 `data/blackbox.db`（11140 sessions）
4. 起 app：`python -m src.main` 或双击 `dist/WorkTrace.exe`（**两者现在同一库**）
5. 重打包：关 WorkTrace.exe → `cd 界面优化/优化图设计为macOS风格 && npm run build:desktop` → `cd ../.. && pyinstaller --noconfirm blackbox.spec`
