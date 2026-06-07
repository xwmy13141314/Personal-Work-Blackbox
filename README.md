# Personal Work Blackbox

> 轻量化个人工作日志自动化采集与 AI 报告工具，现已扩展为可独立运行的 `Personal Recorder` 个人记录器升级版。

这个仓库现在包含两条能力线：

- 原始 `Blackbox` 主应用：Windows 端窗口、键盘、剪贴板采集，生成日报、周报、月报
- 新增 `Personal Recorder` 模块：统一事件模型、历史数据迁移、实时 inbox 接入、重要事项提取、待办提取、日历导出、隐私分层存储

## 当前结构

### 1. Blackbox 主应用

保留原有结构和入口：

```bash
python -m src.main --gui
python -m src.main --no-tray
```

它适合：

- Windows 桌面行为采集
- 原有 GUI 使用方式
- 直接生成 Blackbox 风格日报、周报、月报

### 2. Personal Recorder 升级模块

新增模块位置：

- `src/personal_recorder`

它适合：

- 统一事件化存储
- 从原 Blackbox SQLite 历史数据迁移
- 通过 inbox 接更多来源
- 重点事项、待办、日程候选提取
- 更明确的隐私边界

## 快速开始

### 方式一：运行原 Blackbox

```bash
pip install -r requirements.txt
python -m src.main --gui
```

### 方式二：运行 Personal Recorder

建议在仓库根目录执行：

```bash
PYTHONPATH=src python3 -m personal_recorder init-db
PYTHONPATH=src python3 -m personal_recorder import-sample
PYTHONPATH=src python3 -m personal_recorder build-day --date 2026-06-07
PYTHONPATH=src python3 -m personal_recorder build-week --week-start 2026-06-01
PYTHONPATH=src python3 -m personal_recorder export-ics --date 2026-06-07
```

如果你用 `pip install -e .` 安装，也可以直接运行：

```bash
personal-recorder init-db
```

## Personal Recorder 功能

### 已实现

- SQLite 数据库初始化
- 统一 `events` 模型
- 手动事件记录
- Blackbox SQLite 历史数据迁移
- inbox 实时接入
- Windows Blackbox 实时桥接
- 键盘事件缓冲提交
- 重要事项提取
- 待办和日期提取
- 日报、周报生成
- `.ics` 日历导出
- 敏感信息规则脱敏
- 原始文本与脱敏文本分层存储

### 命令示例

```bash
PYTHONPATH=src python3 -m personal_recorder add-manual \
  --title "今天和客户确认上线计划" \
  --content "周二 15:00 复盘，上线前补测试" \
  --tags work,meeting

PYTHONPATH=src python3 -m personal_recorder import-blackbox-db \
  --db-path /path/to/blackbox.db

PYTHONPATH=src python3 -m personal_recorder push-event \
  --source manual \
  --content "今天确认周报结构，明天补日程同步" \
  --tags important,todo

PYTHONPATH=src python3 -m personal_recorder watch-inbox --once
```

### Windows 实时桥接

如果你在 Windows 上运行原始 Blackbox 采集器，可以直接桥接到新模块：

```bash
PYTHONPATH=src python3 -m personal_recorder bridge-blackbox \
  --blackbox-src D:/Personal-Work-Blackbox/src \
  --keyboard-buffer-timeout 3 \
  --keyboard-buffer-max-length 120
```

当前桥接范围：

- `WindowTracker`
- `ClipboardMonitor`
- `KeyboardHook` 键盘事件缓冲提交
- 手工文本桥接 `emit-blackbox-text`

## 隐私与存储

Personal Recorder 当前已经加入第一版隐私保护：

- `content` 保存原始文本，仅本地保留
- `content_redacted` 保存规则脱敏后的文本
- `content_summary` 默认基于脱敏文本生成
- `storage_tier` 标记为 `private` 或 `restricted`
- 报告和待办提取默认使用脱敏文本

当前会脱敏的内容包括：

- 手机号
- 邮箱
- 银行卡号样式文本
- 身份证号样式文本
- 常见 `token`、`secret`、`password`、`api_key` 键值
- 带敏感查询参数的 URL

## 项目结构

```text
src/
├── main.py
├── collector/
├── processor/
├── storage/
├── ai/
├── ui/
└── personal_recorder/
    ├── bridges/
    ├── collectors/
    ├── config/
    ├── exporters/
    ├── models/
    ├── processors/
    ├── reports/
    ├── repositories/
    └── services/
```

示例数据：

- `examples/sample_events.json`
- `examples/inbox_event.json`

## 原 Blackbox 保留能力

原仓库能力仍然保留：

- Windows 桌面采集
- GUI 与托盘
- 周报/月报生成
- PyInstaller 打包
- 既有测试集

原入口、配置、打包文件均未删除。

## 建议使用方式

如果你只是继续用原 Windows 采集 GUI：

- 继续使用 `src.main`

如果你想把这个仓库升级成个人知识和行为记录器：

- 用 `src.main` 或原采集器采集
- 用 `personal_recorder import-blackbox-db` 迁移历史
- 用 `push-event` / `watch-inbox` 接更多来源
- 用 `build-day` / `build-week` 生成更结构化的日报周报

## 当前边界

当前升级版还没有完成这些部分：

- 更强的敏感应用黑名单联动
- 原始文本单独加密存储
- 项目自动分类训练
- 人工纠偏界面
- 本地模型摘要层

## 兼容说明

- `src.main` 仍是原应用入口
- `personal_recorder` 是并行新增模块，不覆盖原 GUI 工作流
- 新模块默认把数据写到它自己的 `data/` 目录结构中

## 更新日志

### v3.0 (2026-06-07) — Personal Recorder 升级模块接入

新增：

- `src/personal_recorder` 事件化记录模块
- Blackbox SQLite 历史数据迁移
- inbox 实时接入与 watcher
- Windows 实时桥接
- 键盘事件缓冲提交
- 日报、周报、`.ics` 日历导出
- 规则化重要事项与待办提取
- 脱敏文本和原始文本分层存储

保留：

- 原 Blackbox Windows GUI 采集能力
- 原有周报/月报生成链路
- 原有仓库结构和入口

### v2.3 (2026-05-27) — 周报/月报 + 目录整理 + 安全加固

- 周报与月报功能
- 目录整理
- 数据库合并
- 打包与安全加固
