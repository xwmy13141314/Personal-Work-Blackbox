# 产品需求文档：职迹 · 待办看板增强（v4.3）

> **版本**：v4.3 规划 | **状态**：设计中 | **日期**：2026-08-10
> **关联**：本文档是 `PRD_WorkTrace_v4.md`（主 PRD）的增量，详细规格化「待办看板管理」功能。主 PRD 的功能规格（§4）当时未含待办闭环，本文档一并补齐。

## 1. 背景与目标

### 1.1 现状
职迹已有待办闭环（v4.1.x）：
- AI 从日报/周报/月报提取待办 → 草稿区 → 用户确认入库（`extract_todos_from_report` + `adopt_todos`）
- `todos` 表支持：status（pending/in_progress/done/cancelled）、priority（low/normal/high/urgent）、note、due_date、source_type/source_ref（来源标识）、is_draft、completed_at
- 前端 `TodoView` 为**扁平列表视图**，含草稿确认区、手动增删、CSV 导出

### 1.2 痛点
1. 待办是扁平列表，缺看板化的「阶段感」（待办 / 进行中 / 已完成）
2. 任务来源（哪天报告提的）虽有 `source_ref` 数据，但下钻不便（点击不能定位到对应报告）
3. 任务状态完全手动推进，**没有利用职迹独有的采集 + AI 能力**辅助判断进展

### 1.3 目标
让职迹具备**初步 todo 看板管理能力**，且与 AI + 采集深度融合。不是独立的通用看板，而是「工作流任务镜像」。

## 2. 核心理念：任务镜像

> 职迹看板 = 你工作流的「任务镜像」——任务由 AI 从报告提取，带着来源背书（哪天哪份报告），状态由 AI 结合采集活动辅助推进。**任务「自动喂入 + 有工作痕迹」，而非手动录入。**

通用看板（Trello / 滴答清单）的命门是「得自己一条条建任务」；职迹的优势是**它知道你今天干了什么**（三层采集 + AI 报告），所以它能把任务喂给你。这是融合的核心差异化。

## 3. 范围界定

### 3.1 复用职迹已有（不重做）
| 能力 | 现有实现 |
|---|---|
| 待办 CRUD | `add_todo` / `update_todo` / `delete_todo` / `get_todos` |
| 状态机 | status：pending / in_progress / done / cancelled |
| 优先级 | priority：low / normal / high / urgent |
| 截止日期 | due_date |
| 草稿区 | is_draft + `adopt_todos` |
| AI 提取待办 | `extract_todos_from_report` |
| 来源标识 | source_type / source_ref |
| CSV 导出 | `export_todos` |
| 存储 | SQLite（WAL） |
| 桌面提醒 | `notification.py`（toast） |

### 3.2 新增
看板视图、拖拽交互、进度 0-100%、AI 辅助状态推进、当日概览（融合工作实况）、跨日自动迁移、JSON 全量导入导出、多维视图切换。

### 3.3 明确不做 / 改造
- ❌ 不另起 localStorage —— 用 SQLite（已有，更可靠）
- ❌ 不做纯网页后台提醒 —— 复用桌面 toast（避免 PWA / Service Worker 复杂度）
- ❌ 不引入 `todo_lists` 独立表 —— 「列表」= status 的可视化 + 视图维度切换（避免「列表 vs 状态」二义性）
- 🔄 「已完成」列受保护不可删（对应 status=done，系统状态）

## 4. 功能规格

### 4.1 看板视图（多列状态）
- 预置三列：**待办**（pending）、**进行中**（in_progress）、**已完成**（done，受保护）
- `cancelled` 状态默认折叠/隐藏（可切换显示）
- 列头显示该列任务数
- （P4）支持切换视图维度：按状态 / 按来源报告 / 按应用类别

### 4.2 任务卡片
卡片信息：标题 / 优先级色条（左竖条）/ 截止日期标签 / 来源标签（日报 08/06）/ 进度条（P2 起）。
卡片操作：点击标题编辑、点击来源下钻报告、拖拽。

### 4.3 拖拽交互（`@dnd-kit`）
- **跨列拖拽** = 改 status（拖入「已完成」→ status=done，记 completed_at）
- **同列内拖拽** = 改 sort_order（手动序）
- 拖拽有占位符 + 平滑动画

### 4.4 优先级与排序
- 默认排序：优先级 高→中→低 → 同优先级按 sort_order
- 优先级颜色：urgent 红 / high 橙 / normal 蓝 / low 灰
- 同优先级可拖拽微调序

### 4.5 进度追踪（P2）
- 每任务 progress 0-100%
- 100% 自动转 status=done（可回拖回退）
- 进度条可视化 + 可手动调节

### 4.6 AI 辅助状态推进（差异化大招，P2）
每次生成日报时，AI 同时审视未完成待办，对照当天采集活动，给出**建议**（不自动改）：
- 「跟进样品」今天有大量邮件/微信活动 → 建议标记进行中
- 「整理文档」今天采集到 Word 操作 → 建议推进进度
- 某待办连续多日无相关活动 → 提示可能停滞

用户一键采纳或忽略。

### 4.7 当日概览（融合工作实况，P3）
顶部数据卡片 = 任务统计（总 / 已完成 / 今日待办 / 已超期）**+ 当日专注时长 + 主要应用类别 + 时间分布环形图**（复用 `query_category_stats`）。一眼看全「该做什么 + 实际做了什么」。

