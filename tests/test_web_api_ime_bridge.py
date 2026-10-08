from src.ui.web_api import BlackboxAPI


class _Watcher:
    def __init__(self, source: str):
        self.source = source

    def status(self):
        return {"source": self.source, "state": "focused_unavailable"}


class _Engine:
    def __init__(self, source: str):
        self._ime_watcher = _Watcher(source)
        self.events = []

    def _on_keyboard_event(self, event):
        self.events.append(event)


def _api_for(source: str):
    api = BlackboxAPI.__new__(BlackboxAPI)
    api._engine = _Engine(source)
    return api


def test_webview_final_input_is_recorded_for_sogou_even_when_ax_focus_is_unavailable():
    api = _api_for("sogou_ime")

    result = api.record_webview_ime_text("输入法最终上屏")

    assert result == {"ok": True, "source": "sogou_ime", "char_count": 7}
    event = api._engine.events[0]
    assert event.char == "输入法最终上屏"
    assert event.is_ime_composition is True
    assert event.is_final_ime_result is True


def test_webview_text_is_not_recorded_for_an_unmonitored_input_source():
    api = _api_for("")

    assert api.record_webview_ime_text("不应记录") == {
        "ok": False,
        "ignored": "unmonitored_input_source",
    }
    assert api._engine.events == []
