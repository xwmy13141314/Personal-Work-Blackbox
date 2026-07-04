# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（macOS）— 产出 dist/WorkTrace.app

Mac 化要点（相对 Windows 版 blackbox.spec）：
- 移除 pythonnet / clr_loader（pywebview 在 macOS 用 WebKit，后端是 pyobjc，无需 .NET）
- hiddenimports 补 pyobjc frameworks（AppKit/Quartz/WebKit）+ pynput/pystray/webview 子模块
- pathex 同时含项目根与 src：让 PyInstaller 能解析 personal_recorder（snapshot_importer
  运行时用 `personal_recorder.xxx` 绝对导入，经 sys.path 注入 src 使其成为顶层包）
- icon 用 app.icns；BUNDLE 段生成 .app
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ROOT = Path('.').resolve()

# pywebview 及依赖子模块/数据
webview_submodules = (
    collect_submodules('webview')
    + collect_submodules('bottle')
    + collect_submodules('proxy_tools')
)
webview_datas = collect_data_files('webview')

# personal_recorder 快照采集模块（运行时按顶层包 personal_recorder 导入）
pr_submodules = collect_submodules('personal_recorder')

a = Analysis(
    ['src/main.py'],
    pathex=[str(ROOT), str(ROOT / 'src')],
    datas=[
        ('web_frontend', 'web_frontend'),
        ('config/config.example.yaml', 'config'),
    ] + webview_datas,
    hiddenimports=[
        # 采集层
        'pynput', 'pynput.keyboard', 'pynput.mouse', 'pynput._vendor',
        # 托盘 / 图像
        'pystray', 'PIL', 'PIL.Image', 'PIL.ImageDraw',
        # 工具
        'yaml', 'httpx', 'pydantic',
        # pyobjc frameworks（macOS 采集 + pywebview WebKit 后端）
        'AppKit', 'Quartz', 'WebKit', 'Foundation', 'Cocoa',
        'CoreFoundation', 'ApplicationServices',
        'webview.platforms.cocoa',
        # 本项目
        'src.collector', 'src.collector.platform_factory',
        'src.collector.window_tracker_macos', 'src.collector.clipboard_monitor_macos',
        'src.collector.idle_detector_macos', 'src.collector.keyboard_hook',
        'src.collector.snapshot_importer',
        'src.processor', 'src.processor.input_buffer',
        'src.processor.privacy_filter', 'src.processor.session_manager',
        'src.storage', 'src.storage.database', 'src.storage.models',
        'src.storage.markdown_exporter',
        'src.ai', 'src.ai.llm_client', 'src.ai.prompt_engine',
        'src.ai.report_generator',
        'src.ui', 'src.ui.web_ui', 'src.ui.web_api', 'src.ui.system_tray',
        'src.ui.notification', 'src.ui.hotkey_manager',
        'src.config', 'src.config.settings', 'src.config.defaults',
    ] + webview_submodules + pr_submodules + ['bottle', 'proxy_tools'],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'notebook', 'IPython', 'pytest', 'pytest_asyncio',
        # Windows 专有（避免误打包）
        'win32clipboard', 'win32con', 'win32api', 'win32gui', 'pythonnet', 'clr_loader',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorkTrace',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # macOS 不建议 upx（Gatekeeper 易误报）
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.icns',
)

app_bundle = BUNDLE(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='WorkTrace.app',
    icon='app.icns',
    bundle_identifier='com.worktrace.mac',
    info_plist={
        'CFBundleName': 'WorkTrace',
        'CFBundleDisplayName': '职迹 WorkTrace',
        'CFBundleShortVersionString': '3.1.0',
        'NSAppleEventsUsageDescription': '用于采集前台应用与窗口标题以生成工作日报。',
        'NSCameraUsageDescription': '本应用不使用摄像头，仅为满足 macOS 权限声明。',
        'LSUIElement': False,  # 显示 Dock 图标
    },
)
