# 职迹 WorkTrace · macOS 版

> 让每一分努力都有迹可循 · 您的私有工作黑盒

个人工作日志采集 + AI 日报工具的 **macOS 移植版**,基于同一项目的 Windows 版。
**纯本地运行(Local Only)**:不联网上传、数据只存本机。

与 Windows 版共用同一前端(React + pywebview)、AI 链路、SQLite 存储、报告生成;
仅**采集层**按 macOS 原生重写,并新增「快照融合」增强(Git / 终端 / 浏览器历史)。

---

## 与 Windows 版的关系

| 层 | 处置 |
|---|---|
| 前端 React 工程(`界面优化/`) | ✅ 完全复用(同一份构建产物 `web_frontend/`) |
| pywebview 桥接 / AI / 存储 / 报告 | ✅ 完全复用 |
| 键盘采集 | 🔧 改用 **CGEventTap**(pynput 在 macOS 26 会因主线程 TSM 调用崩溃) |
| 窗口 / 剪贴板 / 空闲采集 | 🔧 pyobjc 重写(NSWorkspace / NSPasteboard / ioreg) |
| 系统调用 | 🔧 跨平台化(`open` / `osascript`) |
| **快照融合(新增)** | 🆕 接入 Git / Shell / 浏览器历史快照,并入主库与日报 |

---

## macOS 权限

| 权限 | 用途 | 必需 |
|---|---|---|
| **输入监控** | 键盘输入采集(CGEventTap,ListenOnly) | 键盘记录必需 |
| **屏幕录制** | 前台窗口标题(仅取标题,不截屏) | 可选(无则标题为空) |
| 辅助功能 | 全局快捷键 | 可选 |

未授权时对应采集**静默降级**,不影响其余功能。首次授「输入监控」后**必须完全退出 app 重启**才生效。

---

## 快速开始

### 方式一:源码运行
```bash
pip install -r requirements.txt          # macOS 会装 pyobjc,pynput 仅作 KeyEvent 类型兼容
cd 界面优化/优化图设计为macOS风格 && npm install && npm run build:desktop   # 产出 ../../web_frontend
cd ../..
python -m src.main                        # Web GUI(默认)
python -m src.main --no-tray              # 命令行采集模式
```

### 方式二:打包 .app
```bash
pip install pyinstaller
pyinstaller worktrace-mac.spec            # 产出 dist/WorkTrace.app
open dist/WorkTrace.app
```

### 方式三:开机自启
```bash
bash scripts/install.sh                   # 拷到 ~/Applications + 装 LaunchAgent
bash scripts/uninstall.sh                 # 取消自启(保留 .app 与数据)
```

---

## 配置

首次运行自动从 `config/config.example.yaml` 生成 `config/config.yaml`。
**打包版**配置在 `~/Library/Application Support/WorkTrace/config/config.yaml`;**源码版**在 `worktrace-mac/config/config.yaml`。

关键项:
```yaml
ai:
  default_provider: glm                    # 智谱/aliyun/deepseek/kimi/openai/custom 任一
  glm:
    api_key: "你的真实 Key"                # 示例占位需替换,否则日报 401

collection:
  snapshot_enabled: true                   # 快照融合(Git/Shell/浏览器)开关
  snapshot_interval_seconds: 1800          # 快照采集间隔
  snapshot_roots: [~/你的项目目录]          # Git 采集扫描根(不配则只扫当前目录)
```

---

## 数据位置

| | 路径 |
|---|---|
| 打包版 config / DB / 日志 | `~/Library/Application Support/WorkTrace/` |
| 源码版 | `worktrace-mac/config/`、`worktrace-mac/data/` |
| 主库 | `data/blackbox.db`(sessions / text_segments / clipboard_records / window_events / daily_reports / period_reports) |

---

## 架构(采集层)

```
src/collector/
├── platform_factory.py        # 按 sys.platform 分流采集器(避免 macOS import Win32 即崩)
├── keyboard_macos.py          # MacKeyboardAdapter:CGEventTap → BlackboxEngine KeyEvent 契约
├── window_tracker_macos.py    # NSWorkspace 前台 app + Quartz 窗口标题
├── clipboard_monitor_macos.py # NSPasteboard changeCount 轮询
├── idle_detector_macos.py     # ioreg HIDIdleTime
└── snapshot_importer.py       # 快照融合:SystemSnapshotCollector → 主库(F1 映射 + 去重)
```

**快照融合映射**(无时长的瞬时事件):
- 文本主体类(shell 命令 / Git 提交 / 浏览器)→ `text_segments`(进日报数据源)
- 状态点(文件修改 / 前台应用 / 日历)→ `window_events`
- 剪贴板快照 → `clipboard_records`
- 当天内容去重;每天一个 `__snapshot__` 虚拟会话挂载(让 JOIN 进日报)

---

## 隐私

- **纯本地**:采集数据只写本机 SQLite,不联网上传
- 三层过滤:应用黑名单 + 内容脱敏(身份证/银行卡/手机号/邮箱 → `[FILTERED_*]`)+ 隐私模式开关
- 打包 `.app` 不含任何用户数据(审计:无 config.yaml / *.db / 日志)
- 源码包/提交排除 `config/config.yaml`、`data/`、`*.log`(见 `.gitignore`)

---

## 已知限制

- 未签名:分发他人需右键→打开(Gatekeeper);「输入监控」权限绑定进程身份
- 窗口标题需「屏幕录制」权限,缺失则 `window_title` 为空(不影响应用切换检测)
- `gui.py`(tkinter 回退入口)仍含 Windows 残留,macOS 默认走 Web GUI 不涉及

---

## 致谢

基于 [Personal-Work-Blackbox](https://github.com/xwmy13141314/Personal-Work-Blackbox)(Windows 版)移植。
