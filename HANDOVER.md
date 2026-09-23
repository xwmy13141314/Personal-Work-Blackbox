# HANDOVER — 职迹 WorkTrace 当前快照

> 新会话第一步：读本文件。当前快照，每次收尾覆盖更新，不堆历史。

## 1. 项目是什么
职迹 WorkTrace：纯本地、隐私优先的个人 AI 工作日志工具。三层采集（键盘含中文 IME + 窗口切换 + 剪贴板）→ 隐私过滤 → LLM 日报/周报/月报 + 待办闭环 + 报告可视化 + 导出 + 拼音智能识别 + UIA/COM 真实上屏文本采集。工作目录（唯一主线）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`（git 仓库；`.git` 在此，父级 `职迹\` 不是 git 仓库，环境检测报「非 git」时勿被误导）。

## 2. 当前任务
**v5.4.0 已完成并推送 GitHub（2026-09-23）**：把一条并行开发线（v4.3.1 基线上未提交的本地 v4.5.0「洞察速记」）收编进 v5.3.0 主线——速记标签化（tags + 标签云 + 精确筛选）+ 洞察收件箱双写 + Ctrl+Alt+I + Web UI 模式补齐全局快捷键；并修复上游仓库缺陷（拼音 HMM/DAG 词典被 `.gitignore` 的 `data/` 规则误排除，已补回 6 个词典文件 5.9MB）。

**工作区变更（重要）**：本次起仓库根改为 **`D:\AI 学习\AI coding\职迹\`**（GitHub main + 完整历史），`dist/`、`data/`、`web_frontend/`、`_local_source_backup_*/`、`.workbuddy/` 均 gitignored。旧的 `E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\` 为历史工作目录。

**历史背景**：v5.3.0 的 `.git` 曾严重损坏（`objects/pack/*.pack` + `refs/` 缺失），v4.4.0~v5.3.0 提交对象永久丢失，最终以一次 `release(v5.3.0)` squash 提交对齐远程 `95d20bee` 后推送。因此 v4.3.2~v5.2.0 无独立提交历史，内容以 CHANGELOG/PRD 为准。

**并行线遗留说明**：本地 v4.5.0 的独立 `insights` 表、`todo_archiver.py`、前端 `InsightView.tsx` 均为**重复实现，已弃用**（v5.3.0 已分别有 `notes` 速记表、`DataExporter.append_todo_archive`、`QuickNoteView`）。唯一源码副本一度只存在于系统 Temp 目录，已备份至 `_local_source_backup_20260923/`。

## 3. 已完成进展

**本会话（2026-09-23）v5.4.0 速记标签化 + 洞察收件箱双写（测试 524 passed / 0 failed）：**
- [x] 速记标签：`notes` 增加 `tags` 列（含旧库迁移）；标签归一化（中英文逗号、去重）；标签云（次数降序）；按标签精确筛选（逗号包裹匹配）；搜索命中内容 + 标签
- [x] 洞察收件箱双写：`src/storage/insight_capture.py`（`save_to_inbox` / `normalize_tags` / `inbox_status` / `count_inbox_files`）；速记保存时同步落盘 Markdown（frontmatter `type/created/tags/source`，文件名 `YYYY-MM-DD_HHMM.md`，同分钟加序号）
- [x] 收件箱配置面板：目录写入 `config.yaml` 的 `insight.inbox_dir`，**热生效**（写文件 + 更新引擎内存配置 + 重载单例）；显示连通性/可写性/待处理文件数
- [x] 全局快捷键 Ctrl+Alt+I（`hotkey_manager` + `web_ui` 接线 + 前端 `wt:open-note-capture` 事件 → 跳转速记页 + 聚焦输入框）
- [x] **Web UI 模式补齐全局快捷键**：此前 `Ctrl+Alt+P/R/N` 仅在托盘/GUI 模式注册；现 `run_web()` 内统一注册，`_on_closing` 时 `hotkey_manager.stop()`
- [x] 速记页四指标（今日/本周/累计/置顶）+ 卡片标签 chip 可点选筛选
- [x] **修复上游缺陷**：`.gitignore` 的 `data/` 规则误排除 `src/libs/Pinyin2Hanzi/data/*.json.gz` → 新克隆仓库拼音识别退化为单字映射（`test_pinyin_converter.py` 8 个用例失败）。补回 6 个词典文件（5.9MB，vendored letiantian/Pinyin2Hanzi · MIT）+ `.gitignore` 例外规则
- [x] 版本号统一 5.4.0（web_api / AboutView / pyproject）；文档同步（CHANGELOG v5.4.0 / README / PRD 版本+历史 / 使用说明与 + 视图导航 + 快捷键 + 配置项）
- [x] 合并策略：以 GitHub v5.3.0 为基线，只移植本地独有能力；重复实现（insights 表 / todo_archiver / InsightView / 旧 keyboard_hook 清理）全部弃用

**v5.3.0 输入采集准确性（2026-09-15~09-21，已推送，测试基线 504 passed + 8 failed 拼音词典缺失）：**
- [x] C1 数字键选字触发 IME 上屏检查：`_IME_CONFIRM_VKS` 覆盖数字键（主键盘 0x30-0x39 + 小键盘 0x60-0x69），确认键后 35ms 轮询 `ImmGetCompositionStringW` 取上屏结果
- [x] C2 钩子回调减负防丢键：`_kbd_hook_callback` 仅最小解析 `put_nowait` 入队，`_dispatch_loop` 独立线程消费
- [x] C3 残缺拼音不硬转：`pinyin_converter.py` 置信度门控（2 音节 ≥-0.9 / ≥3 音节 ≥-1.0），低置信度转 HMM 仲裁，仍低保留原文
- [x] C4 AI 增强结果前端视觉区分：`ActivityView.tsx` Sparkles 图标 + accent 高亮
- [x] B1 UIA 快照采集：**独立子进程模式**（`uia_worker.py` + `uia_worker_capture.py` 代理；实测主进程 import comtypes 会毁掉 pywebview WebView2 窗口）；Value→Text→MSAA 三路读取；控件基线差分；快照过期 2.5s 回退键盘文本；密码控件跳过；子进程崩溃自动重启（5s 退避）
- [x] B2 后端集成：`main.py` `_on_text_commit` 阶段 `CaptureRouter` 三路仲裁（COM 优先 > UIA > 键盘兜底）入库前替换；`--uia-worker` 参数在 GUI/引擎初始化前分流
- [x] B3 前端展示真实上屏文本；配置项 `accurate_mode` / `uia_capture_enabled` / `com_capture_enabled` / `uia_capture_interval_ms`
- [x] WPS/Office COM 采集（`wps_com.py`）：GetActiveObject 只读绑定（绝不启动新进程），duck typing 判断表格/文档，覆盖 WPS 表格这类 UIA 读不到的控件
- [x] 版本号统一 5.3.0（web_api / AboutView / pyproject）；文档同步（CHANGELOG v5.3.0 / README / PRD 版本+历史 v5.0-v5.3 / 使用说明活动明细章节 / .gitignore 补 `build_20*/`+`dist_20*/`）

**v5.0-v5.2（2026-09-07~09-09，均已开发完成未推送）：**
- v5.2.0 拼音智能识别 2.0：Pinyin2Hanzi 离线分层引擎（DAG→HMM→单字兜底）+ 部分转换策略 + AI 增强（LLM 批量，简拼/混拼还原）；`启动.bat` 等 5 个 bat 转 CRLF（修 LF 闪退）
- v5.1.0 个人工作台 Phase 1：AI 周度洞察（LLM+本地双模式）+ Ctrl+K 全局搜索命令面板
- v5.0.0/v5.0.1：驾驶舱 + 速记 + projects 表 + 全局搜索；exe 重打包修复旧版启动报错

**更早：v4.4.0 待办删除归档（commit `b26a91a2`，未推送）；v4.3.x 安全加固/看板/换肤（已发 Release）。**

## 4. 下一步计划
1. **上传 GitHub**：双击 `git-upload-v5.3.0.bat`（fetch 恢复 → 预览变更 → 提交 `release(v5.3.0)` → push main）
2. **GUI 实测验证**（沙箱限制数据库写入，需手动）：双击 `启动.bat` → 记事本/浏览器输入中文查上屏文本、WPS 表格查 COM 捕获、活动页「智能识别」+「AI 增强」查 Sparkles 高亮
3. **【可选】发布 GitHub Release v5.3.0**：`git push --tags` → `gh release create v5.3.0 dist/WorkTrace.exe`（先重新打包）
4. 待用户试用反馈后定后续方向（见 PRD §2）

## 5. 关键文件 & 环境
- 本会话改动：`src/collector/{keyboard_hook.py,uia_worker.py,uia_worker_capture.py,wps_com.py,capture_router.py}`、`src/processor/pinyin_converter.py`、`src/main.py`、`src/ui/web_api.py`、`tests/`、`界面优化/.../src/app/components/{ActivityView,AboutView}.tsx`、`pyproject.toml`、`blackbox.spec`、`requirements.txt`、4 文档 + `.gitignore`
- 产物：`web_frontend/`（已重建含 5.3.0 + Sparkles）；`dist/WorkTrace.exe`（旧，待重新打包）
- 技术栈：Python 3.13（ctypes WH_KEYBOARD_LL / pywebview 6.2.1 / UIA 子进程 + WPS COM）+ React18/TS/Tailwind4/Vite6 + SQLite(WAL) + OpenAI 兼容 LLM（默认智谱 GLM）
- 运行：`python -m src.main --gui`；打包：先关 WorkTrace.exe → `pyinstaller --noconfirm blackbox.spec`；前端：`cd 界面优化/优化图设计为macOS风格 && npm run build:desktop`（→ `web_frontend/`）
- 数据库（唯一）：`data/blackbox.db`（项目根）
- 测试：`python -m pytest -q`（**504 passed**，沙箱内加 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`）

