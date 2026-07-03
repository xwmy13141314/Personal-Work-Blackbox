# 职迹 WorkTrace

> 让每一分努力都有迹可循 · 您的私有工作黑盒

轻量化个人工作日志采集与 AI 报告工具。采集键盘输入 + 窗口上下文 + 剪贴板，通过 LLM 自动生成日报 / 周报 / 月报。

**纯本地运行（Local Only）· 不联网、不上传、数据只存本机。**

---

## 特性

- **三层采集**：键盘输入 + 窗口切换 + 剪贴板
- **AI 报告**：日报 / 周报 / 月报，支持任意 OpenAI 兼容模型（智谱 GLM、阿里通义、DeepSeek、Kimi、OpenAI、自定义）
- **Web GUI**：macOS 风格三栏界面（pywebview + React），Windows 原生窗口
- **四视图导航**：报告 / 统计 / 活动明细 / 设置
- **常驻日历**：标记有采集（蓝点）与有日报（底色）的日期，周 / 月切换
- **全文搜索**：检索历史键盘输入，按日期 / 应用定位
- **隐私保护**：三层过滤 + 一键隐私模式开关
- **国产模型友好**：设置页下拉预设，填 Key 即用

## 界面预览

**主界面** — 报告 / 统计 / 活动 / 设置 四视图，右栏常驻日历（蓝点 = 有采集、底色 = 有日报）

![主界面](docs/screenshots/overview.jpg)

**设置** — API 配置表单（任意 OpenAI 兼容模型，填 Key 即用）+ 数据目录 + Local Only

![设置](docs/screenshots/settings.jpg)

## 快速开始

### 方式一：直接运行打包版

双击 `dist/WorkTrace.exe`（无需 Python 环境）。

### 方式二：源码运行

```bash
pip install -r requirements.txt
python -m src.main            # Web GUI（默认）
python -m src.main --gui-tk   # tkinter 旧 GUI（回退）
python -m src.main --no-tray  # 命令行模式
```

或双击 `启动.bat`（自动检查依赖并启动）。

## 界面（三栏）

| 栏 | 内容 |
|----|------|
| 左栏 | 导航（报告 / 统计 / 活动 / 设置）+ 搜索框 + Logo |
| 中栏 | 当前视图内容 |
| 右栏 | 录制控制（启动 / 暂停 / 停止 / 隐私）+ 状态 + 日历 |

### 报告视图
日 / 周 / 月报切换，日期导航，点「生成报告」由 LLM 生成（Markdown 渲染）。录制中生成日报会自动包含当前会话内容。

### 统计视图
应用使用时长排行（今日 / 本周 / 本月），条形图 + 总活跃时长。

### 活动明细
按日期浏览会话列表（各应用 + 时长），点开看输入文本片段；左栏搜索框输入关键词，跨日期全文检索历史输入。

### 设置视图
- **AI 配置表单**：选提供商预设 → 填 API Key → 测试连接 → 保存（写入 config.yaml，重启生效）
- 数据目录（打开本地数据文件夹）
- 关于

## 配置

`config/config.yaml`（也可在「设置」页 GUI 编辑，保存后重启生效）。

```yaml
ai:
  default_provider: glm
  glm:
    api_key: "xxx"
    model: "glm-4.5-flash"
    base_url: "https://open.bigmodel.cn/api/paas/v4"

privacy:
  app_blacklist: [1password.exe, keepass.exe, ...]   # 这些应用不记录
  privacy_mode_duration: 30                            # 隐私模式时长（分钟）

collection:
  keyboard_enabled: true
  clipboard_enabled: true
  idle_threshold: 300                                  # 空闲阈值（秒）
```

支持的 AI 提供商均为 OpenAI 兼容协议，新增厂商只需在 `PROVIDER_PRESETS`（前端）加一条 + config 加字段。

## 隐私保护

三层架构：

1. **应用黑名单**（自动）：密码管理器等窗口前台时完全不记录
2. **内容脱敏**（自动）：身份证 / 银行卡 / 手机号 / 邮箱 / 密码上下文 → `[FILTERED_*]`
3. **隐私模式**（手动）：右栏按钮一键开关，开启期间全部停录（30 分钟自动恢复或随时点关）

所有数据仅存本机 `data/blackbox.db`，不联网上传。

## 数据

- `data/blackbox.db` — SQLite 主库（sessions / text_segments / clipboard_records / window_events / daily_reports / period_reports）
- `data/logs/` — 每日 Markdown 导出 + AI 报告
- `data/backup_历史库_*/` — 历史库归档（永不删）

## 打包

```bash
# 1. 构建前端
cd 界面优化/优化图设计为macOS风格
npm install
npm run build:desktop      # 输出到项目根 web_frontend/

# 2. 打包 exe
cd ../..
pyinstaller --noconfirm blackbox.spec
# 产物：dist/WorkTrace.exe（含 ∞ 图标）
```

重新打包需先关闭运行中的 `WorkTrace.exe`（Windows 文件锁）。

## 项目结构

```text
src/
├── main.py              # 主入口 / BlackboxEngine
├── collector/           # 键盘 / 窗口 / 剪贴板 / 空闲采集
├── processor/           # 输入缓冲 / 隐私过滤 / 会话管理
├── storage/             # SQLite + Markdown 导出
├── ai/                  # LLM 客户端 / 提示词 / 报告生成
├── ui/                  # web_ui / web_api（pywebview 桥接）
└── personal_recorder/   # （可选）事件化记录器模块，见下
界面优化/优化图设计为macOS风格/   # React 前端源码
web_frontend/                    # 前端构建产物（打包输入）
config/                          # 配置文件
data/                            # 数据 + 日志 + 归档
命名与图标/                      # 品牌资源（命名稿 + 图标源图）
```

## Personal Recorder 模块（可选）

仓库另含 `src/personal_recorder` 事件化记录器（v3.0 引入），支持统一事件模型、inbox 接入、Git / Shell / 浏览器历史快照、macOS 采集、`.ics` 导出等。与 Web GUI 并行，互不依赖。

```bash
PYTHONPATH=src python3 -m personal_recorder init-db
PYTHONPATH=src python3 -m personal_recorder build-day --date 2026-07-03
```

详情见 `CHANGELOG.md` 的 v3.0 条目。

## 更新日志

详见 `CHANGELOG.md`。

### v3.1.0 (2026-07-03) — 职迹 WorkTrace：Web GUI + 品牌化 + 多模型

- 全新 Web GUI（pywebview + React）替代 tkinter，macOS 风格三栏
- 四视图导航（报告 / 统计 / 活动明细 / 设置）+ 全文搜索
- 常驻日历（圆角，撑满，双标记有采集 / 有日报，周月跳转）
- 设置页 API 配置可编辑表单 + 通用 OpenAI 兼容 Provider（智谱 / 阿里 / Kimi / DeepSeek / OpenAI / 自定义）+ 测试连接
- 隐私模式改真·开关（可随时关）
- 录制中生成日报 flush 修复
- 品牌化：改名「职迹 WorkTrace」，∞ 莫比乌斯环图标（圆角），Slogan，Local Only 标注
- 数据：5 库分叉合并为单一权威主库，历史库归档，清理冗余 188M

### v3.0 (2026-06-07) — Personal Recorder 升级模块

见 `CHANGELOG.md`。

### v2.3 (2026-05-27) — 周报 / 月报 + 目录整理 + 安全加固

- 周报与月报功能
- 目录整理与数据库合并
- 打包与安全加固
