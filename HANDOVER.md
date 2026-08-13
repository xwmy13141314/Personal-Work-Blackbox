# HANDOVER — 职迹 WorkTrace 当前快照

> 新会话第一步：读本文件。当前快照，每次收尾覆盖更新，不堆历史。

## 1. 项目是什么
职迹 WorkTrace：纯本地、隐私优先的个人 AI 工作日志工具。三层采集（键盘含中文 IME + 窗口切换 + 剪贴板）→ 隐私过滤 → LLM 日报/周报/月报 + 待办闭环 + 报告可视化 + 导出。工作目录（唯一主线）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`（git 仓库；`.git` 在此，父级 `职迹\` 不是 git 仓库，环境检测报「非 git」时勿被误导）。

## 2. 当前任务
**v4.3 深度安全风险评估 + 修复（2026-08-13）**：用 grilling 技能做 5 维度风险评估（安全/隐私/死代码/版本规范/运行时健壮性），用户逐条批准修复路线图后执行。**6 项修复全部完成，353 passed 无回归，已 commit（本地未 push）+ 打包 v4.3.1 exe**。仅剩一项用户侧操作：去智谱控制台轮换 API key。

## 3. 已完成进展

**本会话（2026-08-13）安全加固 6 项（已 commit 本地、未 push；v4.3.1 exe 已打包）：**
- [x] **P1-a 安全堵源头**：
  - `privacy_filter.py` sk- 正则升级 `sk-[A-Za-z0-9_-]{20,}`（支持 sk-proj-/下划线/连字符）；`filter_clipboard` 加 context 参数，剪贴板密码关键词检测生效
  - 引入 `config/.secrets.yaml`（已 gitignore）存 api_key；`settings.py` 优先级：环境变量 > .secrets.yaml > config.yaml 占位符
  - `web_api.save_api_config` 重写：model/base_url → config.yaml；api_key → .secrets.yaml；含旧 key 抢救逻辑
  - `main._on_clipboard_change` 调用 filter_clipboard 传入 window_title
- [x] **P1-b 应用黑名单扩充至 17 个**（config.yaml + defaults.py + config.example.yaml 三处同步）
- [x] **P2-a 排序对齐 PRD**：`TodoView.tsx` 加优先级排序（urgent > high > normal > low）
- [x] **P2-b 死代码清理**：删除 `personal_recorder/` 死模块（38 文件 ~2857 行）+ pyproject/spec/README 无效引用
- [x] **P2-c 运行时健壮性**：`keyboard_hook` 看门狗（`_watchdog_loop` 线程崩溃自恢复）+ `main` session 写入 3 次重试；`_tasks` 超时评估后跳过（多 provider 降级串行可能 ~27min，固定超时易误杀）
- [x] **P0 DB 安全审计**：临时脚本扫描 10 表 **0 命中**——DB 从无明文（三层过滤 + 占位符机制源头堵漏），无需清理；脚本用完已删
- [x] **版本号统一 4.3.1**：修正 v4.3 Release（commit `27d689a`）漏 bump 的代码版本号（后端 `_APP_VERSION` / 前端 `APP_VERSION` 原都停在 4.2.0）；前后端统一 4.3.1；README 加 v4.3.1 更新日志
- [x] **测试连接修复**：`test_api_config` 改用 max_tokens=1 轻量请求（原复用 `complete()`，推理模型 glm-4.5-flash 不限 token 单次回复 30s，触发前端超时误判「测试失败」）
- [x] **打包 v4.3.1**：前端 build + PyInstaller → `dist/WorkTrace.exe` **31.52 MB**；前端版本号验证含 4.3.1 ✓；测试基线 353 passed

**关键结论**：DB 干净；唯一泄露面 = git 历史截图 `settings.jpg`（提交 `0b99918`/`b9ee001`，曾含 sk- 片段，v4.2.0 Release 公开过）。工作区已删除该文件，但历史残留无法清理（会破坏 v4.2.0 tag）→ **修复 = 用户轮换 key**。

**更早（v4.3 待办看板 P1-P4 + 双库根治，commit `27d689a` → main，tag `v4.3`）：** 三列拖拽看板 + 进度联动 + AI 推进建议 + 融合环形图 + 逾期顺延 + toast + CSV 导出 + 多维视图；`get_app_root` 双库根治。GitHub Release **v4.3**（`WorkTrace.exe` 31.5MB）。

## 4. 下一步计划
1. **【用户侧·唯一待办】轮换 API key**：登录智谱开放平台控制台 → 作废旧 key → 生成新 key → `[Environment]::SetEnvironmentVariable("GLM_API_KEY","新key","User")`。消除 git 历史截图泄露的唯一有效手段
2. **【可选·对外发布】push + 打 v4.3.1 Release**：本地已 commit + 打包；push 到 GitHub + `gh release create v4.3.1 dist/WorkTrace.exe`。**对外不可逆，需用户确认**（建议轮换 key 后再公开 Release）
3. 待用户试用反馈后定后续开发方向

## 5. 关键文件 & 环境
- 本会话改动文件：`src/processor/privacy_filter.py`、`src/config/settings.py`、`src/ui/web_api.py`、`src/main.py`、`src/collector/keyboard_hook.py`、`config/{config.yaml,config.example.yaml}`、`src/config/defaults.py`、`界面优化/.../TodoView.tsx`、`界面优化/.../AboutView.tsx`、`.gitignore`、`pyproject.toml`、`blackbox.spec`、`README.md`
- 新增：`config/.secrets.yaml`（已 gitignore，运行时按需生成）
- 产物：`dist/WorkTrace.exe`（31.52 MB，v4.3.1，2026-08-13 打包）
- 技术栈：Python 3.13（ctypes WH_KEYBOARD_LL / pywebview 6.2.1 / pywin32）+ React18/TS/Tailwind4/Vite6 + SQLite(WAL) + OpenAI 兼容 LLM（默认智谱 GLM，降级链 ollama→glm→deepseek→openai）
- 工作目录（唯一主线）：`E:\工作\AI CLOUDE\职迹\轻量化键盘记录工具\`
- 运行：`python -m src.main`；打包：`pyinstaller --noconfirm blackbox.spec` → `dist/WorkTrace.exe`
- 前端：`cd 界面优化/优化图设计为macOS风格 && npm run dev`（dev）/ `npm run build:desktop`（→ `web_frontend/`，已 gitignore）
- **数据库（唯一）：`data/blackbox.db`**（exe 与 python 共用，项目根）
- 测试：`python -m pytest -q`（**353 passed**）

## 6. 已知的坑 & 注意事项
- **git 仓库位置**：`.git` 在 `轻量化键盘记录工具\`（项目子目录），父级 `职迹\` 非 git 仓库；Claude 环境检测报「非 git 仓库」是因 primary working dir 在父级，勿被误导
- **版本号历史坑**：v4.3 Release（tag `v4.3`，commit 27d689a）发布时**漏 bump 代码版本号**（后端/前端都停在 4.2.0）。本会话 v4.3.1 已统一修正。**注意 tag 是 `v4.3` 不是 `v4.3.0`**
- **DB 无明文**：扫描确认 10 表 0 命中；密钥经环境变量 / .secrets.yaml 提供，config.yaml 只放占位符
- **pynput 非死代码**：keyboard_hook / input_buffer / hotkey_manager 用 `pynput.keyboard.Key` 做枚举比较（不用 Listener）；blackbox.spec 收集 pynput 子模块是必要的
- **_tasks 不加超时**：report worker 多 provider 降级串行可能 ~27min，固定超时会误杀；LLM 层已有 120s×3 retry 兜底
- **测试连接勿复用 complete()**：推理模型（glm-4.5-flash 等）不限 max_tokens 单次回复 30s+ 会触发前端超时；`test_api_config` 用 max_tokens=1 轻量请求（2-3s 验证 Key），勿走完整 complete
- **别用 ECharts 做报告图**：PDF window.print() 丢图，用纯 SVG
- **LLM 纯文本输出**：结构化提取「prompt 要求 JSON + 后端容错解析」，别依赖 response_format
- **Windows 中文路径下 node fs 删除静默失败**：删中文路径一律用 PowerShell / bash `rm`
- **打包前先关运行中的 WorkTrace.exe**（WinError 5）；windowed exe 子进程必须 CREATE_NO_WINDOW
- **PowerShell 跑 native exe（npm/pyinstaller）的 stderr 会被包成 NativeCommandError**，看似报错实则正常（看 exit code + 最终产物）
- 新 DB 表走 SCHEMA_SQL，新字段走 _migrate_schema（ADD COLUMN）；长时 LLM 操作用 task_id + 轮询（web_api `_tasks`）
- **公开仓库勿含真实数据/key**：`data/` `web_frontend/` 已 gitignore；`settings.jpg` 已从工作区删（历史残留→轮换 key 根治）
- **看板列内排序 = sort_order 主序**（本会话叠加优先级排序）；**progress ↔ status 联动**（`web_api.update_todo` 仅显式传 progress 时触发）；**AI 推进建议只建议不改**（采纳才改）；**多维视图** status 三列可拖 / source 四列只读

## 7. 如何续上
1. 读本文件 + `CLAUDE.md`
2. **当前状态**：v4.3 + 本会话 6 项安全加固完成，353 passed，**已 commit（本地未 push）+ 打包 v4.3.1 exe（`dist/WorkTrace.exe` 31.52MB）**
3. 确认基线：`python -m pytest -q`（应 353 passed）
4. 若用户已轮换 key → P0 彻底闭环；可 push + 发 v4.3.1 Release
5. 若要重打包：关 WorkTrace.exe → build:desktop → `pyinstaller --noconfirm blackbox.spec`
6. 看板相关改 `TodoView.tsx` + `web_api.py` 的 todo_* 接口
