"""pywebview 启动入口：用嵌入 WebView 加载前端，替换 tkinter GUI

主线程 = pywebview mainloop；BlackboxEngine 采集在 daemon 线程。

三种 UI 模式（config.yaml → ui.mode）
------------------------------------
- ``embedded``：只用 pywebview 嵌入窗口（原行为）
- ``browser`` ：只用系统默认浏览器 + 托盘图标（最稳，兼容性最好）
- ``auto``    ：先试嵌入窗口，N 秒内没加载出页面就自动切到浏览器 + 托盘（默认）

为什么需要 ``auto`` 兜底
----------------------
部分机器上 WebView2 运行时会出问题：窗口能弹出、但**页面永远加载不完成**
（实测连 ``https://example.com`` 都一样 ``loaded=False``），表现为"全白窗口"。
这时改走系统浏览器是唯一稳定可用的路径 —— 前端本身没问题（Edge 打开同一
地址渲染完整），坏的只是嵌入的 WebView2 环境。
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

_DEFAULT_UI = {
    "mode": "auto",                # auto | embedded | browser
    "embed_timeout_seconds": 20,   # auto 模式下等待嵌入窗口加载的上限
    "disable_webview2_sandbox": True,  # 见下方说明
}


def _bridge_js(token: str) -> str:
    """生成「pywebview.api → HTTP」桥接脚本

    前端通过 `window.pywebview.api` 调后端（见打包产物中的 Rj 函数）：
        window.addEventListener("pywebviewready", () => t(window.pywebview.api))
        setTimeout(() => { if (!window.pywebview?.api) t(Aj) }, 3000)   // Aj = mock
    纯浏览器里没有 pywebview，3 秒后就会退化成 mock 假数据。
    这段脚本用 Proxy 造一个同名 api，把方法调用转成 HTTP POST 打到本机静态服务，
    于是浏览器模式也能读写真实数据。
    """
    return f"""
