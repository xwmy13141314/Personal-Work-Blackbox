# Changelog

## v5.3.0 - 2026-09-15 — 输入采集准确性：键盘钩子修复（C 系列）+ UIA/COM 真实上屏文本（B 系列）

> 目标：让记录的文本**就是真实上屏内容**，而不是键盘逆推的拼音近似。
> C 系列修键盘钩子本身的丢键/漏检；B 系列在提交入库前用 UIA/COM 读到的真实文本替换键盘文本。

### 修复（C 系列：键盘钩子）
- **C1 数字键选字触发 IME 上屏检查**：`_IME_CONFIRM_VKS` 扩展覆盖数字键（主键盘 0x30-0x39 + 小键盘 0x60-0x69）——拼音候选数字选择同样会触发上屏，此前漏检；确认键按下后延时 35ms 轮询 `ImmGetCompositionStringW` 取上屏结果，`_handle_ime_confirm` 区分"数字被 IME 消费（选字）"与普通数字字符
- **C2 钩子回调减负防丢键**：`_kbd_hook_callback` 只做最小解析并 `put_nowait` 入队（队列满丢弃），`_dispatch_loop` 独立线程消费——回调内不再记日志/抛异常/执行耗时操作，避免高并发输入时回调超时丢键
- **C3 残缺拼音不硬转（置信度检测）**：`pinyin_converter.py` 新增置信度门控——2 音节序列 `avg_log ≥ -0.9`、≥3 音节序列 `≥ -1.0` 才采用 DAG 结果，低置信度弱信号转 HMM 仲裁，仍低则回退保留原文；修复 `gongsi`→`工四`、`xiangm`→`现gm` 类残缺拼音硬转错误
- **C4 AI 增强结果视觉区分**：前端会话详情与搜索结果中，AI 增强结果以 Sparkles 图标 + 主题色高亮展示，与普通拼音转换结果、原文肉眼可辨

### 新增（B 系列：UIA/COM 真实上屏文本）
- **B1 UIA 快照采集（独立子进程）**：`uia_worker.py` 子进程 + `uia_worker_capture.py` 主进程代理——UIA 读取整体隔离到子进程（**实测结论：主进程导入 comtypes 会毁掉 pywebview 的 WebView2 窗口**）；ValuePattern → TextPattern → MSAA 三路读取焦点控件；控件首次出现记基线、提交时差分出新增部分；快照过期 2.5s 自动回退键盘文本；密码控件跳过、连续失败退避；子进程崩溃自动重启（5s 退避）
- **B2 后端集成**：`main.py` 在 `_on_text_commit` 阶段用 `CaptureRouter` 三路仲裁结果替换提交文本（COM 优先 → UIA → 键盘兜底），替换前经 `_uia_should_capture` 隐私门控（隐私模式/黑名单直接跳过）；IME 上屏时 `request_snapshot()` 立即唤醒快照
- **B3 前端展示真实上屏文本**：UIA/COM 增强替换后的文本即入库文本，活动页直接展示；配置项 `accurate_mode`（总开关）/`uia_capture_enabled`/`com_capture_enabled`/`uia_capture_interval_ms` 可一键回退纯键盘链路
- **WPS/Office COM 采集**（`wps_com.py`）：WPS 表格/文字、MS Excel/Word 通过 COM 自动化读取 `ActiveCell.Value2` / `Selection.Text`——**WPS 表格的单元格文本不通过 UIA 暴露**，必须走 COM；只读绑定运行中实例（GetActiveObject）、绝不启动新进程；按进程列出多候选 COM 类 + duck typing 判断表格/文档

### 打包
- `blackbox.spec`：hiddenimports 增加 `uiautomation`、`comtypes`（含 client/stream）、`src.collector.uia_worker`、`uia_worker_capture`、`wps_com`、`capture_router`；子进程命令行打包版复用自身 exe（`WorkTrace.exe --uia-worker`），`_ensure_stdout` 处理 GUI 子系统 stdout=None
- `requirements.txt`：新增 `uiautomation>=2.0.18`、`comtypes>=1.2.0`（均为可选依赖，缺失时自动跳过增强）

### 验证
- 后端：全量单元测试 504 通过（含新增 `test_uia_worker.py`、更新后的 `test_keyboard_hook.py` IME 去重用例、`test_uia_capture.py` 差分/仲裁用例）
- 前端：vite 生产构建零错误，产物含 AI 增强视觉区分代码与 5.3.0 版本号
- GUI 完整验证需手动启动（TRAE 沙箱限制数据库写入）：双击 `启动.bat` → 在记事本/浏览器输入中文 → 检查记录为上屏文本；WPS 表格输入 → 检查单元格文本被 COM 捕获
- 打包验证需在非 TRAE 终端执行：`pyinstaller blackbox.spec --noconfirm`

## v5.2.0 - 2026-09-09 — 拼音智能识别 2.0：离线转换引擎 + AI 增强

