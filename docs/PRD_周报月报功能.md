# PRD — 周报/月报生成功能

> **状态**: ✅ 已完成（2026-05-27）
> **版本**: v2.3

## 1. 需求背景

当前系统仅支持**日报**生成（单日数据 → AI 总结）。实际使用中，用户需要按周/月维度汇总工作内容，用于：
- 周报提交（向上级汇报本周工作）
- 月度回顾（自我复盘，发现效率趋势）
- 避免手动拼接多篇日报

## 2. 功能定义

### 2.1 周报
- **触发方式**: GUI 新增「生成周报」按钮，自动计算选中日期所在自然周（周一~周日）
- **数据来源**: 该周内所有已有的**日报**（`daily_reports` 表），如果某天缺日报则先自动补生成（可选，默认跳过）
- **输出**: 一篇 Markdown 周报，保存到 `data/logs/` + 持久化到数据库

### 2.2 月报
- **触发方式**: GUI 新增「生成月报」按钮，自动计算选中日期所在自然月
- **数据来源**: 该月内所有已有的**日报**（跨周汇总）
- **输出**: 一篇 Markdown 月报，保存到 `data/logs/` + 持久化到数据库

### 2.3 智能降级
- 如果该周/月内有日报缺失，**不阻断**，基于已有的日报生成（在周报中标注缺失天数）
- 如果该周/月完全无日报，提示用户先补生成日报

## 3. 技术方案

### 3.1 数据库扩展

**方案**: 在现有 `daily_reports` 表基础上，新增 `period_reports` 表。

理由：`daily_reports` 的 UNIQUE 约束是 `report_date`（YYYY-MM-DD），周报/月报的标识是日期范围而非单日，强行复用需要改表结构且影响现有逻辑。新建表更符合 SOLID 的开闭原则。

```sql
CREATE TABLE IF NOT EXISTS period_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type       TEXT NOT NULL,           -- 'weekly' | 'monthly'
    period_start      TEXT NOT NULL,            -- YYYY-MM-DD（周一/月初）
    period_end        TEXT NOT NULL,            -- YYYY-MM-DD（周日/月末）
    report_label      TEXT NOT NULL,            -- 显示标签，如 "2026-W21" 或 "2026-05"
    structured_report TEXT NOT NULL,
    model_used        TEXT NOT NULL,
    generated_at      TEXT NOT NULL,
    format            TEXT DEFAULT 'markdown',
    token_count       INTEGER DEFAULT 0,
    UNIQUE(report_type, period_start)
);
```

### 3.2 各层改动清单

| 层 | 文件 | 改动内容 |
|---|---|---|
| **模型** | `src/storage/models.py` | 新增 `PeriodReportRecord` 数据类 |
| **数据库** | `src/storage/database.py` | 1. SCHEMA 新增 `period_reports` 建表语句<br>2. 新增 `insert_period_report()` / `query_period_report()` / `query_app_usage_stats_range()` |
| **Prompt** | `src/ai/prompt_engine.py` | 1. 完善周报 Prompt（填充真实 `weekly_app_stats`）<br>2. 新增月报 Prompt（`build_monthly_prompt`） |
| **报告生成** | `src/ai/report_generator.py` | 1. 完善 `generate_weekly_report()` 加入持久化<br>2. 新增 `generate_monthly_report()`<br>3. 新增 `generate_period_sync()` 统一入口 |
| **引擎** | `src/main.py` | 新增 `generate_weekly_report()` / `generate_monthly_report()` 代理方法 |
| **GUI** | `src/ui/gui.py` | AI 报告区新增报告类型选择器（日报/周报/月报），按钮联动 |

### 3.3 数据流

