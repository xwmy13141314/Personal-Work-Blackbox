"""本地 REST API 服务器

提供 HTTP 接口访问采集数据，供第三方工具集成。
默认监听 127.0.0.1:19527（仅本地访问，安全考虑）。

启动方式：在配置中启用 rest_api.enabled: true
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

DEFAULT_PORT = 19527


class RestAPIHandler(BaseHTTPRequestHandler):
    """REST API 请求处理器"""

    # 由 RestAPIServer 注入
    engine = None

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=400):
        self._send_json({"error": message}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if not self.engine or not self.engine._db.is_connected:
            self._send_error("引擎未初始化或数据库未连接", 503)
            return

        try:
            # GET /api/status
            if path == "/api/status":
                self._send_json(self._get_status())

            # GET /api/sessions?date=2026-07-06
            elif path == "/api/sessions":
                date = params.get("date", [None])[0]
                sessions = self.engine._db.query_sessions(date=date, limit=500)
                self._send_json([
                    {
                        "id": s.id, "start_time": s.start_time, "end_time": s.end_time,
                        "process_name": s.process_name, "window_title": s.window_title,
                        "active_seconds": s.active_seconds, "idle_seconds": s.idle_seconds,
                        "category": getattr(s, "category", "其他"),
                    }
                    for s in sessions
                ])

            # GET /api/sessions/{id}
            elif path.startswith("/api/sessions/"):
                session_id = int(path.split("/")[-1])
                sess = self.engine._db.query_session_by_id(session_id)
                if not sess:
                    self._send_error("会话不存在", 404)
                    return
                segs = self.engine._db.query_text_segments(session_id)
                self._send_json({
                    "session": {
                        "id": sess.id, "start_time": sess.start_time,
                        "end_time": sess.end_time, "process_name": sess.process_name,
                        "window_title": sess.window_title,
                        "active_seconds": sess.active_seconds,
                    },
                    "segments": [
                        {
                            "timestamp": seg.timestamp,
                            "text": seg.raw_text if not seg.is_filtered else "[已过滤]",
                            "source": seg.source,
                        }
                        for seg in segs
                    ],
                })

            # GET /api/stats?range=today&date=2026-07-06
            elif path == "/api/stats":
                range_type = params.get("range", ["today"])[0]
                date = params.get("date", [None])[0]
                if not date:
                    from datetime import datetime as dt
                    date = dt.now().strftime("%Y-%m-%d")
                stats = self._get_stats(range_type, date)
                self._send_json(stats)

            # GET /api/search?q=keyword
            elif path == "/api/search":
                q = params.get("q", [""])[0]
                if not q:
                    self._send_error("缺少查询参数 q")
                    return
                results = self.engine._db.search_text(q, limit=50)
                self._send_json({"query": q, "results": results})

            # GET /api/dates
            elif path == "/api/dates":
                dates = self.engine._db.query_available_dates(limit=30)
                self._send_json({"dates": dates})

            else:
                self._send_error(f"未知路径: {path}", 404)

        except Exception as e:
            logger.exception("REST API 处理异常")
            self._send_error(f"服务器内部错误: {e}", 500)

    def do_OPTIONS(self):
        """CORS 预检"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        logger.debug("REST API: %s", format % args)

    def _get_status(self):
        from datetime import datetime
        return {
            "running": self.engine._running,
            "version": "3.2.0",
            "today": datetime.now().strftime("%Y-%m-%d"),
        }

    def _get_stats(self, range_type, date):
        from src.ai.report_generator import _week_range, _month_range
        if range_type == "week":
            start, end = _week_range(date)
        elif range_type == "month":
            start, end = _month_range(date)
        else:
            start = end = date
        items = self.engine._db.query_app_usage_stats_range(start, end)
        total = sum(it.get("active_seconds", 0) for it in items)
        return {
            "range": {"start": start, "end": end, "type": range_type},
            "items": items,
            "total_active": total,
        }


class RestAPIServer:
    """REST API 服务器管理器"""

    def __init__(self, engine, port: int = DEFAULT_PORT):
        self._engine = engine
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        if self._server:
            logger.warning("REST API 服务器已在运行")
            return

        RestAPIHandler.engine = self._engine
        self._server = HTTPServer(("127.0.0.1", self._port), RestAPIHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="RestAPI",
        )
        self._thread.start()
        logger.info("REST API 服务器已启动: http://127.0.0.1:%d/api/", self._port)

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            logger.info("REST API 服务器已停止")

    @property
    def is_running(self) -> bool:
        return self._server is not None
