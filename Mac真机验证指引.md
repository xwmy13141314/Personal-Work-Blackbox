# 职迹 WorkTrace macOS 版 — 真机验证指引

> 把 mac版本 拷到 Mac 后，按本指引操作。代码层面已完整，本流程用于验证 + 调试。

## 一、拷贝准备（在 Windows 上操作）

```bash
# 可选：删掉前端源码的 node_modules（153M，Mac 上重新 install，Windows 的不兼容）
# 保留 web_frontend/（已构建，界面可直接起）
```
- 整个 `mac版本/` 文件夹拷到 Mac（U盘 / 局域网 / 压缩 zip）
- **必须保留**：`src/`、`config/`、`web_frontend/`、`requirements-mac.txt`、`启动.command`、`setup.py`、`Info.plist`
- **可删**：`界面优化/优化图设计为macOS风格/node_modules`（省 153M）
- 压缩建议：`cd 职迹 && zip -r mac版本.zip mac版本 -x "*/node_modules/*"`

## 二、Mac 上的操作步骤

### 步骤 1：安装依赖

```bash
cd mac版本
python3 -m venv .venv && source .venv/bin/activate   # 推荐 venv 隔离
pip3 install -r requirements-mac.txt
```
依赖：`pyobjc-framework-Quartz/AppKit/ApplicationServices/CoreFoundation` + `pywebview/pystray/pynput/httpx/yaml/pydantic/markdown`

### 步骤 2：配置 API Key

```bash
echo 'export GLM_API_KEY="你的智谱密钥"' >> ~/.zshrc
source ~/.zshrc
```
（也可在「设置」页 GUI 填写后保存，但推荐环境变量避免明文落盘）

### 步骤 3：首次启动 + 权限授权

```bash
python3 -m src.main
```
1. 程序启动后应弹出 **「需要辅助功能权限」引导弹窗**（MacPermissionGuide）
2. 按引导打开：**系统设置 → 隐私与安全性 → 辅助功能**
3. 在列表中找到运行本程序的项（终端 / Python / .venv 的 python），**勾选启用**（可能需输入密码）
4. 回到程序点「**我已授权，重新检测**」
5. **重启程序**（权限变更后 CGEventTap 需重新创建）

> 或双击 `启动.command`（需先 `chmod +x 启动.command`）

## 三、验证清单（逐项打勾）

| # | 验证项 | 操作 | 预期结果 |
|---|--------|------|---------|
| 1 | 界面启动 | `python3 -m src.main` | 三栏布局 + 日历常驻 |
| 2 | 权限引导 | 首次启动 | 弹「辅助功能权限」引导弹窗 |
| 3 | 键盘采集 | 任意应用打字几分钟后看「活动」 | 当天有会话 + 文本片段 |
| 4 | 窗口追踪 | 切换 2-3 个应用 | 「统计」视图显示应用名 + 时长 |
| 5 | 窗口标题 | 看活动明细 | 窗口标题非空（需辅助功能授权） |
| 6 | 剪贴板 | 复制一段文本 | 活动明细/DB 有剪贴板记录 |
| 7 | 空闲检测 | 5 分钟不操作 | 日志见「进入空闲状态」（阈值 300s） |
| 8 | 中文 IME | 输入中文（如"你好"） | 活动明细出现汉字（⚠️ 见已知限制） |
| 9 | AI 日报 | 报告视图 → 今天 → 生成报告 | LLM 返回 Markdown 日报（需 GLM Key） |
| 10 | 待办看板 | 待办视图 | 三列拖拽 + 统计卡 + 迷你环形图 |
| 11 | 报告导出 | 报告工具栏 HTML 按钮 | 导出单文件 HTML，可浏览器打开 |
| 12 | 时间分布 | 报告生成后 | 自动分析，显示 SVG 环形图 |
| 13 | REST API | config.yaml `rest_api.enabled: true` | `http://127.0.0.1:19527/api/status` 可访问 |

## 四、常见问题排查

| 现象 | 原因 / 解决 |
|------|------------|
| 界面起不来 / 空白 | 检查 `web_frontend/index.html` 是否存在；pywebview 需 WebKit（系统自带） |
| 键盘不采集 / 日志「CGEventTapCreate 返回 None」 | 辅助功能未授权；授权后**重启程序** |
| 窗口标题为空 | 辅助功能未授权，或该应用不暴露 AX（部分 Electron 应用） |
| 中文 IME 无汉字 | AXValue 不可访问（ime_watcher 轮询失效）——**已知限制**，后续优化为 AXObserver |
| `import Quartz` 失败 | `pip3 install pyobjc-framework-Quartz` |
| 全局热键无效 | pynput 也需辅助功能权限 |
| 权限弹窗未出现 | 检查 `check_permissions` 返回（终端看日志）；可能已授权 |
| `启动.command` 双击无效 | `chmod +x 启动.command` |

## 五、日志排查

- **控制台输出**：`python3 -m src.main` 直接看终端（最直接）
- **每日导出**：`data/logs/`（Markdown）
- **关键日志关键词**（出现=对应环节通了）：
  - `CGEventTap 已安装` / `键盘事件监听已启动`
  - `首次按键事件已收到` / `按键转换: keycode=0x__ → char=`
  - `InputBuffer 首次收到字符` / `InputBuffer 提交文本`
  - `WindowTracker 已启动` / `ClipboardMonitor 已启动` / `ImeWatcher 已启动`
  - `IME 中文检测`（ime_watcher 检到汉字）

## 六、已知限制（首版）

- **中文 IME**：轮询 diff 框架，对中间编辑不精确；部分应用 AXValue 不可访问导致汉字采集失效
- **打包**：源码运行为主；py2app 打包 `.app` 为后续（`setup.py` 已就绪，待 `python3 setup.py py2app`）
- **测试**：4 个 Windows 专属 IME 去重测试在 Mac 跳过（正常）

## 七、验证后反馈

若某项异常，请把以下信息带回给我：
1. 哪一项失败 + 现象
2. 终端日志（关键词那段）
3. `data/blackbox.db` 是否有数据（可用 DB Browser 看 sessions/text_segments 表）

我据此修复。祝验证顺利。
