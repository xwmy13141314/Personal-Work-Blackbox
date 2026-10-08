from types import SimpleNamespace

from src.storage.database import Database
from src.storage.models import TodoRecord
from src.ui.web_api import BlackboxAPI


def _draft(title: str, *, is_draft: bool = True) -> TodoRecord:
    return TodoRecord(
        title=title, status="pending", priority="normal", note="", due_date="",
        source_type="daily_report", source_ref="2026-09-09", is_draft=is_draft,
        created_at="2026-09-09T09:00:00", updated_at="2026-09-09T09:00:00", completed_at="",
    )


def _api(db: Database) -> BlackboxAPI:
    api = BlackboxAPI.__new__(BlackboxAPI)
    api._engine = SimpleNamespace(_db=db)
    return api


def test_batch_adopt_and_discard_only_change_drafts(tmp_path):
    db = Database(tmp_path / "todos.db")
    db.initialize()
    try:
        first = db.insert_todo(_draft("采纳的草稿"))
        second = db.insert_todo(_draft("丢弃的草稿"))
        formal = db.insert_todo(_draft("正式待办", is_draft=False))
        api = _api(db)

        assert api.adopt_todos([first, formal]) == {"ok": True, "adopted": 1}
        assert db.query_todo(first).is_draft is False
        assert db.query_todo(formal).is_draft is False

        assert api.discard_todos([second, formal]) == {"ok": True, "discarded": 1}
        assert db.query_todo(second).status == "cancelled"
        assert db.query_todo(formal).status == "pending"
    finally:
        db.close()
