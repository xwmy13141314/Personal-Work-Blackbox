"""py2app 打包配置 — 职迹 WorkTrace macOS 版

构建步骤：
  1. 构建前端：
       cd 界面优化/优化图设计为macOS风格
       npm install && npm run build:desktop   # 输出到项目根 web_frontend/
  2. 准备图标（可选）：将 app.ico 转为 app.icns（可用 iconutil 或在线工具）
  3. 安装打包依赖：
       pip3 install py2app
  4. 打包：
       cd 项目根
       python3 setup.py py2app
  5. 产物：dist/WorkTrace.app

重新打包需先关闭运行中的 WorkTrace.app（文件锁）。
首次启动 .app 需在「系统设置 > 隐私与安全性 > 辅助功能」授权（键盘监听+窗口标题）。

注意：
  - py2app 默认不会自动收集 PyObjC 框架的全部子模块，includes 列表已显式声明
  - 若运行时缺模块，按报错追加到 includes
  - 数据目录解析见 main.py:get_app_root（.app 内只读，数据放 .app 同级 data/）
"""

import os
from setuptools import setup

APP = ['src/main.py']

# 数据文件：前端构建产物 + 配置（含 config.yaml 与 prompts/）
DATA_FILES = [
    'web_frontend',
    'config',
]

OPTIONS = {
    'argv_emulation': False,          # 不模拟 argv（避免双击文件传参干扰）
    'plist': 'Info.plist',
    # 与前端 src/assets/logo.png 同源生成，保证 Finder/Dock 与界面内 Logo 一致。
    'iconfile': 'app.icns',
    # 这些包仅在用户选择对应本地文档后才动态导入；显式列为 package，确保 py2app 收录。
    # certifi 包含 HTTPS 根证书；py2app 会以包资源形式一并收录。
    'packages': [
        'pypdf', 'docx', 'certifi',
        # httpx 的异步网络栈；仅包含 httpx 本体会在运行时缺 anyio._backends。
        'httpx', 'httpcore', 'anyio', 'h11', 'idna',
    ],
    'includes': [
        # PyObjC 框架
        'Quartz', 'AppKit', 'ApplicationServices', 'CoreFoundation', 'Vision',
        # 跨平台依赖
        # pywebview 的发行包名为 pywebview，实际 import 名为 webview。
        'webview', 'pystray', 'PIL',
        'httpx', 'httpcore', 'anyio', 'anyio._backends._asyncio', 'h11', 'idna', 'sniffio',
        # 报告 HTML 导出会按名称动态加载 Markdown 扩展，必须全部显式收录。
        'certifi', 'yaml', 'pydantic', 'markdown', 'markdown.extensions',
        'markdown.extensions.tables', 'markdown.extensions.fenced_code',
        'markdown.extensions.sane_lists', 'pypdf', 'docx',
    ],
    'excludes': ['tkinter', 'pytest', 'unittest'],
}

setup(
    app=APP,
    name='WorkTrace',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
