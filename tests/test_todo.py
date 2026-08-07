"""待办事项（Todo）单元测试 — 数据库 CRUD + 提取器 JSON 容错解析 + Prompt 构建"""

import pytest

from src.storage.database import Database
from src.storage.models import TodoRecord
from src.ai.todo_extractor import TodoExtractor
from src.ai.prompt_engine import PromptEngine


# ==================== Fixtures ====================

@pytest.fixture
def db(tmp_path):
    """创建临时数据库（含 todos 表）"""
    db_path = tmp_path / "test_todo.db"
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


def _make_todo(title="回复客户邮件", **kwargs):
    """构造一条待办，默认正式（非草稿）"""
    defaults = dict(
        title=title, status="pending", priority="normal",
        note="", due_date="", source_type="manual", source_ref="",
        is_draft=False, created_at="2026-08-07T09:00:00",
        updated_at="2026-08-07T09:00:00", completed_at="",
    )
    defaults.update(kwargs)
    return TodoRecord(**defaults)


# ==================== Database CRUD ====================

class TestTodoCRUD:
    """待办数据库 CRUD 测试"""

    def test_insert_and_query(self, db):
        """插入后应能按主键查回"""
        tid = db.insert_todo(_make_todo("完成季度报告", priority="high"))
        assert tid > 0
        got = db.query_todo(tid)
        assert got is not None
        assert got.title == "完成季度报告"
        assert got.priority == "high"
        assert got.status == "pending"
        assert got.is_draft is False

    def test_insert_draft_default(self, db):
        """TodoRecord 默认 is_draft=True（AI 提取场景）"""
        rec = TodoRecord(title="草稿待办", created_at="2026-08-07T09:00:00",
                         updated_at="2026-08-07T09:00:00")
        assert rec.is_draft is True
        tid = db.insert_todo(rec)
        assert db.query_todo(tid).is_draft is True

    def test_query_todo_not_found(self, db):
        """查询不存在的 ID 返回 None"""
        assert db.query_todo(99999) is None

    def test_query_todos_filter_by_status(self, db):
        """按状态过滤"""
        db.insert_todo(_make_todo("任务1", status="pending"))
        db.insert_todo(_make_todo("任务2", status="done"))
        db.insert_todo(_make_todo("任务3", status="pending"))

        assert len(db.query_todos(status="pending", include_drafts=True)) == 2
        assert len(db.query_todos(status="done", include_drafts=True)) == 1

    def test_query_todos_exclude_drafts(self, db):
        """include_drafts=False 时排除草稿"""
        db.insert_todo(_make_todo("正式", is_draft=False))
        db.insert_todo(_make_todo("草稿", is_draft=True))

        assert len(db.query_todos(include_drafts=True)) == 2
        non_draft = db.query_todos(include_drafts=False)
        assert len(non_draft) == 1
        assert non_draft[0].title == "正式"

    def test_query_todos_filter_by_source_ref(self, db):
        """按来源标识过滤"""
        db.insert_todo(_make_todo("日报待办", source_ref="2026-08-06"))
        db.insert_todo(_make_todo("另一天", source_ref="2026-08-07"))

        rows = db.query_todos(source_ref="2026-08-06", include_drafts=True)
        assert len(rows) == 1
        assert rows[0].source_ref == "2026-08-06"

    def test_update_todo_fields(self, db):
        """更新标题与优先级"""
        tid = db.insert_todo(_make_todo("旧标题", priority="normal"))
        assert db.update_todo(tid, {"title": "新标题", "priority": "urgent"}) is True
        got = db.query_todo(tid)
        assert got.title == "新标题"
        assert got.priority == "urgent"

    def test_update_todo_is_draft_bool_to_int(self, db):
        """update_todo 把 is_draft 布尔值正确存为 0/1"""
        tid = db.insert_todo(_make_todo("草稿", is_draft=True))
        assert db.update_todo(tid, {"is_draft": False}) is True
        assert db.query_todo(tid).is_draft is False

    def test_update_todo_rejects_unknown_field(self, db):
        """白名单外字段（如 id）应被忽略，不报错"""
        tid = db.insert_todo(_make_todo("待办"))
        ok = db.update_todo(tid, {"id": 999, "title": "改了"})
        assert ok is True
        got = db.query_todo(tid)
        assert got.id == tid  # id 未被篡改
        assert got.title == "改了"

    def test_update_todo_unknown_id(self, db):
        """更新不存在的 ID 返回 False"""
        assert db.update_todo(99999, {"title": "x"}) is False

    def test_delete_todo(self, db):
        """删除后查不到，二次删返回 False"""
        tid = db.insert_todo(_make_todo("待删"))
        assert db.delete_todo(tid) is True
        assert db.query_todo(tid) is None
        assert db.delete_todo(tid) is False


