# Personal Recorder (macOS)

> **状态：已隔离** — 此模块是 WorkTrace 的 macOS 早期原型，当前主项目（`src/`）不依赖此目录的任何代码。

## 说明

本目录包含 macOS 平台的早期采集器实现，使用 `objc` + `Quartz` 框架。主项目已通过 `pynput` 实现跨平台采集，此目录保留供未来 macOS 原生支持参考。

## 隔离决策

- PyInstaller 打包配置（`blackbox.spec`）已将 `src.personal_recorder` 添加到 `excludes` 列表
- 主项目 `src/` 中无任何 `import personal_recorder` 语句
- 测试套件不包含此目录的测试

## 未来计划

当启动 macOS 原生支持（第三期规划）时，可参考此目录的实现：
- `macos_recorder.py` — macOS 原生采集器
- `macos_clipboard_monitor.py` — macOS 剪贴板监控

届时将评估是否将此代码合并到主项目的跨平台架构中。
