import json
from datetime import datetime
from types import SimpleNamespace

from src.ui.web_api import BlackboxAPI


def _api(tmp_path):
    api = BlackboxAPI.__new__(BlackboxAPI)
    api._engine = SimpleNamespace(_settings=SimpleNamespace(_app_root=str(tmp_path)))
    api._tencent_scheduled_task = None
    api._tencent_next_retry_at = 0.0
    return api


def _schedule(tmp_path):
    path = tmp_path / "config" / "tencent_doc_schedule.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "selected_id": "doc-1",
        "documents": [{"id": "doc-1", "name": "邮箱", "url": "https://docs.qq.com/sheet/demo", "enabled": True}],
    }), encoding="utf-8")
    return path


def test_schedule_catches_up_after_nine_and_marks_success_only_after_task_finishes(tmp_path):
    path = _schedule(tmp_path)
    api = _api(tmp_path)
    calls = []
    api.extract_todos_from_tencent_doc = lambda url: calls.append(url) or {"task_id": "scheduled-1"}
    api.get_task_status = lambda task_id: {"status": "done", "result": {"recognized": 3, "extracted": 1, "skipped_duplicates": 2}, "error": None}

    after_nine = datetime(2026, 9, 14, 10, 30)
    api._tencent_schedule_tick(after_nine)
    running = json.loads(path.read_text(encoding="utf-8"))["documents"][0]
    assert calls == ["https://docs.qq.com/sheet/demo"]
    assert running["last_run_date"] == ""
    assert running["last_run_status"] == "running"

    api._tencent_schedule_tick(after_nine)
    completed = json.loads(path.read_text(encoding="utf-8"))["documents"][0]
    assert completed["last_run_date"] == "2026-09-14"
    assert completed["last_run_status"] == "done"
    assert "新增 1 条" in completed["last_run_message"]


def test_schedule_does_not_run_before_nine(tmp_path):
    _schedule(tmp_path)
    api = _api(tmp_path)
    calls = []
    api.extract_todos_from_tencent_doc = lambda url: calls.append(url) or {"task_id": "scheduled-1"}

    api._tencent_schedule_tick(datetime(2026, 9, 14, 8, 59))
    assert calls == []
