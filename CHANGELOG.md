# Changelog

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
