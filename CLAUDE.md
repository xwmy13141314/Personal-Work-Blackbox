# Personal Work Blackbox — AI 项目上下文

## 项目概述
轻量化个人工作日志采集与 AI 日报工具。记录键盘输入 + 窗口上下文 + 剪贴板，通过智谱 GLM 生成每日工作报告。

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
`data/blackbox.db` — 5 张表: sessions, window_events, text_segments, clipboard_records, daily_reports
（config_snapshots 在 PRD 中提及但未实现）

## 测试
140 个测试，覆盖:
- InputBuffer(16)、PrivacyFilter(19)、SessionManager(9)、AI Layer(18)
- Database 全量 CRUD(32)、MarkdownExporter(15)、Settings 配置层(18)、ReportGenerator(13)

## 当前状态 (2026-05-19)
- Phase 1 + Phase 2 开发完成
- GUI 操作面板已实现（tkinter）
- 已打包为 `Personal_Work_Blackbox_v2.0.zip`
- 智谱 API Key 已配置，glm-4.5-flash 可用，glm-4.7 待充值后切换
- 2026-05-15: 修复 2 个 Bug + 新增 74 个测试（总计 136 个全通过）
- 2026-05-17: 新增 4 个数据库查询/统计测试（总计 140 个全通过）
- 已完成实际使用测试（5月17日完整采集+AI日报生成流程验证通过）

## 已知待改进项
- 中文 IME: 仅捕获拼音，需接入 UI Automation 获取最终文本
- API Key 明文存储在 config.yaml 中
- config/prompts/ 自定义模板目录已创建但为空
- 采集层和 UI 层缺少测试覆盖
- BlackboxEngine 核心协调逻辑缺少测试
- 未使用版本控制（待初始化 Git）