(function () {{
  var TOKEN = {token!r};
  function call(method, args) {{
    return fetch('/__api__', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', 'X-WorkTrace-Token': TOKEN }},
      body: JSON.stringify({{ method: method, args: args }})
    }}).then(function (r) {{
      if (r.status === 403) throw new Error('bridge forbidden');
      return r.json();
    }}).then(function (j) {{
      if (j && j.error) throw new Error(j.error);
      return j.result;
    }});
  }}
  var api = new Proxy({{}}, {{
    get: function (t, name) {{
      if (typeof name !== 'string') return undefined;
      return function () {{ return call(name, Array.prototype.slice.call(arguments)); }};
    }}
  }});
  // pywebview 真身已注入时不覆盖（嵌入模式优先用真身）
  if (!window.pywebview || !window.pywebview.api) {{
    window.pywebview = window.pywebview || {{}};
    window.pywebview.api = api;
  }}
  window.__worktraceBridge = true;
  try {{ window.dispatchEvent(new Event('pywebviewready')); }} catch (e) {{}}
}})();
"""


def _apply_webview2_flags(ui_cfg: dict) -> None:
    """设置 WebView2 启动参数（必须在 WebView2 环境创建前调用）

    **--no-sandbox 是本机白屏的根治手段（2026-09-14 实测定位）**

    现象：窗口能弹出、WebView2 进程也起了，但页面只完成"取回 index.html"，
    不解析、不执行（子资源与 JS 均无请求），窗口一片空白。

    用"页面主动回调服务器"的方式做铁证对照：
        默认参数                 → 只收到 GET /index.html，无任何后续请求 ❌
        --disable-gpu            → 同上 ❌
        --disable-features=RendererCodeIntegrity → 同上 ❌
        --no-sandbox             → 收到 /__ping(img) 与 /__ping(js) ✅
        --single-process         → 同上 ✅

    结论：**本机 WebView2 的渲染进程沙箱被外部安全软件/策略阻断**，
    渲染进程起不来 → 页面无法解析。关闭沙箱即可恢复正常。

    安全说明：本应用只加载本机 127.0.0.1 的静态页面，不访问外部站点，
    关闭渲染器沙箱的风险有限；如需恢复沙箱，把 config 里
    `ui.disable_webview2_sandbox` 设为 false。
    """
    if not ui_cfg.get("disable_webview2_sandbox", True):
        return
    existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    if "--no-sandbox" in existing:
        return
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        (existing + " ") if existing else ""
    ) + "--no-sandbox"


def _start_static_server(directory, host: str = "127.0.0.1", api=None, token: str | None = None):
    """启动本地静态文件服务，返回 (httpd, port)

    为什么必须这么做（2026-09-14 修复白屏）
    --------------------------------------
    前端是 Vite 打包产物，入口是：
        <script type="module" crossorigin src="./assets/index-xxx.js">
    **ES module 在 `file://` 协议下会因为 origin 为 null 被 CORS 拦死**，
    结果就是"窗口打开但一片空白"（实测：源码模式与打包版都会白屏）。

    pywebview 自带的 `http_server=True` 对"绝对文件路径"的 url 不生效，
    所以这里自己起一个只绑本机的静态服务，让 WebView 走 http:// 加载。

    额外提供：
    - `/__bridge.js`：把 `window.pywebview.api` polyfill 成 HTTP 调用
    - `/__api__`    ：POST 入口，转发到 BlackboxAPI（仅本机 + 随机 token）
    """
    import http.server
    import json
    import socketserver
    import threading as _threading
    from pathlib import Path

    index_file = Path(directory) / "index.html"

    class _Handler(http.server.SimpleHTTPRequestHandler):
        """静态资源 + pywebview API 桥接"""

        def __init__(self, *args, **kwargs):  # noqa: D107
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *args):  # noqa: D102
            logger.debug("[webui] " + fmt, *args)

        def end_headers(self):  # noqa: D102
            # 前端资源不做缓存，避免改完前端后看到旧版本
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _send(self, code: int, body: bytes, ctype: str):  # noqa: D102
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, code: int, obj):  # noqa: D102
            body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def do_GET(self):  # noqa: D102
            path = self.path.split("?", 1)[0]
            if path == "/__bridge.js":
                js = _bridge_js(token or "").encode("utf-8")
                self._send(200, js, "application/javascript; charset=utf-8")
                return
            if path in ("/", "/index.html"):
                try:
                    html = index_file.read_text(encoding="utf-8")
                except Exception:
                    return super().do_GET()
                if "__bridge.js" not in html:
                    inject = '  <script src="/__bridge.js"></script>\n'
                    if "</head>" in html:
                        html = html.replace("</head>", inject + "</head>", 1)
                    else:
                        html = inject + html
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            return super().do_GET()

        def do_POST(self):  # noqa: D102
            if self.path.split("?", 1)[0] != "/__api__":
                self.send_error(404)
                return
            if api is None:
                self._send_json(503, {"error": "bridge disabled"})
                return
            if token and self.headers.get("X-WorkTrace-Token") != token:
                logger.warning("桥接请求 token 校验失败，来源 %s", self.client_address)
                self._send_json(403, {"error": "forbidden"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                method = str(payload.get("method") or "")
                args = payload.get("args") or []
                if not isinstance(args, list):
                    args = [args]
                if method.startswith("_") or not method:
                    self._send_json(400, {"error": f"非法方法名: {method}"})
                    return
                fn = getattr(api, method, None)
                if not callable(fn):
                    self._send_json(400, {"error": f"未知方法: {method}"})
                    return
                self._send_json(200, {"result": fn(*args)})
            except Exception as exc:
                logger.exception("桥接调用失败")
                self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    httpd = socketserver.ThreadingTCPServer((host, 0), _Handler)  # 0 = 随机空闲端口
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    _threading.Thread(
        target=httpd.serve_forever, daemon=True, name="WebUIStatic",
    ).start()
    return httpd, port


def _load_ui_config(config_path) -> dict:
    """读取 ui 配置（缺省时回退到内置默认值）"""
    cfg = dict(_DEFAULT_UI)
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        section = data.get("ui") or {}
        if isinstance(section, dict):
            cfg.update({k: v for k, v in section.items() if v is not None})
    except FileNotFoundError:
        logger.debug("配置文件不存在，ui 使用默认值: %s", config_path)
    except Exception:
        logger.warning("读取 ui 配置失败，使用默认值", exc_info=True)
    return cfg


def _run_browser_mode(engine, api, page_url: str, open_browser: bool = True):
    """浏览器 + 托盘模式（阻塞）

    适用场景：本机 WebView2 不可用（嵌入窗口白屏）时的兜底。
    控制台界面用系统默认浏览器打开，托盘图标提供暂停/隐私/导出/退出等操作。
    """
    import webbrowser

    from src.ui.system_tray import SystemTray

    logger.info("已切换为「浏览器 + 托盘」模式，控制台地址: %s", page_url)
    if open_browser:
        try:
            webbrowser.open(page_url)
        except Exception:
            logger.exception("打开浏览器失败，请手动访问: %s", page_url)

    def on_open_ui():
        try:
            webbrowser.open(page_url)
        except Exception:
            logger.exception("打开浏览器失败: %s", page_url)

    def toggle_pause():
        is_paused = getattr(api, "_is_paused", False)
        try:
            if is_paused:
                engine.resume()
            else:
                engine.pause()
        except Exception:
            logger.exception("切换暂停状态失败")
            return
        api._is_paused = not is_paused

    def activate_privacy():
        try:
            engine.toggle_privacy_mode()
        except Exception:
            logger.exception("切换隐私模式失败")

    def export_today():
        from datetime import datetime

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            engine._exporter.export_daily(today)
        except Exception:
            logger.exception("导出今日日志失败")

    def on_quit():
        try:
            api.shutdown()
        except Exception:
            logger.exception("shutdown 异常")
        finally:
            os._exit(0)

    tray = SystemTray(
        on_pause_resume=toggle_pause,
        on_privacy_mode=activate_privacy,
        on_export=export_today,
        on_quit=on_quit,
        on_open_ui=on_open_ui,
    )
    try:
        tray.run()  # 阻塞
    except (KeyboardInterrupt, SystemExit):
        pass


def run_web():
    """启动 Web UI（嵌入窗口 / 浏览器 + 托盘，按 ui.mode 决定）"""
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

    ui_cfg = _load_ui_config(config_path)
    mode = str(ui_cfg.get("mode", "auto")).strip().lower()
    if mode not in ("auto", "embedded", "browser"):
        logger.warning("未知的 ui.mode=%r，按 auto 处理", mode)
        mode = "auto"
    # 必须在任何 WebView2 创建之前应用（本机白屏的根治参数，见函数说明）
    _apply_webview2_flags(ui_cfg)
    try:
        embed_timeout = float(ui_cfg.get("embed_timeout_seconds", 20))
    except (TypeError, ValueError):
        embed_timeout = float(_DEFAULT_UI["embed_timeout_seconds"])

    # 引擎初始化
    engine = BlackboxEngine(config_path)

    from src.ui.web_api import BlackboxAPI

    api = BlackboxAPI(engine)

    # 共享状态：fallback=已降级到浏览器+托盘；shutting_down=正在正常退出
    # （定义在 _auto_start 之前，避免线程间竞态）
    _state = {"fallback": False, "shutting_down": False}

    # 自动启动采集（3秒后，给 pywebview 窗口加载时间）
    import time

    def _auto_start():
        time.sleep(3)
        if _state["shutting_down"]:
            logger.info("应用正在关闭，跳过自动启动")
            return
        try:
            engine.start()
            api._is_paused = False
            api._recording_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("采集已自动启动")
        except Exception:
            logger.exception("自动启动采集失败")

    threading.Thread(target=_auto_start, daemon=True, name="AutoStart").start()

    # 前端产物路径
    # 1. 开发者场景：优先从项目根目录的 web_frontend 加载（新构建的前端）
    app_root = get_app_root()
    index_path = app_root / "web_frontend" / "index.html"
    # 2. 打包场景：fallback 到 PyInstaller 内嵌的前端
    if not index_path.exists():
        index_path = get_bundled_root() / "web_frontend" / "index.html"
    if not index_path.exists():
        raise RuntimeError(
            f"前端产物不存在: {index_path}\n"
            f"请先在 界面优化/优化图设计为macOS风格/ 执行: npm run build:desktop"
        )

    # 关键：必须通过 http:// 加载（见 _start_static_server 的说明）
    # 直接传本地文件路径会让前端以 file:// 解析，ES module 被 CORS 拦死 → 白屏
    # token 随机生成，仅本机可访问（防止其他本地程序调用后端能力）
    import secrets

    _bridge_token = secrets.token_urlsafe(24)
    _httpd, _port = _start_static_server(
        index_path.parent, api=api, token=_bridge_token,
    )
    page_url = f"http://127.0.0.1:{_port}/{index_path.name}"
    logger.info("前端静态服务已就绪: %s", page_url)

    # 浏览器模式：不创建嵌入窗口
    if mode == "browser":
        logger.info("ui.mode=browser：跳过嵌入窗口，直接使用浏览器 + 托盘")
        _run_browser_mode(engine, api, page_url)
        return

    import webview

    # auto 模式下窗口先隐藏：加载成功才显示。
    # 原因：部分机器 WebView2 损坏，窗口弹出但页面永远加载不出来（白屏），
    # 还会被系统标记为"未响应"。隐藏启动可保证用户永远看不到白屏窗口 ——
    # 要么正常显示，要么直接降级浏览器，中间无难看的过渡态。
    window = webview.create_window(
        title="职迹 WorkTrace",
        url=page_url,
        js_api=api,
        width=1100,
        height=720,
        min_size=(900, 600),
        hidden=(mode == "auto"),
    )
    # 把窗口引用注入 API，供文件保存对话框等使用
    api.bind_window(window)

    # 全局快捷键（v5.4：Web UI 模式下同样可用；Ctrl+Alt+I 唤起窗口并聚焦速记）
    from src.ui.hotkey_manager import HotkeyManager

    def _hk_toggle_pause():
        try:
            if api._is_paused:
                api.resume_recording()
            else:
                api.pause_recording()
        except Exception:
            logger.exception("快捷键切换暂停失败")

    def _hk_export_today():
        try:
            path = engine._exporter.export_daily(time.strftime("%Y-%m-%d"))
            logger.info("日志已导出: %s", path)
        except Exception:
            logger.exception("快捷键导出失败")

    def _hk_toggle_privacy():
        try:
            engine.toggle_privacy_mode()
        except Exception:
            logger.exception("快捷键切换隐私模式失败")

    def _hk_capture_note():
        """Ctrl+Alt+I：唤起主窗口并通知前端打开速记输入"""
        try:
            window.show()
            window.restore()
            window.evaluate_js(
                "window.dispatchEvent(new CustomEvent('wt:open-note-capture'));"
            )
        except Exception:
            logger.exception("速记快捷键触发失败")

    hotkey_manager = HotkeyManager(
        on_toggle_pause=_hk_toggle_pause,
        on_export=_hk_export_today,
        on_privacy_mode=_hk_toggle_privacy,
        on_capture_note=_hk_capture_note,
    )
    hotkey_manager.start()

    # 页面加载完成标志（auto 模式据此判断嵌入窗口是否可用）
    _loaded = threading.Event()
    window.events.loaded += _loaded.set

    # 窗口关闭时优雅释放引擎（含数据库）
    def _on_closing():
        if _state["fallback"]:
            # 降级路径：只是关掉白屏的嵌入窗口，应用继续以「浏览器 + 托盘」运行
            logger.info("嵌入窗口已关闭（降级模式），应用继续在托盘中运行")
            return
        _state["shutting_down"] = True
        logger.info("窗口关闭事件触发，开始关闭引擎")
        try:
            hotkey_manager.stop()
        except Exception:
            logger.exception("注销全局快捷键失败")
        try:
            api.shutdown()
        except Exception:
            logger.exception("shutdown 异常")
        finally:
            time.sleep(0.5)
            os._exit(0)

    window.events.closing += _on_closing

    # auto 模式看门狗：加载成功 → 显示窗口；超时 → 降级浏览器 + 托盘
    if mode == "auto":
        def _watchdog():
            if _loaded.wait(embed_timeout):
                # 加载成功，现在显示窗口（auto 模式创建时是隐藏的）
                # 注意：hidden 创建的窗口 show() 后可能仍是最小化状态，
                # 需再 restore() 一次才能正常出现在桌面上（实测）
                try:
                    window.show()
                except Exception:
                    logger.exception("显示嵌入窗口失败")
                try:
                    window.restore()
                except Exception:
                    logger.debug("恢复窗口尺寸失败（可忽略）", exc_info=True)
                logger.info("嵌入窗口加载完成（%.0fs 内）并已显示", embed_timeout)
                return
            # 先置位，避免 destroy() 触发的 closing 事件把进程直接杀掉
            _state["fallback"] = True
            logger.warning(
                "嵌入窗口在 %.0fs 内未加载完成，判定 WebView2 不可用，"
                "自动降级为「浏览器 + 托盘」模式", embed_timeout,
            )
            try:
                import webbrowser

                webbrowser.open(page_url)
            except Exception:
                logger.exception("打开浏览器失败")
            # destroy 可能因 UI 线程卡死而挂起 —— 看门狗本身是 daemon 线程，
            # 即使挂住也不影响应用继续运行（浏览器已打开）
            try:
                window.destroy()
            except Exception:
                logger.debug("销毁嵌入窗口失败（浏览器已打开，可忽略）", exc_info=True)
            # 再兜一手：若 destroy 挂起导致 webview.start() 不返回，
            # 由本线程直接进入浏览器模式（tray 阻塞在本线程）
            try:
                if not _loaded.wait(3):  # 再给 start() 3 秒返回的机会
                    logger.warning("webview.start() 未随窗口销毁返回，从看门狗线程直接进入浏览器模式")
                    _run_browser_mode(engine, api, page_url, open_browser=False)
            except Exception:
                logger.debug("看门狗兜底失败", exc_info=True)

        threading.Thread(target=_watchdog, daemon=True, name="UIWatchdog").start()

    logger.info("启动 Web UI（pywebview，mode=%s）", mode)

    # WebView2 用户数据目录：**必须给一个真实存在的固定目录**（2026-09-14 定位）
    #
    # pywebview 默认 private_mode=True 且未传 storage_path 时，会把用户数据目录设为
    # tempfile.TemporaryDirectory().name —— 该临时目录对象随即被回收、目录被删除，
    # WebView2 拿到一个不存在的路径 → 初始化失败：
    #   msedgewebview2 进程数 0、页面 loaded 事件永不触发 → 窗口白屏/黑屏。
    # 对照实测：不传 storage_path = 进程 0/加载失败；传固定目录 = 进程 6/加载成功。
    # private_mode=False 同时让前端 localStorage 等设置能持久化。
    _profile_dir = app_root / "data" / "webview_profile"
    _profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(storage_path=str(_profile_dir), private_mode=False)
    except TypeError:
        # 兼容没有 private_mode 参数的 pywebview 版本
        webview.start(storage_path=str(_profile_dir))

    # 走到这里说明嵌入窗口已销毁；若发生了降级，转浏览器 + 托盘模式续命
    if _state["fallback"]:
        _run_browser_mode(engine, api, page_url, open_browser=False)