### 新增功能
- **拼音转汉字离线引擎升级**（活动页「智能识别」）：
  - 引入开源 [Pinyin2Hanzi](https://github.com/letiantian/Pinyin2Hanzi)（MIT，纯 Python，数据来自搜狗互联网词库），内置到 `src/libs/Pinyin2Hanzi/`
  - **分层转换**：DAG（词库+动态规划，词组级）→ HMM（维特比，字级上下文）→ 原单字频率映射（兜底），任意一层失败自动降级，永不丢失原文
  - **部分转换策略**（v5.2.0 内迭代）：字母段按"连续合法音节块"分组转换（块≥2 音节），简拼声母、英文字母等无法识别的部分**保留原字母**——能识别的转汉字，识别不了的保留原文，不再整段乱转或整段跳过；实测 `nihao,jintyaowancgr1003xiangmdewaiguanjianmopinggu` → `你好,jintyaowancgr1003xiangm的外观建模评估`（旧版输出乱码 `现gm的外关建摸平古`）
  - 修复贪心分词 4 字母上限 bug（`xiang`/`zhuang` 等 5-6 字母音节被拆碎），改为最长 6 字母匹配
  - 数据文件 gzip 压缩（37MB → 5.8MB），懒加载单例（首次约 0.5s，进程内共享），不影响应用启动
  - 转换质量实测：`wojintianhenkaixin` → `我今天很开心`（旧版 `我进天很开新`）、`baocunwenjian` → `保存文件`（旧版 `报村问建`）、`xiugaibaogao` → `修改报告`（旧版 `修改报高`）；英文/数字/代号保护回归通过
- **AI 增强识别**（B+C 双引擎）：
  - 「智能识别」开启后新增「AI 增强」按钮：当前可见片段**批量一次 LLM 调用**（非逐条），结果覆盖离线引擎输出
  - Prompt 针对**简拼/混拼**优化（用户打字快，音节只敲开头几个字母）：明示 `jint→今天`、`wanc→完成`、`xiangm→项目` 等规则 + 代号规范化（`gr1003→GR1003`）+ 无法还原的保留原字母；实测真实数据 100% 还原：`nihao,jintyaowancgr1003xiangmdewaiguanjianmopinggu` → `你好，今天要完成GR1003项目的外观建模评估`、`hiayougr1002debeijiapinggu` → `还有GR1002的背夹评估`
  - 复用现有 LLM 多提供商降级（Ollama/GLM/DeepSeek/OpenAI/自定义），未配置 API Key 时按钮报错提示、离线结果保留
  - 异步任务式（task_id + 轮询），容错解析 LLM JSON 输出（代码块剥离 / 长度校验 / 失败降级）
- 原则不变：转换仅在展示层，**数据库原始数据永不修改**，关闭「智能识别」即看原文

### 后端
- 新建：`src/libs/Pinyin2Hanzi/`（vendored，仅 `implement.py` 改为 gzip 加载）、`src/ai/pinyin_ai.py`（LLM 批量转换 + 容错解析，复用 LLMClient 重试降级）
- 重写：`pinyin_converter.py`（分层引擎 + 懒加载单例 + 音节规范化 lue→lve + HMM 超长序列保护）
- `web_api.py`：新增 `convert_pinyin_ai`（批量异步任务），`convert_pinyin` 内部引擎升级（接口不变），版本号 5.1.0 → 5.2.0
- `blackbox.spec`：datas 增加 Pinyin2Hanzi gzip 数据；hiddenimports 增加 `src.libs.*` 7 项 + `src.ai.pinyin_ai`（+补 todo_extractor/timedist_extractor）

### 前端
- `ActivityView.tsx`：「AI 增强」按钮（Sparkles 图标，加载中/已增强/错误三态）+ AI 结果覆盖显示 + 数据源切换自动重置
- `pywebview.ts`：`convert_pinyin_ai` 接口签名 + mock
- 版本号统一 5.2.0（web_api / AboutView / pyproject）；构建产物已更新到 `web_frontend/`

### 修复
- **`启动.bat` 双击闪退（黑窗一闪而过、无报错、无日志）**：根因是 bat 文件为 LF（Unix）换行符，cmd 解析 `if (...)` 括号块时直接中止脚本——所有错误分支（含 pause）从未执行过；已将全部 5 个 bat（`启动` / `重新打包` / `deploy` / `scripts/install_startup` / `scripts/setup_whitelist`）转为 CRLF（UTF-8 无 BOM 编码保持不变），并用同结构测试脚本验证 if 块 + 中文 echo + pause 全部恢复正常

### 验证
- 后端：vendored 库导入/转换 13 组用例全部通过（首次 517ms 懒加载，后续 0ms）；pinyin_ai 解析 6 组容错用例（代码块/多余文字/长度不匹配/非法 JSON）+ mock LLM 全流程通过
- 前端：vite 生产构建零错误，产物含 5.2.0 版本与 AI 增强代码
- GUI 完整验证需手动启动（TRAE 沙箱限制数据库写入）：双击 `启动.bat` → 活动页任意会话展开 → 「智能识别」→「AI 增强」（需已配置 API Key）

## v5.1.0 - 2026-09-08 — 个人工作台 Phase 1：AI 周度洞察 + 全局搜索命令面板

### 新增功能
- **AI 周度洞察**（报告页新增「洞察」tab）：
  - LLM 基于本周 vs 上周活动统计（小时分布 / 每日时长 / 分类占比 / 连续天数 / 目标达成）生成 4 类洞察卡片：最佳时段（best_time）/ 需要注意（warning）/ 周环比（wow）/ 目标节奏（goal）
  - **双模式兜底**：LLM 不可用或调用失败时自动降级为本地统计规则（无 API Key 也可用），徽标区分「AI 生成」/「本地统计」
  - 异步任务式生成（立即返回 task_id，前端 1.5s 轮询），结果缓存到 `data/insights/`，支持一键重新生成
  - 日均按**实际有数据的天数**计算（修复周初「环比暴跌」误报），本周不足 3 天自动标注「数据尚不完整」；时段标签细分上午/中午/下午/晚上
- **全局搜索命令面板（Ctrl+K）**：
  - 任意界面 `Ctrl+K` 唤起，350ms 防抖跨模块搜索：**报告（日报/周报/月报正文）+ 待办 + 速记 + 输入记录**四类
  - 结果按类型分组着色，点击直达：报告 → 打开对应日期报告；待办 → 跳转看板；速记 → 跳转速记页并携带关键词过滤；输入记录 → 跳转活动明细全文检索

### 后端
- `database.py`：新增 `query_hourly_stats_range` / `query_daily_totals_range` / `query_category_stats_range` 三个周度聚合查询；`global_search` 扩展报告搜索（daily_reports + period_reports）
- `report_generator.py`：新增 `generate_weekly_insights`（LLM 优先 + `_local_weekly_insights` 本地兜底 + `data/insights/` 缓存读写）
- `prompt_engine.py`：新增 `build_weekly_insight_prompt`（v5.1 结构化 Prompt，强约束数字与统计一致、合法 JSON 输出）
- `web_api.py`：新增 `get_weekly_insights` / `generate_weekly_insights`（异步任务 + `get_task_status` 轮询），版本号 5.0.0 → 5.1.0

### 前端
- 新建：`InsightsView.tsx`（洞察卡片网格 + 生成中/错误/空态 + 轮询超时保护）、`GlobalSearchModal.tsx`（Ctrl+K 命令面板）
- 修改：`pywebview.ts`（InsightItem / InsightsData 类型 + 2 新接口签名 + mock）、`App.tsx`（Ctrl+K 全局监听 + 报告页四 tab 切换 + 搜索结果导航回调）、`QuickNoteView.tsx`（支持 `initialKeyword` 外部带入关键词）、`utils.tsx`（REPORT_TABS 增加「洞察」）
- 修复：`vite.config.ts` `__dirname` → `import.meta.url`（兼容 `--configLoader runner`，支持受限环境构建）；App.tsx 报告视图孤儿 `</>` 标签（导致构建失败）
- 版本号统一 5.1.0（web_api / AboutView / pyproject）；构建产物已更新到 `web_frontend/`

### 验证
- 后端：真实数据副本（8.1MB，13265 会话）验证周度聚合 SQL（小时/每日/分类）+ 报告搜索 + 本地洞察规则 + Prompt 构建，全部通过
- 前端：vite 生产构建 2704 模块零错误；web_frontend 产物与 index.html 引用一致
- GUI 完整验证需手动启动（TRAE 沙箱限制数据库写入）：双击 `启动.bat` → 报告页「洞察」tab / 任意页 `Ctrl+K`

## v5.0.1 - 2026-09-08 — exe 重打包发布（修复启动报错）

### 修复
- **启动报错 `unable to open database file` / `disk I/O error`**：根因是旧版 exe 内嵌的过时初始化代码，无法兼容当前数据目录；本次用最新源码重新打包，`Database.initialize()` 的健壮逻辑（目录自动创建 + WAL→DELETE 降级重试 + 损坏库备份兜底）已随新 exe 生效
- 源码版与 exe 版共用同一套 `config/`、`data/`（`get_app_root()` 开发者场景检测），历史数据（8.1MB 主库）零丢失

### 部署与验证
- 重新打包 `dist\WorkTrace.exe`（29.0 MB，PyInstaller + blackbox.spec）
- 旧 exe 归档至 `dist\旧版本备份_20260908\WorkTrace_旧版.exe`（可回滚）
- 实测验证：新 exe 启动 → 数据库初始化成功（`notes`/`projects` 新表就位）→ 键盘/窗口/剪贴板/闲置采集全部运行 → 采集自动启动
- 新增 [重新打包.bat]：一键清理 build/ 并重新打包（依赖：Python + pyinstaller）

## v5.0.0 - 2026-09-07 — 个人工作台 Phase 1：驾驶舱 + 速记

### 新增功能
- **驾驶舱（Dashboard）**：信息聚合首页，4 张指标卡片（今日采集时长/待办/逾期/速记），6 个快捷入口，最近报告列表，今日工作进度条；30 秒自动刷新
- **速记（QuickNote）**：单行速记输入（Enter 保存/Shift+Enter 换行），置顶/取消置顶，搜索过滤，仅看置顶筛选，来源标签（快捷键/报告/手动），关联待办标记
- **导航分组**：左导航改为 3 组结构——工作台（驾驶舱、速记）/ 记录与报告（报告、统计、活动、待办）/ 系统（设置、关于）；默认视图从「报告」改为「驾驶舱」
- **全局搜索**：跨文本片段、速记、待办三表搜索

### 数据库扩展
- 新增 `notes` 表：速记（content, source, pinned, linked_todo_id, 软删除）
- 新增 `projects` 表：项目（name, color, icon, archived 软归档）
- `todos` 表新增 `project_id` 列（迁移自动添加，旧库无缝升级）
- 新增 5 个索引（notes.created_at / notes.pinned / notes.deleted_at / notes.linked_todo_id / projects.archived）

### 后端 API（web_api.py）
- 速记 CRUD：`get_notes` / `add_note` / `update_note` / `delete_note`
- 项目 CRUD：`get_projects` / `add_project` / `update_project` / `delete_project`
- 驾驶舱聚合：`get_dashboard_summary`（一次调用聚合采集/待办/速记/报告数据）
- 全局搜索：`global_search`（跨三表搜索）
- 版本号 4.4.0 → 5.0.0

### 前端
- 新建：`DashboardView.tsx`、`QuickNoteView.tsx`
- 修改：`pywebview.ts`（4 新接口 + 11 方法签名 + mock）、`utils.tsx`（ViewKey + navGroups 分组）、`Sidebar.tsx`（分组导航栏）、`App.tsx`（路由 + 默认视图）
- 构建产物已输出到 `web_frontend/`

## v4.4.0 - 2026-08-14 — 待办删除归档

### 删除不再丢数据（软删除 + 双归档）
- **软删除**：`todos` 新增 `deleted_at` 列（`_migrate_schema` 自动迁移，旧库无缝升级）；应用内删除 = 打时间戳隐藏，记录仍在库中
- **文件归档双保险**：删除时同步追加 `data/exports/todo_archive_YYYY-MM.md`（按月 Markdown 表，人读）+ `todo_archive.jsonl`（全字段机读）；文件 append-only，恢复/彻底删除都不回改，任何时点可找回
- **归档视图**（待办 → 视图 → 归档）：列表形式浏览已删待办（状态/来源/进度/删除时间），关键词搜索标题/备注（防抖 300ms），分页加载
- **一键恢复**：清空 `deleted_at` 回看板，`sort_order` 保留 → 回到原看板位置；恢复后同步刷新看板统计
- **彻底删除**：两步确认（点垃圾桶 → 「确认删除」），真 DELETE；归档文件中的历史记录仍保留
- **口径同步**：看板列表 / 统计 / CSV/JSON 导出 / AI 提取去重全部排除已删除待办；删除交互不变（仍是一步删除，无需确认）

### 接口与文件
- 后端：`src/storage/database.py`（delete_todo 软删除 + query_archived_todos/restore_todo/purge_todo）、`src/ui/web_api.py`（delete_todo 重写 + get_archived_todos/restore_todo/purge_todo）、`src/storage/data_exporter.py`（append_todo_archive）
- 前端：`src/lib/pywebview.ts`（Todo.deleted_at + 3 接口 + mock）、`src/app/components/TodoView.tsx`（归档分段档 + ArchivePanel）
- 测试：test_todo.py 软删除/归档/恢复/彻底删除/统计口径 + test_export.py 归档文件 4 组；基线 364 passed
- 版本号统一 4.4.0（web_api / AboutView / pyproject）

## v4.3.2 - 2026-08-14 — UI 换肤

### 视觉方案落地（依据 `职迹UI优化效果图` 设计稿）
- **设计 token 全量更新**（`theme.css`）：品牌色 `#0071e3`→`#2563eb`、背景 `#f3f4f6`、文本 `#111827` 系、边框 `#e5e7eb`、语义色 `#22c55e/#f59e0b/#ef4444`；Inter 字体栈；html 基准字号 13→14px。`--wt-*` 是唯一样式真源，各视图自动跟随
- **日报页**：工具条实色白底（日/周/月分段器方形化、HTML/PDF 描边按钮、生成报告改 Plus 图标）；右侧栏 300→320px、毛玻璃卡改实色白卡 + shadow-sm；日历标记色统一走 `--wt-accent`
- **设置页**：实色白卡、provider chip 方形描边（「智谱GLM」→「智谱 GLM」）、输入框 focus 双环、内容限宽 720px
- **字体大小默认档 小→中**（zoom 系数不变 1/1.14/1.29，设置页三档切换逻辑不变）
- **导航**：删除「待办」的「新」徽标；左导航保留原浅色毛玻璃配色（宽 200→240px，用户确认不改暗色）
- 注：统计/活动/待办/关于视图仅经 token 换色，毛玻璃卡未实色化（已知项，待后续统一）

### 修改文件
- 前端：`styles/theme.css`、`app/lib/{fontSize.ts,utils.tsx}`、`app/components/{Sidebar,SettingsView}.tsx`、`app/App.tsx`
- 文档：README / CHANGELOG / PRD / HANDOVER
- 版本号统一 4.3.2（web_api / AboutView / pyproject）；测试基线 353 passed

## v4.3.1 - 2026-08-13 — 安全加固

### 安全与隐私
- **密钥隔离**：API Key 改由环境变量 / `config/.secrets.yaml`（已 gitignore）提供，`config.yaml` 仅占位符；`save_api_config` 重写（model/base_url→config.yaml，api_key→.secrets.yaml，含旧 key 抢救）
- **隐私过滤增强**：`sk-` 正则升级（支持 sk-proj-/下划线/连字符）；剪贴板密码关键词检测生效（filter_clipboard 加 context）
- **应用黑名单扩充至 17 个**（银行/钱包/密码管理器类）
- **DB 安全审计**：10 表扫描 0 命中明文，无需清理
- **运行时健壮性**：键盘钩子看门狗（线程崩溃自恢复）+ session 写入 3 次重试
- **测试连接修复**：`test_api_config` 改 max_tokens=1 轻量请求（原复用 complete() 触发前端超时误判）
- **死代码清理**：移除 `personal_recorder` 死模块（38 文件约 2857 行）
- 待办看板列内叠加优先级排序；版本号前后端统一 4.3.1；353 passed；已发布 GitHub Release v4.3.1

## v4.3.0 - 2026-08-11 — 待办看板增强 + 双库根治

### 双库问题根治（架构修复）
- **根因**：`get_app_root()`（src/main.py）对打包 exe（返回 `dist/`）与源码 python（返回项目根）解析出不同路径，导致 exe 与 python 各用一套 `data/blackbox.db`，长期使用数据分叉
- **修复**：`get_app_root` 改为**智能检测**——打包 exe 启动时检测 `exe.parent.parent/src` 是否存在：存在（=开发者场景，exe 在项目内 dist/）则返回项目根，与源码运行共用同一套 config/data/logs；不存在（=外部用户场景，exe 单独分发）则返回 exe 同级目录，数据就近存放
- 移除双库过渡期的一次性迁移函数 `_migrate_legacy_data`（根治后冗余）
- `system_tray.py` / `gui.py` 中相对 cwd 的 `Path("./data")` 改为 `get_app_root()/"data"`，消除对启动目录的依赖
- 合并后的权威主库：项目根 `data/blackbox.db`（11140 会话 / 43 日报 / 7 待办）；dist 旧库归档至 `data/backup_双库根治归档_20260811/` 后清理
- exe 已重打包（含智能检测逻辑，验证日志确认 exe 与 python 读同一库）

### 待办看板（§4.1-4.10）
- **P1 三列看板**：@dnd-kit 拖拽（待办 / 进行中 / 已完成）+ sort_order 排序 + 来源下钻 + 4 统计卡片
- **P2 进度跟踪**：progress 字段 + 100%↔done 状态联动（clamp [0,100]，纯拖拽改 status 不动 progress）
- **P2-C AI 推进建议**：start / progress / stall 三类建议，日报生成后自动触发，入 todo_advices（去重），「采纳」才改待办
- **P3-A 融合工作实况**：统计卡旁今日活动迷你环形图（MiniDonut 纯 SVG，复用 category_stats）
- **P3-B 逾期顺延**：逾期待办红色提示条 + 一键批量顺延到今日
- **P3-C toast 提醒**：todo_notify_log 去重表 + 后台线程每小时检查 + send_toast
- **P4-A 数据导入导出**：`export_todos_json`（todos 全字段 JSON 备份，原始值不翻译）/ `import_todos_json`（mode=append 同标题跳过 / merge 更新内容不动 sort_order）；后端 + pywebview 接口保留，前端工具栏按用户决定只留 CSV 导出（备份/导入按钮精简）
- **P4-B 多维视图**：viewMode 切换——按状态（三列可拖）/ 按来源（手动 / 日报 / 周报 / 月报 四列只读），看板上方 segmented 切换器；应用类别维度因 todo 无 category 字段未做

### 修改文件
- 核心架构：`src/main.py`（get_app_root 智能检测 + 移除 _migrate_legacy_data）、`src/ui/system_tray.py` / `src/ui/gui.py`（get_app_root 取代 Path("./data")）
- 待办看板后端：`src/ui/web_api.py`、`src/storage/database.py`、`src/storage/data_exporter.py`、`src/ai/`（todo_extractor / prompt_engine / report_generator）
- 前端：`界面优化/优化图设计为macOS风格/src/app/components/TodoView.tsx`（看板 + 多维视图）、`src/lib/pywebview.ts`
- 测试：`tests/test_todo.py`（+TestTodoJsonBackup 7 个）

### 测试
- 全量 353 passed（v4.2.0 的 291 → P1-P4 新增 62）

## v4.2.0 - 2026-08-08 — 报告可视化 + 导出能力

### 报告导出（HTML / PDF）
- 新增 `src/storage/report_exporter.py`：将报告 Markdown 渲染为自包含单文件 HTML（内联 CSS/SVG，无外部依赖，可离线打开、微信/邮件直发）
- macOS 风格卡片化排版：Hero 标题区（类型胶囊 + 日期 + 模型元信息）+ 章节正文 + 时间分布环形图 + 页脚
- h2 章节标题自动注入 emoji 图标（概览📋/完成✅/沟通💬/待办📌/时间分布📊/效率⚡…）
- 内置 `@media print`：浏览器 Ctrl+P 直接打出排版干净的 PDF，环形图静态 SVG 必显示（不依赖 JS 渲染）
- `export_report` 桥接 API：导出前自动提取时间分布，LLM 失败则导出无图版（优雅降级）

### 待办导出（CSV）
- `DataExporter.export_todos_csv`：待办列表导出为 CSV，UTF-8 BOM 编码（Excel 中文不乱码）
- 字段含标题/状态/优先级/来源/截止日期/是否草稿/来源引用，状态与优先级做中文映射

### 时间分布可视化（环形图）
- 新增 `src/ai/timedist_extractor.py`：复用 todo_extractor 模式，LLM 从报告"时间分布"章节提取 `[{"category","minutes","percent"}]`，容错 JSON 解析 + 百分比归一化
- `render_donut_svg`：纯 SVG 环形图（stroke-dasharray 扇形 + 图例），后端一处生成、导出 HTML 与 app 内共用；不内联约 1MB JS 库，单文件 HTML 保持轻量
- app 内报告页：报告加载后调 `analyze_report`（task 轮询）渲染环形图，LLM 失败静默隐藏图区
- 数据源决策：DB sessions 表无 category 列、报告文字格式 8 种不统一，故采用 LLM 提取（新旧报告都管，与文字一致）

### 修改文件
- 新增：`src/ai/timedist_extractor.py`、`src/storage/report_exporter.py`
- 修改：`src/ai/prompt_engine.py`（+时间分布提取 prompt）、`src/main.py`（+extract_timedist_from_report）、`src/ui/web_api.py`（+analyze_report / 增强 export_report）、`src/storage/data_exporter.py`（+export_todos_csv）
- 前端：`界面优化/优化图设计为macOS风格/src/app/App.tsx`（报告页环形图 + 导出按钮）、`src/lib/pywebview.ts`（+analyze_report 签名与 mock）
- 测试：`tests/test_export.py`（+SVG/解析/CSV 共 18 个新测试）

### 测试
- 全量 291 passed（含新增 TestDonutSvg 5 / TestTimedistParse 7 / TestTodosCsv 6）

## v4.1.0 - 2026-07-08 — 键盘捕获引擎重构 + 关于页面

### 键盘捕获引擎彻底重构（核心修复）

经过 6 轮迭代调试，彻底解决了 PyInstaller 打包环境下键盘事件无法捕获的问题。

#### 问题根因链
1. `ImmGetOpenStatus()` 在英文模式下也返回 True，丢弃所有按键
2. pynput 在打包 exe 中静默回退到 `_dummy` 后端
3. pynput.Listener 线程消息泵在 pywebview 环境下不工作
4. WH_KEYBOARD_LL 安装在 pywebview 主线程，但主线程没有标准 Win32 消息泵
5. WH_GETMESSAGE 钩子传 thread_id=0 导致 error 1428（需要 DLL 注入）
6. `GetKeyboardState()` 在钩子线程返回全零，`ToUnicodeEx` 无法转换字符

#### 最终方案
- **ctypes 直接调用**：抛弃 pynput.Listener，使用 `SetWindowsHookExW(WH_KEYBOARD_LL)` 直接安装钩子
- **专用线程 + 独立消息泵**：创建 KbHookThread 线程，运行 `GetMessageW` 循环处理回调，不依赖 pywebview 主线程
- **64 位类型修复**：`LRESULT`/`WPARAM`/`LPARAM` 使用 `c_ssize_t`/`c_size_t`（ctypes.wintypes 错误地定义为 32 位）
- **硬编码字符映射**：字母键 A-Z 和数字键 0-9 使用硬编码映射 + `MapVirtualKeyW(MAPVK_VK_TO_CHAR)`，不依赖 `GetKeyboardState`
- **shift 状态自跟踪**：_process_keydown 中自行维护 shift 按下状态，传入 _vk_to_char
- **IME 主动轮询**：WH_GETMESSAGE 钩子 + 在确认键（Enter/Space等）触发时主动调用 `ImmGetCompositionStringW` 获取组合结果
- **优雅停止**：`PostThreadMessageW(WM_QUIT)` 通知钩子线程退出消息泵

#### 钩子生命周期改进
- `engine.stop()` 不再卸载键盘钩子，仅设 `_keyboard_paused` 标志
- 只有 `engine.shutdown()`（应用退出）才卸载钩子
- 解决 stop() 后 start() 钩子已卸载无法重新安装的问题

#### 全链路诊断日志
- `首次按键事件已收到: vk=0xXX` — 钩子捕获到首个按键
- `按键转换: vk=0xXX → char='x'` — 虚拟键码转字符成功
- `引擎首次收到键盘事件` — 事件到达引擎
- `InputBuffer 首次收到字符` — 字符到达缓冲区
- `InputBuffer 提交文本: 'text' (len=N)` — 文本片段提交
- `引擎首次收到文本提交` — 引擎收到文本
- `会话持久化: segments=N` — 片段写入数据库

### 新增「关于」页面

- 五视图导航：报告 / 统计 / 活动 / 设置 / 关于
- AboutView.tsx 组件：版本信息 (v4.1.0) + 隐私承诺 + 联系方式（邮箱 xwmy1314@gmail.com + GitHub 链接）+ 技术栈
- utils.tsx 新增 'about' 到 ViewKey 和 navItems
- App.tsx 新增 AboutView 路由

### 其他改进

- **自动启动采集**：web_ui.py 中 pywebview 窗口加载 3 秒后自动启动引擎
- **竞态条件修复**：_on_closing 与 _auto_start 线程通过 _shutting_down 标志协调
- **pynput 打包修复**：blackbox.spec 添加 `collect_submodules('pynput')` + 7 个显式 hiddenimports
- **InputBuffer 智能去重**：IME 组合文本到达时自动移除缓冲区中残留的拼音字母
- **测试适配**：244 passed（keyboard_hook 15 + input_buffer 29 + integration 12 + 其他）

### 技术细节

#### 修改文件
- `src/collector/keyboard_hook.py` — 完全重写（ctypes WH_KEYBOARD_LL + 专用线程）
- `src/processor/input_buffer.py` — 适配新 KeyEvent + 诊断日志
- `src/main.py` — 钩子生命周期分离 + 诊断日志
- `src/ui/web_ui.py` — 自动启动 + 竞态条件修复
- `src/ui/web_api.py` — 版本号更新
- `blackbox.spec` — pynput hiddenimports
- `tests/test_keyboard_hook.py` — 适配新 API
- `tests/test_input_buffer.py` — 适配 pynput Key
- `tests/test_integration.py` — 适配 pynput Key
- 前端：AboutView.tsx（新增）、utils.tsx、App.tsx

## v4.0.0 - 2026-07-06 — 品牌重定位 + 发布红线 + 功能增强

### 第一期：发布前红线与核心体验修复

#### 品牌重定位
- 全线文案去除"键盘记录"，改为"活动追踪"/"输入记录"
- README 新增隐私优先 slogan：隐私优先的个人 AI 工作日志 · 本地存储 · 开源可审计
- pyproject.toml 描述更新为"轻量化个人活动追踪与 AI 工作日志工具"
- 前端 UI 中面向用户的"键盘"文案替换为"输入"

#### 首次启动隐私告知弹窗
- 新增 PrivacyConsent.tsx 组件：首次启动弹出隐私告知，说明采集内容、本地存储、三层过滤机制
- 后端 get_consent_status / set_consent API，持久化到 data/.consent 文件
- 支持"仅记录窗口活动"选项

#### 数据库加密（SQLCipher）
- Database 类支持 encryption_key 参数，可选启用 SQLCipher 加密
- 新增 migrate_to_encrypted 方法：明文数据库 → 加密数据库迁移
- 配置开关 storage.encryption_enabled + 环境变量 WORKTRACE_DB_KEY
- 优雅降级：sqlcipher3 未安装时回退到普通 sqlite3

#### IME 中文输入法捕获
- 新增 Windows IMM API 绑定（ctypes），检测 IME 组合状态
- 键盘事件中检测 IME 活动，捕获组合完成后的最终中文文本
- InputBuffer 新增 _on_ime_text 方法，将整段 IME 文本作为单个语义片段处理
- KeyEvent 新增 is_ime_composition 标志
- 10 个新增测试覆盖 IME 场景

#### 前端重构
- App.tsx 从 1096 行拆分为 537 行 + 4 个独立组件文件（Sidebar/StatsView/ActivityView/SettingsView）
- 新建 utils.tsx 提取共享类型、工具函数和通用组件
- 新建 theme.css 定义 16 个 --wt-* CSS 变量，统一 15 类硬编码色值
- StatusDot / Badge 组件颜色改用 CSS 变量

#### 依赖清理
- 前端 dependencies 从 46 个精简到 11 个
- 删除 45 个未使用的 shadcn UI 组件文件
- 移除 @mui/material、recharts、react-dnd、@emotion 等未用依赖

#### 集成测试
- 新建 test_integration.py，16 个测试覆盖引擎初始化、键盘→数据库、隐私过滤、加密、原子写入、API 冒烟、品牌验证

### 第二期：产品功能增强与竞争力提升

#### 自动应用分类系统
- 新建 AppClassifier 模块：10 类预设分类（开发工具/浏览器/通讯社交/办公文档/设计创作/娱乐休闲/系统工具/数据库/AI 工具/其他）
- 每个分类配 emoji 图标，基于进程名 + 窗口标题正则匹配
- 数据库 sessions 表新增 category 和 icon 列（migration 向后兼容）
- 新增 backfill_categories 方法：为历史数据批量回填分类
- API: get_category_stats / backfill_categories / get_categories

#### 数据导出与 REST API
- 新建 DataExporter 模块：支持 CSV / JSON 格式导出会话和文本片段
- CSV 使用 UTF-8 BOM 编码（Excel 兼容），已过滤内容显示为 [已过滤]
- 新建 RestAPIServer：基于 http.server，6 个端点（/api/status, /api/sessions, /api/sessions/{id}, /api/stats, /api/search, /api/dates）
- 仅监听 127.0.0.1:19527（安全考虑），配置开关默认关闭

#### 专注模式与提醒系统
- 新建 FocusModeManager：娱乐应用检测 + 专注会话 + 效率目标
- FocusSession 类：目标设定、时长控制、分心比率计算
- 窗口切换时自动追踪分类，娱乐超阈值触发提醒（含冷却机制）
- 每日工作目标设定与达成检测
- API: start_focus_session / stop_focus_session / get_focus_session / get_daily_efficiency / set_daily_goal

#### CI 测试流水线
- 新建 .github/workflows/ci.yml：Windows + Ubuntu 双平台
- push/PR 自动运行 pytest + flake8 lint
- 测试结果 artifact 上传

#### personal_recorder 隔离
- 确认主项目无依赖，blackbox.spec 添加 excludes
- 创建 README 说明隔离决策和未来计划

#### 打包体积优化
- blackbox.spec 新增 14 个排除模块（tkinter/unittest/setuptools 等）
- 启用 strip=True，UPX 排除关键 DLL
- 清理 33 个旧前端构建产物文件

### 测试与验证
- 198 个测试全部通过（174 原有 + 24 新增）
- 前端 Vite 构建 2691 模块 0 错误

## v3.2.0 - 2026-07-06 — 安全加固与线程安全

### 安全（Security）

- API Key 支持环境变量加载（GLM_API_KEY / DEEPSEEK_API_KEY 等），避免明文存储
- 清理 config.yaml 中的明文密钥，改用占位符
- 隐私过滤正则大幅补全：新增 JWT Token、API Key (sk-xxx)、IPv4 地址、PEM 私钥、URL 内嵌凭据
- 银行卡正则支持 16-19 位
- NUMBER_PATTERN 阈值从 6 位提高到 8 位，减少误杀
- 自定义正则编译容错（单条非法不影响其余）

### 线程安全（P0 修复）

- Database：所有读写操作加 threading.Lock 保护，消除多线程 commit/rollback 互相干扰
- InputBuffer：所有缓冲区操作加锁，消除键盘线程与窗口线程的竞态
- SessionManager：所有会话操作加锁，消除 TOCTOU 错误
- 新增 insert_session_with_segments 原子性批量插入方法，解决会话持久化非原子问题
- 会话持久化改为单事务写入

### 功能修复（Fixed）

- 实现 Ctrl+A 全选替换功能（之前文档宣称但未实现）
- 剪贴板回调增加黑名单检查（之前密码管理器中复制密码仍被记录）
- 修复 KeyboardHook char 解析运算符优先级隐患
- SessionManager 新增 MAX_SEGMENTS_PER_SESSION 限制，防止超长会话内存无限增长

### UI / 错误处理

- 后端控制方法（start/stop/pause/resume/toggle_privacy）统一加 try/except
- _tasks 字典读取后自动清理，防止内存单调增长
- web_ui.py os._exit 前加 0.5s 延迟确保 DB flush 完成
- AI 层降级链支持自定义提供商（不再仅限 FALLBACK_ORDER 硬编码列表）
- 版本号统一为 3.2.0（pyproject.toml 与 CHANGELOG 一致）
- 构建产物 title 修正为「职迹 WorkTrace」

## v3.1.0 - 2026-07-03 — 职迹 WorkTrace：Web GUI + 品牌化 + 多模型

### 新增（Added）

- 全新 Web GUI：pywebview + React 三栏界面（macOS 风格 + Windows 原生标题栏），替代 tkinter
- 四视图导航：报告 / 统计 / 活动明细 / 设置
- 统计视图：应用使用时长排行（今日 / 本周 / 本月）+ 条形图
- 活动明细视图：按日期浏览会话与文本片段
- 全文搜索：检索历史键盘输入（text_segments，跨日期）
- 常驻日历（右栏）：圆角图标、36px 方格撑满、双标记（有采集蓝点 / 有日报底色）、周 / 月跳转
- 设置页 API 配置可编辑表单：6 预设（智谱 / 阿里通义 / DeepSeek / Kimi / OpenAI / 自定义）+ 测试连接 + 保存到 config.yaml
- 通用 `OpenAICompatibleProvider`：任意 OpenAI 兼容厂商即配即用
- 数据库 `query_reported_dates` / `query_session_by_id` / `search_text`
- 桥接 API：`get_app_stats` / `get_sessions` / `get_session_detail` / `search_text` / `get_reported_dates` / `save_api_config` / `test_api_config`
- 品牌化：改名「职迹 WorkTrace」、∞ 莫比乌斯环图标（圆角 app.ico + logo.png）、Slogan「让每一分努力都有迹可循」、副标题「您的私有工作黑盒」、Local Only 标注

### 变更（Changed）

- 默认 GUI 入口从 tkinter 切换到 Web UI（`--gui-tk` 保留回退）
- 隐私模式改为真·开关：开启时再点一次立即关闭（之前只能重置 30 分钟）
- exe 文件名 PersonalWorkBlackbox.exe → `WorkTrace.exe`
- 窗口标题 / 启动.bat / 关于页 全部改为「职迹 WorkTrace」

### 修复（Fixed）

- 录制中生成日报缺失当前会话内容：`generate_daily_report` 前强制 flush 当前会话并接续新会话（`_flush_active_session`）
- PyInstaller windowed 模式 stdout=None 崩溃、pywebviewready 时序误用 mock、pythonnet CLR 阻止退出等打包坑

### 数据整理

- 5 个分叉 blackbox.db 合并为单一权威主库（9347 会话 / 29 份日报，05-14 ~ 07-02 连续完整）
- 原始库归档 `data/backup_历史库_2026-07-03/`，清理 build/轻量化111/v2.2 等冗余约 188M

### 保留（Preserved）

- 原 Blackbox 采集 / 存储 / AI 链路、周报月报、托盘、tkinter 回退入口
- Personal Recorder 模块（v3.0）不受影响

## v3.0.0 - 2026-06-07

### Added

- Added `src/personal_recorder` as a parallel module inside the original repository.
- Added a unified `events` data model for personal activity recording.
- Added `personal-recorder` CLI entrypoint.
- Added Blackbox SQLite history import for:
  - `sessions`
  - `text_segments`
  - `clipboard_records`
  - `window_events`
- Added inbox-based realtime ingestion:
  - `push-event`
  - `watch-inbox`
- Added Windows runtime bridge for Blackbox collectors:
  - window switch bridge
  - clipboard bridge
  - keyboard buffered text bridge
- Added daily report and weekly report generation for the new recorder pipeline.
- Added `.ics` calendar export.
- Added rule-based importance extraction and action-item extraction.
- Added privacy-aware layered storage:
  - raw content
  - redacted content
  - derived summary
  - storage tier tagging
- Added first-wave local snapshot collectors:
  - Git activity
  - Git branch, status, and diff snapshots
  - shell history
  - recent file modifications
  - Chrome-family browser history
- Added first-wave macOS snapshot collectors:
  - Safari history
  - foreground application snapshot
  - clipboard snapshot
- Added macOS Calendar import and permission check commands
- Added lightweight `watch-macos` background watch mode
- Added launchd install / uninstall / status commands for macOS watch mode
- Added persistent watch state storage and near-realtime shell history ingestion

### Changed

- Upgraded repository positioning from a single Windows Blackbox app to a dual-track repository:
  - original Blackbox workflow
  - new Personal Recorder workflow
- Updated `README.md` to describe both usage paths clearly.
- Updated `pyproject.toml` to expose the `personal-recorder` CLI.

### Preserved

- Preserved the original `src.main` application entrypoint.
- Preserved the original Windows GUI and tray workflow.
- Preserved the original collector, processor, storage, AI, UI, and packaging structure.
- Preserved the original Blackbox use case for Windows desktop activity capture.

### Notes

- This version introduces a stronger personal knowledge and reporting workflow without removing the original Blackbox flow.
- Privacy protection currently uses rule-based redaction and storage tier tagging.
- Git transport on the local machine was unstable, so the repository update was ultimately synchronized through authenticated GitHub API writes.

## v2.3 - 2026-05-27

- Added weekly and monthly report support.
- Added period report persistence.
- Improved prompt templates and cross-day statistics.
- Reorganized repository directories and packaging assets.

## v2.2 - 2026-05-19

- Improved database query and statistics tests.
- Verified actual AI daily report generation flow.
- Initialized repository version control.

## v2.1 - 2026-05-14

- Fixed clipboard monitoring crash on 64-bit Python.
- Fixed GUI startup crash behavior.
- Improved PyInstaller packaging and startup error visibility.