### 4.8 跨日自动迁移（P3）
每日首次打开，把 due_date 早于今天且 status=pending 的待办迁入「今日待办」视图；迁移时 AI 可补「昨日进展」备注。

### 4.9 提醒（P3）
逾期 / 即将到期（due_date 前 1 天）触发桌面 toast，每任务每日最多 1 次。复用 `notification.py`。

### 4.10 数据导入导出（P4）
- 已有 CSV（`export_todos`）
- 补 JSON 全量备份（含 status / priority / order / progress 全字段），支持导入恢复

## 5. 数据模型变更

### 5.1 todos 表（复用 + 新增字段）
现有字段（全部复用）：id / title / status / priority / note / due_date / source_type / source_ref / is_draft / created_at / updated_at / completed_at

**新增字段**：
| 字段 | 类型 | 说明 | 阶段 |
|---|---|---|---|
| `sort_order` | REAL | 同列内手动排序（用 REAL 便于两值中间插值，避免整体重排） | P1 |
| `progress` | INTEGER | 0-100 完成进度，默认 0 | P2 |

走 `_migrate_schema`（ADD COLUMN），兼容已有数据。

### 5.2 不新增表
明确不引入 `todo_lists` 表。「列表」= status 可视化 + 视图维度。这避免「任务属于哪个列表」与「任务什么状态」的二义性。

### 5.3 任务 ↔ 报告关联（已有，强化）
`source_type` + `source_ref` 已是天然外键（如 daily_report + "2026-08-06"）。P1 强化前端：点击来源标签 → 跳转报告页对应日期。

## 6. 技术方案

### 6.1 前端
- `TodoView` 升级看板布局（三列 + 卡片）
- 引入 `@dnd-kit/core` + `@dnd-kit/sortable`（拖拽）
- 看板交互多，评估引入 `zustand`（轻量状态管理）
- 样式延续 Tailwind + macOS 风
- 来源下钻：复用现有报告页路由/视图切换

### 6.2 后端
- `database.py`：`_migrate_schema` 加 sort_order / progress；新增批量排序更新方法
- `web_api.py`：
  - 复用 `update_todo` 改 status（拖拽跨列）
  - 新增 `reorder_todos`（批量更新 sort_order）
  - （P2）扩展 AI 推进建议接口

### 6.3 AI
- （P2）扩展 `report_generator` / `todo_extractor` prompt：生成报告时同时输出待办推进建议（JSON，容错解析，复用现有 LLM 纯文本 + 后端解析模式）

## 7. 阶段拆分与验收

### P1 · AI 驱动的状态看板（初步，差异化最小可见）
**目标**：待办从列表升级为看板，任务带来源背书，可拖拽改状态。

**范围**：
1. 看板三列布局（待办 / 进行中 / 已完成）
2. 任务卡片（标题 / 优先级色条 / 截止 / 来源标签）
3. 拖拽：跨列改 status + 同列改 sort_order
4. 来源下钻：点击来源标签 → 跳转对应报告
5. 优先级排序（颜色 + 高→低 + 手动序）
6. 保留现有：草稿区、手动增删、CSV 导出、AI 提取

**验收标准**：
- [ ] 待办页默认展示看板视图（三列状态）
- [ ] 拖拽任务到「已完成」→ status=done + completed_at 记录，持久化（刷新不变）
- [ ] 同列拖拽改顺序 → sort_order 持久化，刷新顺序保持
- [ ] 任务卡片显示来源（报告类型 + 日期），点击能定位到对应报告
- [ ] 优先级颜色区分清晰，排序为 优先级 → 手动序
- [ ] 现有待办（已入库）在看板正确分列显示
- [ ] 无回归：草稿区确认/采纳、手动增删改、CSV 导出、AI 提取均正常
- [ ] `python -m pytest -q` 全绿（新增 sort_order 相关测试）

**数据 / 接口改动**：
- todos 加 `sort_order` 字段（`_migrate_schema`）
- 现有 todos 数据 sort_order 回填（按 created_at 或 id 初始序）
- `web_api.reorder_todos`（批量排序）+ 复用 `update_todo` 改 status

### P2 · AI 辅助推进 + 进度
- progress 字段 + 100% 联动 done
- AI 推进建议（报告生成联动，大招 §4.6）
- 进度条可视化 + 手动调节

### P3 · 概览融合 + 跨日迁移
- 当日工作实况卡片（§4.7，复用 `query_category_stats`）
- 跨日自动迁移（§4.8）
- 桌面 toast 提醒（§4.9）

### P4 · 数据流转 + 多维视图
- JSON 全量导入导出（§4.10）
- 多维视图切换（按状态 / 来源 / 应用类别）

## 8. 关键决策（已定）
1. **AI 辅助推进强度** = 只建议、用户确认（不自动改状态/进度）。保留控制感，符合隐私优先理念。
2. **列表 = status 可视化**（不引入 `todo_lists` 表），消除二义性。
3. **进度 100% 联动 done**，但允许回拖回退。

## 9. 风险与开放问题
- **dnd-kit 工程量**：拖拽细节（占位符 / 动画 / 边界）是体验成败关键，易低估 → P1 重点投入
- **AI 推进建议准确度**（P2）：依赖 prompt 质量 + 采集活动关联，需调优
- **看板性能**：大量待办（>100）时拖拽流畅度 → 必要时分页 / 虚拟列表
- **sort_order 策略**：REAL 中间插值 vs 整数重排，待实现时定（倾向 REAL 减少重排）
