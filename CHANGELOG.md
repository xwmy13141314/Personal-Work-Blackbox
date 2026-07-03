# Changelog

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