## 6. 已知的坑 & 注意事项
- **git 仓库位置**：`.git` 在 `轻量化键盘记录工具\`；父级非 git 仓库，环境检测误报勿信
- **`.git` 仓库损坏状态（2026-09-21 发现）**：`objects/pack/` 只有 `.idx` 无 `.pack`（对象丢失）、`refs/` 缺失（已重建 refs/heads/main → `b26a91a2`）。必须 fetch origin 恢复对象；沙箱禁止写 `.git/objects/pack`，git 写操作只能在非 TRAE 终端
- **UIA 必须子进程**：主进程 import comtypes 会毁掉 pywebview WebView2 窗口（白屏）；`--uia-worker` 参数须在 GUI 初始化前分流；打包版子进程复用 exe（`WorkTrace.exe --uia-worker`），`_ensure_stdout` 处理 GUI 子系统 stdout=None
- **WPS 表格走 COM**：et.exe 单元格文本不通过 UIA 暴露；按进程列出多候选 COM 类 + duck typing（ActiveCell=表格 / Selection=文档），不能按进程名判断类型
- **bat 必须 CRLF**：LF 换行符导致 cmd 解析 if 块中止（v5.2.0 踩过，全部 bat 已转 CRLF，新增 bat 也要转）
- **改中文内容文件一律用 Edit 工具**：PS 5.1 `Get-Content` 无 `-Encoding utf8` 会把无 BOM UTF-8 读成 ANSI 导致 mojibake（v4.3.2 踩过）
- 新列索引别放 SCHEMA_SQL（旧库 executescript 报 no such column）；delete_todo 必须传 deleted_at；归档文件 append-only
- UI 字体缩放用 zoom 不用 rem；`--wt-*` token 是唯一样式真源；别用 ECharts 做报告图（PDF 丢图）
- `_tasks` 不加超时（多 provider 降级串行可能 ~27min）；测试连接用 max_tokens=1
- Windows 中文路径删除用 PowerShell / bash `rm`，别用 node fs；打包前先关 WorkTrace.exe（WinError 5）
- PowerShell 跑 native exe 的 stderr 会被包成 NativeCommandError，看 exit code + 产物即可
- 新 DB 表走 SCHEMA_SQL，新字段走 _migrate_schema；长时 LLM 操作用 task_id + 轮询
- `v4.3_看板演示.html` 不入库（约定）；tag 注意 `v4.3` 不是 `v4.3.0`

## 7. 如何续上
1. 读本文件 + `CLAUDE.md`
2. **当前状态**：v5.3.0 开发完成（504 passed）；本地 `.git` 损坏待 fetch 修复；**v4.4.0~v5.3.0 全部提交未推送**；上传脚本 `git-upload-v5.3.0.bat` 已备好
3. 验证路径：双击 `启动.bat` → 中文输入查上屏文本（UIA/COM）→ 活动页「智能识别」/「AI 增强」→ 隐私模式跳过增强
4. 确认基线：`python -m pytest -q`（应 504 passed）
5. 若要发版：上传后 `git tag v5.3.0 && git push --tags` → `gh release create v5.3.0 dist/WorkTrace.exe`（先重打包）
6. 采集链路相关改 `src/collector/` + `src/main.py`；前端拼音/AI 增强改 `ActivityView.tsx`；UI 配色只动 `theme.css`
