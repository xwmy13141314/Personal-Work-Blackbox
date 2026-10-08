# HANDOVER — 职迹 WorkTrace macOS 版 当前快照

> 新会话第一步：读本文件。当前快照，每次收尾覆盖更新，不堆历史。

## 1. 项目是什么
职迹 WorkTrace macOS 版：纯本地、隐私优先的个人 AI 工作日志工具。由 Windows 版 v4.3 迁移——采集层 macOS 原生重写（CGEventTap/NSWorkspace/NSPasteboard/CGEventSource），核心处理/存储/AI/前端复用。工作目录（唯一主线）：`E:\工作\AI CLOUDE\职迹\mac版本\`。

## 2. 当前任务
**macOS 版首版迁移完成（代码层面）**：目录建立 + 核心代码复制 + 采集层 4 模块 Mac 原生重写 + UI 层适配 + 入口适配 + Mac 配置/依赖/文档。**尚未在真实 Mac 上运行验证**（开发机为 Windows，需 Mac 设备测试）。

## 3. 已完成进展

**P1 目录与复制（2026-08-11）：**
- [x] 建 `mac版本/` 独立目录（与 Windows 版平级）
- [x] 复制可复用代码：src/（含 personal_recorder）、界面优化/、web_frontend/、config/、docs/、tests/、pyproject.toml、app.ico、.gitignore
- [x] 清理 __pycache__/.pytest_cache

**P2 采集层 Mac 原生重写：**
- [x] `keyboard_hook.py`：Quartz CGEventTap（专用线程 + CFRunLoop + ListenOnly），Mac keycode→pynput Key 映射 + CGEventKeyboardGetUnicodeString 取字符；KeyEvent/KeyEventType 完整复用（InputBuffer 零改动）
- [x] `window_tracker.py`：AppKit NSWorkspace.frontmostApplication + AXUIElement 窗口标题；osascript 回退
- [x] `idle_detector.py`：CGEventSourceSecondsSinceLastEventType
- [x] `clipboard_monitor.py`：NSPasteboard.changeCount 轮询；pbpaste 回退

**P3 UI 层与入口适配：**
- [x] `notification.py`：osascript display notification（替代 PowerShell BurntToast）
- [x] `system_tray.py`：`explorer`→`open`
- [x] `web_api.py`：reveal_path `explorer /select`→`open -R`
- [x] `main.py` get_app_root：适配 macOS .app 结构（.app 内只读，数据放 .app 同级）；frozen 时 os.chdir(get_app_root())
- [x] hotkey_manager.py：复用 pynput（Mac Quartz 后端，需辅助功能权限）

**P4 Mac 配置与文档：**
- [x] `app_classifier.py`：补充 Mac 独有应用（Xcode/Finder/Pages/Numbers/Keynote/Messages/Mail/Music/TV/Activity Monitor/System Settings/Pixelmator/Affinity/Logic Pro 等）
- [x] `config/config.yaml`：应用黑名单改 Mac 应用名（1password/keychain access 等）；环境变量示例改 export
- [x] `requirements-mac.txt`：pyobjc-framework-Quartz/AppKit/ApplicationServices + 跨平台依赖
- [x] `启动.command`：Mac 双击启动脚本（自动检查依赖）
- [x] `pyproject.toml`：name=worktrace-mac, version=4.3.0
- [x] `README.md` / `CLAUDE.md` / `HANDOVER.md`：Mac 版文档

**P5 PyObjC API 核对修复（对照官方用法，2026-08-11）：**
- [x] `keyboard_hook.py`：`CGEventKeyboardGetUnicodeString` 改 4 参数 `(event, max, None, None)`，返回值解包 `(length, chars)`（chars 兼容 str/整数序列）；CFRunLoop 导入双保险（CoreFoundation 优先，Quartz fallback）
- [x] `window_tracker.py`：`AXUIElementCopyAttributeValue` 返回值改 `(error, value)` 解包，`error==0` 成功；AX 属性改字符串字面量 `"AXFocusedWindow"`/`"AXTitle"`；import 加 HIServices fallback
- [x] `idle_detector.py`：`kCGEventSourceStateCombinedSessionState`/`kCGAnyInputEventType` 改 getattr fallback
- [x] `requirements-mac.txt`：加 `pyobjc-framework-CoreFoundation`（CFRunLoop 所需）

**P6 Mac 辅助功能权限引导（前后端）：**
- [x] 后端 `web_api.py` 加 `check_permissions()`（AXIsProcessTrusted 检测辅助功能，返回 platform/accessibility_granted/needs_permission）
- [x] 前端 `pywebview.ts` 加 check_permissions 类型 + mock；新建 `MacPermissionGuide.tsx`（授权步骤引导+重新检测+暂不授权）；`App.tsx` 初始化检测，Mac 未授权时显示引导弹窗

**P7 中文 IME 监听框架（AXUIElement 轮询）：**
- [x] 新建 `src/collector/ime_watcher.py`：轮询前台聚焦控件 AXValue，diff 提取新增中文（CJK 范围），经 is_ime_composition 通道发射 KeyEvent（复用 InputBuffer._on_ime_text 拼音去重）
- [x] `main.py` BlackboxEngine 集成：start() 启动 ImeWatcher（darwin+keyboard_enabled），stop() 停止；IME 事件走 _on_keyboard_event
- [x] 注：轮询 diff 对中间编辑不精确，后续可优化为 AXObserver 事件驱动；需真机验证 AXValue 可访问性

**P8 py2app 打包脚本：**
- [x] 新建 `setup.py`（py2app：APP=src/main.py，DATA_FILES=web_frontend+config，includes PyObjC+跨平台依赖）
- [x] 新建 `Info.plist`（bundle id cn.worktrace.app，version 4.3.0，NSAppleEventsUsageDescription，LSMinimumSystemVersion 12.0）
- [x] 图标 app.icns 待准备（从 app.ico 转换）

**P9 测试适配：**
- [x] `test_keyboard_hook.py` 重写：移除 Windows 专属 import（ctypes.wintypes/HC_ACTION 等），IME 去重测试改 @pytest.mark.skip，KeyEvent 属性测试保留（跨平台）
- [x] 修复 `keyboard_hook.py` 的 `keyboard.Key.escape`→`Key.esc`（pynput 枚举名 bug）
- [x] pytest 结果：**349 passed, 4 skipped**（与 Windows 版 353 总数一致）

## 4. 下一步计划
1. **⚠️ 真机验证（最高优先）**：在 Mac 上 `pip3 install -r requirements-mac.txt && python3 -m src.main`，验证：界面启动 / 辅助功能授权引导 / 键盘采集 / 窗口追踪 / 剪贴板 / 空闲 / IME 中文 / AI 日报 / 待办看板
2. **py2app 实际打包**：在 Mac 上 `python3 setup.py py2app`，验证 .app 产物（含权限引导、图标 .icns）
3. **IME 优化**：AXValue 轮询 → AXObserver 事件驱动（kAXValueChangedNotification）
4. **数据目录优化**：打包版数据可迁至 ~/Library/Application Support/WorkTrace/
5. **签名公证**：Developer ID 签名 + notarization（正式发布前）

## 5. 关键文件 & 环境
- 技术栈：Python 3.11+（PyObjC: Quartz/AppKit/ApplicationServices）+ React18/TS/Tailwind4/Vite6 + SQLite(WAL) + OpenAI 兼容 LLM（默认智谱 GLM）+ pywebview + pystray
- 工作目录：`E:\工作\AI CLOUDE\职迹\mac版本\`
- 运行：`python3 -m src.main`（Web GUI 默认）
- 前端：`cd 界面优化/优化图设计为macOS风格 && npm run dev`（dev）/ `npm run build:desktop`（→ `web_frontend/`）
- 数据库：`data/blackbox.db`（源码运行时在项目根 data/）
- Mac 依赖：`requirements-mac.txt`（核心：pyobjc-framework-Quartz/AppKit/ApplicationServices）

## 6. 已知的坑 & 注意事项
- **辅助功能权限是硬门槛**：无权限则 CGEventTapCreate 返回 None（键盘不可用）+ AXUIElement 取不到窗口标题。首启动必须引导授权
- **中文 IME 首版不工作**：首版记录拼音字母，汉字文本待 P5 补
- **KeyEvent 接口不可变**：InputBuffer 依赖一系列 is_xxx 属性，Mac 实现已保持一致，勿改
- **CGEventTap 回调需保持引用**：_tap_callback_ref 存类级别，防 GC 崩溃（类比 Windows HOOKPROC）
- **.app 内只读**：打包后数据不可放 .app 内，get_app_root 返回 .app 同级
- **别用 pynput 做键盘采集**：本版用 CGEventTap 直接写（pynput 仅用于 Key 枚举 + 全局热键）
- **别用 ECharts**：纯 SVG
- **LLM 纯文本输出**：prompt 要求 JSON + 后端容错解析
- **测试未验证**：测试从 Windows 版复制，平台相关用例（如键盘钩子）可能需适配或跳过
- **gui.py（tkinter 回退）未验证**：默认走 web_ui，gui 回退入口 Mac 上未测

## 7. 如何续上
1. 读本文件 + `CLAUDE.md` + `README.md`
2. **在 Mac 上**：`pip3 install -r requirements-mac.txt` → `python3 -m src.main`
3. 首次启动到「系统设置 > 隐私与安全性 > 辅助功能」授权终端/Python
4. 验证采集：打字看活动明细是否有记录、窗口切换是否捕获应用名
5. 后续：IME 补充 / py2app 打包 / 测试适配
