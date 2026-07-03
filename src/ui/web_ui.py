"""pywebview 启动入口：用嵌入 WebView 加载前端，替换 tkinter GUI

主线程 = pywebview mainloop；BlackboxEngine 采集在 daemon 线程。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def run_web():
    """启动 Web UI（pywebview 嵌入窗口）"""
    from src.main import (
        BlackboxEngine,
        ensure_config,
        get_app_root,
        get_bundled_root,
        setup_logging,
    )

    setup_logging()

    # 配置初始化（复刻 run_with_tray / run_gui）
    config_path = get_app_root() / "config" / "config.yaml"
    if not config_path.exists():
        config_path = ensure_config()

    # 引擎初始化但不自动启动采集（待用户点「启动」）
    engine = BlackboxEngine(config_path)

    from src.ui.web_api import BlackboxAPI

    api = BlackboxAPI(engine)

    # 前端产物路径（源码模式 = 项目根；打包模式 = sys._MEIPASS）
    index_path = get_bundled_root() / "web_frontend" / "index.html"
    if not index_path.exists():
        raise RuntimeError(
            f"前端产物不存在: {index_path}\n"
            f"请先在 界面优化/优化图设计为macOS风格/ 执行: npm run build:desktop"
        )

    import webview

    window = webview.create_window(
        title="职迹 WorkTrace",
        url=str(index_path),
        js_api=api,
        width=1100,
        height=720,
        min_size=(900, 600),
    )
    # 窗口关闭时优雅释放引擎（含数据库）
    def _on_closing():
        api.shutdown()
        # pythonnet/.NET CLR 线程会阻止进程正常退出，强制退出确保关闭无残留
        os._exit(0)

    window.events.closing += _on_closing
    logger.info("启动 Web UI（pywebview）")
    webview.start(http_server=True)
