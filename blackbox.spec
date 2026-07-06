# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置文件

使用方法：
    pip install pyinstaller
    pyinstaller blackbox.spec
"""

import sys
from pathlib import Path

# pywebview + pythonnet(.NET 后端) 依赖收集
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

block_cipher = None

# 项目根目录
ROOT = Path('.')

# 收集 pywebview 及 Windows .NET 后端（pythonnet/clr_loader）的子模块、数据、动态库
webview_submodules = collect_submodules('webview')
webview_datas = collect_data_files('webview')
dotnet_submodules = collect_submodules('pythonnet') + collect_submodules('clr_loader')
dotnet_libs = collect_dynamic_libs('clr_loader') + collect_dynamic_libs('pythonnet')
# 收集 pywin32 的动态库（pywintypes310.dll, pythoncom310.dll 等）
pywin32_libs = collect_dynamic_libs('pywin32') + collect_dynamic_libs('win32')

a = Analysis(
    ['src/main.py'],
    pathex=[str(ROOT)],
    binaries=dotnet_libs + pywin32_libs,
    datas=[
        ('config/config.example.yaml', 'config'),
        ('web_frontend', 'web_frontend'),
    ] + webview_datas,
    hiddenimports=[
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'pynput._vendor',
        'win32clipboard',
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'win32event',
        'win32security',
        'win32profile',
        'pywintypes',
        'pythoncom',
        'pystray',
        'bottle',
        'proxy_tools',
        'proxy_tools._proxy12',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'yaml',
        'httpx',
        'pydantic',
        'src.collector',
        'src.collector.keyboard_hook',
        'src.collector.window_tracker',
        'src.collector.clipboard_monitor',
        'src.collector.idle_detector',
        'src.processor',
        'src.processor.input_buffer',
        'src.processor.privacy_filter',
        'src.processor.session_manager',
        'src.processor.app_classifier',
        'src.processor.focus_mode',
        'src.processor.pinyin_converter',
        'src.storage',
        'src.storage.database',
        'src.storage.models',
        'src.storage.markdown_exporter',
        'src.storage.data_exporter',
        'src.ai',
        'src.ai.llm_client',
        'src.ai.prompt_engine',
        'src.ai.report_generator',
        'src.ui',
        'src.ui.gui',
        'src.ui.system_tray',
        'src.ui.hotkey_manager',
        'src.ui.notification',
        'src.ui.web_ui',
        'src.ui.web_api',
        'src.ui.rest_api',
        'src.config',
        'src.config.settings',
        'src.config.defaults',
        # 数据库加密（可选，未安装时 PyInstaller 会警告但不影响打包）
        'pysqlcipher3',
        'pysqlcipher3.dbapi2',
        'sqlcipher3',
    ] + webview_submodules + dotnet_submodules + [
        'bottle',
        'proxy_tools',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'notebook',
        'IPython',
        'pytest',
        'pytest_asyncio',
        # 排除 personal_recorder（macOS 专用模块，不影响 Windows 打包）
        'src.personal_recorder',
        'src.personal_recorder.*',
        # 排除未使用的大型库
        'tkinter',
        'unittest',
        'xmlrpc',
        'pydoc',
        'doctest',
        'lib2to3',
        'setuptools',
        'pip',
        'wheel',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WorkTrace',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # 不压缩 .NET 运行时 DLL（会导致崩溃）
        'pythonnet',
        'clr_loader',
        'python310.dll',
        'pywintypes310.dll',
        'pythoncom310.dll',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)
