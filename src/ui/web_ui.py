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

    # 引擎初始化
    engine = BlackboxEngine(config_path)

    from src.ui.web_api import BlackboxAPI

    api = BlackboxAPI(engine)

    # 自动启动采集（3秒后，给 pywebview 窗口加载时间）
    import threading
    import time
    def _auto_start():
        time.sleep(3)
        try:
            engine.start()
            api._is_paused = False
            api._recording_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("采集已自动启动")
        except Exception:
            logger.exception("自动启动采集失败")
    threading.Thread(target=_auto_start, daemon=True, name="AutoStart").start()

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

    # 在主线程安装键盘钩子（必须在 webview.start() 之前）
    # pywebview 的消息循环将处理 WH_KEYBOARD_LL 回调
    try:
        engine.install_keyboard_hook()
        logger.info("键盘钩子已在主线程安装（webview.start 之前）")
    except Exception:
        logger.exception("主线程安装键盘钩子失败")

    # 窗口关闭时优雅释放引擎（含数据库）
    def _on_closing():
        try:
            api.shutdown()
        except Exception:
            logger.exception("shutdown 异常")
        finally:
            # 确保数据库 flush/close 完成后再退出
            import time
            time.sleep(0.5)
            # pythonnet/.NET CLR 线程会阻止进程正常退出，强制退出确保关闭无残留
            os._exit(0)

    window.events.closing += _on_closing
    logger.info("启动 Web UI（pywebview）")
    webview.start(http_server=True)
