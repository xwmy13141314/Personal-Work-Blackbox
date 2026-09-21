"""Web UI 启动层测试：ui 配置解析 + WebView2 参数 + 静态服务 + pywebview API 桥接

覆盖 2026-09-14 白屏修复引入的能力：
1. `ui.mode` 配置解析（auto / embedded / browser）
2. WebView2 启动参数（--no-sandbox，本机白屏的根治手段）
3. index.html 注入桥接脚本、`/__bridge.js` 可访问
4. `/__api__` POST 转发（token 校验 + 私有方法拦截）
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from src.ui.web_ui import (
    _DEFAULT_UI,
    _apply_webview2_flags,
    _bridge_js,
    _load_ui_config,
    _start_static_server,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "web_frontend"
_FLAG_ENV = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"


# ==================== 0. WebView2 启动参数（白屏根治）====================

class TestWebview2Flags:
    """--no-sandbox：本机 WebView2 渲染进程沙箱被安全软件阻断导致白屏的根治参数"""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        monkeypatch.delenv(_FLAG_ENV, raising=False)

    def test_sets_no_sandbox_by_default(self):
        _apply_webview2_flags({})
        assert "--no-sandbox" in os.environ[_FLAG_ENV]

    def test_explicit_true(self):
        _apply_webview2_flags({"disable_webview2_sandbox": True})
        assert "--no-sandbox" in os.environ[_FLAG_ENV]

    def test_explicit_false_keeps_sandbox(self):
        _apply_webview2_flags({"disable_webview2_sandbox": False})
        assert _FLAG_ENV not in os.environ

    def test_does_not_duplicate_flag(self):
        os.environ[_FLAG_ENV] = "--no-sandbox"
        _apply_webview2_flags({})
        assert os.environ[_FLAG_ENV].count("--no-sandbox") == 1

    def test_preserves_existing_args(self):
        os.environ[_FLAG_ENV] = "--disable-gpu"
        _apply_webview2_flags({})
        value = os.environ[_FLAG_ENV]
        assert "--disable-gpu" in value and "--no-sandbox" in value

    def test_default_ui_enables_the_fix(self):
        assert _DEFAULT_UI["disable_webview2_sandbox"] is True


# ==================== 1. ui 配置解析 ====================

class TestUiConfig:
    def test_defaults_when_file_missing(self, tmp_path):
        cfg = _load_ui_config(tmp_path / "nope.yaml")
        assert cfg == _DEFAULT_UI
        assert cfg["mode"] == "auto"

    def test_reads_ui_section(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("ui:\n  mode: browser\n  embed_timeout_seconds: 3\n", encoding="utf-8")
        cfg = _load_ui_config(p)
        assert cfg["mode"] == "browser"
        assert cfg["embed_timeout_seconds"] == 3

    def test_partial_section_falls_back(self, tmp_path):
        """只写 mode 时，超时时间应回落到默认值"""
        p = tmp_path / "c.yaml"
        p.write_text("ui:\n  mode: embedded\n", encoding="utf-8")
        cfg = _load_ui_config(p)
        assert cfg["mode"] == "embedded"
        assert cfg["embed_timeout_seconds"] == _DEFAULT_UI["embed_timeout_seconds"]

    def test_none_value_does_not_override(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("ui:\n  mode:\n", encoding="utf-8")
        assert _load_ui_config(p)["mode"] == _DEFAULT_UI["mode"]

    def test_other_sections_ignored(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("collection:\n  keyboard_enabled: false\n", encoding="utf-8")
        assert _load_ui_config(p) == _DEFAULT_UI

    def test_broken_yaml_falls_back(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("ui: [unclosed\n", encoding="utf-8")
        assert _load_ui_config(p) == _DEFAULT_UI

    def test_real_project_config(self):
        cfg = _load_ui_config(PROJECT_ROOT / "config" / "config.yaml")
        assert cfg["mode"] in ("auto", "embedded", "browser")
        assert float(cfg["embed_timeout_seconds"]) > 0


# ==================== 2. 桥接脚本 ====================

class TestBridgeJs:
    def test_contains_token(self):
        assert "TOKEN = 'abc123'" in _bridge_js("abc123")

    def test_polyfills_pywebview_api(self):
        js = _bridge_js("t")
        assert "window.pywebview" in js
        assert "pywebviewready" in js
        assert "Proxy" in js

    def test_posts_to_bridge_endpoint(self):
        assert "'/__api__'" in _bridge_js("t")


# ==================== 3. 静态服务 + API 桥接 ====================

class _StubApi:
    def get_status(self):
        return {"is_running": True}

    def echo(self, value):
        return value

    def _private(self):  # pragma: no cover - 不应被调用
        raise AssertionError("私有方法不应该被桥接调用")


@pytest.fixture()
def server():
    if not (FRONTEND_DIR / "index.html").exists():
        pytest.skip("web_frontend 产物不存在")
    httpd, port = _start_static_server(FRONTEND_DIR, api=_StubApi(), token="tok")
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def _post(base, payload, token="tok"):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-WorkTrace-Token"] = token
    req = urllib.request.Request(
        base + "/__api__", method="POST",
        data=json.dumps(payload).encode("utf-8"), headers=headers,
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))


class TestStaticServer:
    def test_index_html_injects_bridge(self, server):
        html = urllib.request.urlopen(server + "/index.html", timeout=10).read().decode("utf-8")
        assert "__bridge.js" in html

    def test_bridge_js_served(self, server):
        js = urllib.request.urlopen(server + "/__bridge.js", timeout=10).read().decode("utf-8")
        assert "window.pywebview" in js
        assert "TOKEN = 'tok'" in js

    def test_static_asset_reachable(self, server):
        html = urllib.request.urlopen(server + "/index.html", timeout=10).read().decode("utf-8")
        assert "<script" in html

    def test_api_call_ok(self, server):
        assert _post(server, {"method": "get_status", "args": []})["result"] == {"is_running": True}

    def test_api_call_with_args(self, server):
        assert _post(server, {"method": "echo", "args": ["你好"]})["result"] == "你好"

    def test_api_rejects_missing_token(self, server):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(server, {"method": "get_status", "args": []}, token=None)
        assert e.value.code == 403

    def test_api_rejects_wrong_token(self, server):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(server, {"method": "get_status", "args": []}, token="bad")
        assert e.value.code == 403

    def test_api_rejects_private_method(self, server):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(server, {"method": "_private", "args": []})
        assert e.value.code == 400

    def test_api_rejects_unknown_method(self, server):
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(server, {"method": "no_such_method", "args": []})
        assert e.value.code == 400

    def test_unknown_path_is_404(self, server):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(server + "/__api__", timeout=10)
        assert e.value.code in (404, 405)


class TestServerWithoutApi:
    def test_bridge_disabled(self):
        if not (FRONTEND_DIR / "index.html").exists():
            pytest.skip("web_frontend 产物不存在")
        httpd, port = _start_static_server(FRONTEND_DIR)
        try:
            with pytest.raises(urllib.error.HTTPError) as e:
                _post(f"http://127.0.0.1:{port}", {"method": "get_status", "args": []})
            assert e.value.code == 503
        finally:
            httpd.shutdown()
            httpd.server_close()
