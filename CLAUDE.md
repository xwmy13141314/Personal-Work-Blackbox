# Personal Work Blackbox — AI 项目上下文

## 项目概述
轻量化个人工作日志采集与 AI 报告工具。记录键盘输入 + 窗口上下文 + 剪贴板，通过智谱 GLM 生成每日工作报告、周报和月报。

## 关键决策
- **键盘记录方案**: 使用 pynput (WH_KEYBOARD_LL)，有杀毒误报风险，提供白名单引导脚本
- **中文 IME**: MVP 阶段仅捕获拼音序列+窗口上下文，V1.1 接入 UI Automation 获取最终文本
- **AI 提供商**: 默认智谱 GLM-4.5-flash（当前账户可用），充值后切 glm-4.7（改 config.yaml 即可）
- **存储**: SQLite WAL 模式 + 每日 Markdown 导出
- **生命周期管理**: `stop()` 停止采集但保留 DB 连接（支持后续报告生成），`shutdown()` 完全关闭含 DB（仅在应用退出时调用）

## 运行方式
```bash
python -m src.main --gui       # GUI 模式（默认）
python -m src.main --no-tray   # 命令行模式
python -m src.main             # 等同 --gui
```

## 配置文件
`config/config.yaml` — AI Key、模型选择、隐私黑名单、性能参数

## 数据库
`data/blackbox.db` — 6 张表: sessions, window_events, text_segments, clipboard_records, daily_reports, period_reports
- `period_reports` 存储 AI 周报和月报，按 `(report_type, period_start)` 唯一索引
- `query_app_usage_stats_range(start, end)` 支持跨日期范围的应用统计
（config_snapshots 在 PRD 中提及但未实现）

## 测试
164 个测试，覆盖:
- InputBuffer(16)、PrivacyFilter(19)、SessionManager(9)、AI Layer(24)
- Database 全量 CRUD(32)、MarkdownExporter(15)、Settings 配置层(18)、ReportGenerator(31)
- 重试机制 + 错误分类 + 网络诊断(6)
- 日期范围工具函数(10)、周报/月报生成(8)、PromptEngine 周报/月报(1)

## 当前状态 (2026-05-27)
- Phase 1 + Phase 2 开发完成
- **Phase 3: 周报/月报功能已完成** — GUI 新增报告类型选择器，支持日报/周报/月报切换
- GUI 操作面板已实现（tkinter）
- 已打包为 `Personal_Work_Blackbox_v2.2/`（纯 exe 运行目录，2026-05-27 重新打包）
- 智谱 API Key 已配置，glm-4.5-flash 可用，glm-4.7 待充值后切换
- LLM 调用容错体系（重试+降级+网络诊断+自动补生成）
- 已完成实际使用测试（5月14日~5月26日完整采集+AI日报生成验证通过）
- 数据库已合并为单一完整库（5/14~5/26，含 7 份日报）
- 目录已整理：文档归 docs/，日志归 data/logs/，v2.2 精简为纯运行目录

## 目录结构
```
轻量化键盘记录工具/
├── config/              # 配置文件
│   ├── config.yaml
│   ├── config.example.yaml
│   └── prompts/         # 自定义提示词模板（预留）
├── data/                # 统一数据目录
│   ├── blackbox.db      # 主数据库（已合并，5/14~5/26 完整数据）
│   └── logs/            # 所有历史日志 + AI 日报
├── docs/                # 项目文档
│   ├── PRD_Personal_Work_Blackbox_v2.md
│   ├── 轻量化数据采集.docx
│   ├── work_report.html
│   └── 使用说明.md
├── scripts/             # 辅助脚本
├── src/                 # 源码
├── tests/               # 测试（164 个）
├── Personal_Work_Blackbox_v2.2/  # 精简 exe 运行目录
│   ├── PersonalWorkBlackbox.exe
│   ├── config/
│   ├── data/            # 含合并后的数据库副本
│   ├── scripts/
│   └── 使用说明.md
├── blackbox.spec
├── CLAUDE.md
├── pyproject.toml
├── README.md
├── requirements.txt
└── 启动.bat
```

## LLM 容错机制
- **指数退避重试**: 单个提供商最多重试 3 次（延迟 5→15→30 秒），仅网络类错误重试
- **自动降级**: 默认提供商失败后按 ollama→glm→deepseek→openai 顺序尝试
- **网络预检**: `diagnose()` 方法可快速区分"配置错误"和"网络不通"
- **自动补生成**: 引擎启动时扫描最近 7 天，对有数据无日报的日期自动补生成
- **GUI 防抖**: 生成按钮加 `_generating` 标志，防止连点创建多线程

## 周报/月报功能
- **触发方式**: GUI 报告类型下拉选择「周报」或「月报」，选择该周期内任意日期，自动计算自然周/月
- **数据来源**: 基于该周期内已有的日报（`daily_reports`）汇总，缺失日报的日期在报告中标注
- **持久化**: 新表 `period_reports`（`report_type` + `period_start` 唯一），同一周期覆盖旧版
- **文件保存**: 周报 `{周一日期}_weekly.md`，月报 `{yyyy-MM}_monthly.md`
- **详细 PRD**: `docs/PRD_周报月报功能.md`

## 已知待改进项
- 中文 IME: 仅捕获拼音，需接入 UI Automation 获取最终文本
- API Key 明文存储在 config.yaml 中
- config/prompts/ 自定义模板目录已创建但为空
- 采集层和 UI 层缺少测试覆盖
- BlackboxEngine 核心协调逻辑缺少测试
- 未使用版本控制（待初始化 Git）— *已初始化 Git（2026-05-27）*