# ==================== JSON 容错解析 ====================

class TestParseTodosJson:
    """TodoExtractor.parse_todos_json 容错测试"""

    def test_plain_json_array(self):
        todos = TodoExtractor.parse_todos_json('[{"title": "任务A", "priority": "high"}]')
        assert len(todos) == 1
        assert todos[0]["title"] == "任务A"
        assert todos[0]["priority"] == "high"

    def test_json_code_fence(self):
        """被 ```json ... ``` 包裹"""
        content = '```json\n[{"title": "任务", "due_date": "2026-08-10"}]\n```'
        todos = TodoExtractor.parse_todos_json(content)
        assert len(todos) == 1
        assert todos[0]["due_date"] == "2026-08-10"

    def test_extra_text_around_array(self):
        """数组前后有多余文字"""
        content = '好的，以下是提取的待办：\n[{"title": "任务"}]\n以上。'
        todos = TodoExtractor.parse_todos_json(content)
        assert len(todos) == 1
        assert todos[0]["title"] == "任务"

    def test_brackets_inside_strings(self):
        """字符串内的方括号不应破坏平衡匹配"""
        content = '[{"title": "处理 [紧急] 标记", "note": "见附录[1]"}]'
        todos = TodoExtractor.parse_todos_json(content)
        assert len(todos) == 1
        assert todos[0]["title"] == "处理 [紧急] 标记"

    def test_empty_array(self):
        assert TodoExtractor.parse_todos_json("[]") == []

    def test_empty_or_whitespace(self):
        assert TodoExtractor.parse_todos_json("") == []
        assert TodoExtractor.parse_todos_json("   ") == []

    def test_invalid_json_returns_empty(self):
        """非法 JSON 返回空，不抛异常"""
        assert TodoExtractor.parse_todos_json("[{title: 缺引号}]") == []

    def test_no_array_returns_empty(self):
        """没有数组结构返回空"""
        assert TodoExtractor.parse_todos_json('{"title": "不是数组"}') == []

    def test_priority_normalized(self):
        """非法 priority 归一化为 normal；合法大写值转小写"""
        content = '[{"title": "a", "priority": "超高"}, {"title": "b", "priority": "HIGH"}]'
        todos = TodoExtractor.parse_todos_json(content)
        assert todos[0]["priority"] == "normal"
        assert todos[1]["priority"] == "high"

    def test_invalid_due_date_dropped(self):
        """不符合 YYYY-MM-DD 的 due_date 置空"""
        todos = TodoExtractor.parse_todos_json('[{"title": "a", "due_date": "8月10日"}]')
        assert todos[0]["due_date"] == ""

    def test_valid_due_date_kept(self):
        todos = TodoExtractor.parse_todos_json('[{"title": "a", "due_date": "2026-08-10"}]')
        assert todos[0]["due_date"] == "2026-08-10"

    def test_skip_item_without_title(self):
        """缺 title 的条目被跳过"""
        todos = TodoExtractor.parse_todos_json('[{"priority": "high"}, {"title": "有效"}]')
        assert len(todos) == 1
        assert todos[0]["title"] == "有效"

    def test_non_dict_item_skipped(self):
        """非对象元素被跳过"""
        todos = TodoExtractor.parse_todos_json('["字符串", {"title": "有效"}, 123]')
        assert len(todos) == 1


# ==================== Prompt 构建 ====================

class TestTodoPrompt:
    """待办提取 Prompt 构建测试"""

    def test_build_prompt_structure(self):
        engine = PromptEngine()
        messages = engine.build_todo_extract_prompt("## 今日概览\n完成了X")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "完成了X" in messages[1]["content"]

    def test_build_prompt_empty_report(self):
        engine = PromptEngine()
        messages = engine.build_todo_extract_prompt("")
        assert len(messages) == 2
        assert "（空报告）" in messages[1]["content"]