```
用户点击「生成周报」
    │
    ▼
GUI._on_generate_report() 识别报告类型
    │
    ▼
Engine.generate_weekly_report(end_date)
    │
    ▼
ReportGenerator.generate_weekly_report(end_date)
    │  ├─ 计算自然周范围 (周一 ~ 周日)
    │  ├─ DB.query_period_report(weekly, start) → 检查已有
    │  ├─ 逐日 DB.query_daily_report() → 收集日报
    │  ├─ DB.query_app_usage_stats_range(start, end) → 跨日统计
    │  ├─ PromptEngine.build_weekly_prompt(data) → 构建 Prompt
    │  ├─ LLMClient.complete(messages) → AI 生成
    │  └─ DB.insert_period_report() → 持久化
    │
    ▼
返回 Markdown → GUI 保存文件 + 预览
```

月报流程同理，仅日期范围计算和 Prompt 不同。

### 3.4 GUI 交互设计

在现有 AI 报告区增加报告类型选择：

```
[日报 v]  日期: [2026-05-27 v] [◀][▶]  [生成报告] [查看报告]
```

- **报告类型下拉**: `日报` / `周报` / `月报`
- 选择「周报」时，日期选择器变为该周的**任意一天**，系统自动计算所在自然周
- 选择「月报」时，同理自动计算所在自然月
- 「查看报告」按钮也适配：日报按原有逻辑，周报/月报从 `period_reports` 查询

### 3.5 周报 Prompt 结构

**System**: 周报分析助手，关注跨日持续任务、效率趋势
**User 输入**:
- 每日日报摘要（已有的 structured_report）
- 本周应用使用统计（跨日汇总的 `app_usage_stats`）
- 出勤天数/缺失天数

**输出格式**:
1. 本周概览（一段话）
2. 关键成果（按重要度排序）
3. 进行中事项（跨周持续任务）
4. 下周计划建议
5. 效率分析（时间分布趋势）

### 3.6 月报 Prompt 结构

**System**: 月报分析助手，关注月度目标完成度、长期趋势
**User 输入**:
- 每日日报摘要
- 本月应用使用统计（跨日汇总）
- 出勤天数/总工作天数
- 按周分组的工作分布

**输出格式**:
1. 本月概览
2. 关键成果与里程碑
3. 按周工作分布
4. 效率趋势分析（本月时间投入变化）
5. 下月计划建议

## 4. 文件保存约定

| 报告类型 | 文件名格式 | 示例 |
|---|---|---|
| 日报 | `{date}_{HHMMSS}_report.md` | `2026-05-22_091156_report.md` |
| 周报 | `{start}_weekly.md` | `2026-05-19_weekly.md` |
| 月报 | `{yyyy-MM}_monthly.md` | `2026-05_monthly.md` |

周报/月报文件名不含时间戳（同一周期覆盖旧版）。

## 5. 不做的事（YAGNI）

- ❌ 自动定时生成周报/月报（仅手动触发）
- ❌ 自动补生成缺失日报后再生周报（提示用户手动补即可）
- ❌ 自定义周期（双周报、季报等），仅支持自然周和自然月
- ❌ 周报/月报导出为 HTML/PDF（仅 Markdown）
- ❌ 发送周报/月报到邮箱或 IM

## 6. 测试计划

| 测试类别 | 覆盖内容 | 实际用例数 |
|---|---|---|
| `PeriodReportRecord` 模型 | 字段正确性（含于其他测试中） | — |
| `Database` 扩展 | period_reports CRUD + query_app_usage_stats_range（含于已有 32 个 DB 测试） | — |
| `PromptEngine` 扩展 | build_weekly_prompt（含真实统计） | 1 |
| `ReportGenerator` 扩展 | weekly/monthly 生成 + 持久化 + 空数据降级 + LLM 失败 + 覆盖 | 8 |
| 同步包装 | generate_period_sync + 无效类型异常 | 3 |
| 日期工具函数 | _week_range / _month_range / _week_label / _month_label（含闰年/跨年） | 10 |
| GUI 集成 | 报告类型切换 + 按钮联动（手动验证） | — |
| **合计新增** | | **22** |

### 测试结果
- 全量 164 个测试通过（原 146 + 新增 18），无回归
- 端到端验证：数据库自动建表、period_reports 写入/读取、跨日统计（36 个应用）均正常
