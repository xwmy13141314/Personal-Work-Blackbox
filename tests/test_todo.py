"""待办事项（Todo）单元测试 — 数据库 CRUD + 提取器 JSON 容错解析 + Prompt 构建"""

import json

import pytest

from src.storage.database import Database
from src.storage.models import TodoRecord, TodoAdvice
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


# ==================== 看板：排序与统计（v4.3） ====================

class TestTodoSortOrder:
    """sort_order 字段读写 + 批量排序"""

    def test_insert_assigns_incremental_order(self, db):
        """未指定 sort_order 时自动按 1,2,3... 放末尾"""
        a = db.insert_todo(_make_todo("A"))
        b = db.insert_todo(_make_todo("B"))
        c = db.insert_todo(_make_todo("C"))
        assert db.query_todo(a).sort_order == 1.0
        assert db.query_todo(b).sort_order == 2.0
        assert db.query_todo(c).sort_order == 3.0

    def test_insert_respects_explicit_order(self, db):
        """传入 sort_order>0 时保留指定值"""
        tid = db.insert_todo(_make_todo("X", sort_order=10.5))
        assert db.query_todo(tid).sort_order == 10.5

    def test_query_todos_returns_sort_order(self, db):
        """query_todos 返回的记录带 sort_order"""
        db.insert_todo(_make_todo("A"))
        rows = db.query_todos(include_drafts=True)
        assert len(rows) == 1
        assert rows[0].sort_order == 1.0

    def test_update_sort_order(self, db):
        """update_todo 白名单内可改 sort_order"""
        tid = db.insert_todo(_make_todo("A"))
        assert db.update_todo(tid, {"sort_order": 2.5}) is True
        assert db.query_todo(tid).sort_order == 2.5

    def test_reorder_todos(self, db):
        """reorder_todos 批量改 sort_order 并持久化（中间插值场景）"""
        a = db.insert_todo(_make_todo("A"))  # 1.0
        b = db.insert_todo(_make_todo("B"))  # 2.0
        c = db.insert_todo(_make_todo("C"))  # 3.0
        updated = db.reorder_todos([
            {"id": b, "sort_order": 0.5},  # B 提到最前
            {"id": a, "sort_order": 1.0},
            {"id": c, "sort_order": 3.0},
        ])
        assert updated == 3
        assert db.query_todo(b).sort_order == 0.5
        assert db.query_todo(a).sort_order == 1.0
        assert db.query_todo(c).sort_order == 3.0

    def test_reorder_empty(self, db):
        """空列表返回 0，不报错"""
        assert db.reorder_todos([]) == 0


class TestTodoStats:
    """get_todo_stats 四指标口径（PRD v4.3 §4.7）"""

    def test_stats_full_scenario(self, db):
        """综合场景：today=2026-08-11"""
        today = "2026-08-11"
        db.insert_todo(_make_todo("A", status="pending", due_date=""))        # 无截止 → today_pending
        db.insert_todo(_make_todo("B", status="pending", due_date=today))     # 今天到期 → today_pending
        db.insert_todo(_make_todo("C", status="pending", due_date="2026-08-10"))  # 逾期 → overdue
        db.insert_todo(_make_todo("D", status="in_progress", due_date="2026-08-15"))  # 未来 → today_pending
        db.insert_todo(_make_todo("E", status="done", due_date="2026-08-09"))  # done
        db.insert_todo(_make_todo("F", status="cancelled", due_date="2026-08-01"))  # 取消：含 total，不进分项
        db.insert_todo(_make_todo("G", status="pending", is_draft=True))      # 草稿：全排除

        stats = db.get_todo_stats(today)
        assert stats["total"] == 6          # A-F（G 草稿排除）
        assert stats["today_pending"] == 3  # A B D
        assert stats["overdue"] == 1        # C
        assert stats["done"] == 1           # E

    def test_stats_empty(self, db):
        stats = db.get_todo_stats("2026-08-11")
        assert stats == {"total": 0, "today_pending": 0, "overdue": 0, "done": 0}

    def test_stats_drafts_excluded(self, db):
        """草稿不计入 total"""
        db.insert_todo(_make_todo("草稿1", is_draft=True))
        db.insert_todo(_make_todo("草稿2", is_draft=True))
        stats = db.get_todo_stats("2026-08-11")
        assert stats["total"] == 0

    def test_stats_today_boundary(self, db):
        """due_date == today 算 today_pending（未逾期边界）"""
        today = "2026-08-11"
        db.insert_todo(_make_todo("今天到期", status="pending", due_date=today))
        stats = db.get_todo_stats(today)
        assert stats["today_pending"] == 1
        assert stats["overdue"] == 0

    def test_stats_cancelled_not_in_buckets(self, db):
        """cancelled 不进 today_pending/overdue/done，但含在 total"""
        db.insert_todo(_make_todo("取消", status="cancelled", due_date="2020-01-01"))
        stats = db.get_todo_stats("2026-08-11")
        assert stats["total"] == 1
        assert stats["today_pending"] == 0
        assert stats["overdue"] == 0
        assert stats["done"] == 0


class _FakeEngine:
    """轻量假引擎：BlackboxAPI.update_todo 联动逻辑只依赖 engine._db"""
    def __init__(self, db):
        self._db = db


class TestTodoProgress:
    """progress 字段读写 + 100%↔done 联动（PRD v4.3 §4.5 / §8 决策3）"""

    def test_progress_default_zero(self, db):
        """新建待办默认 progress=0"""
        tid = db.insert_todo(_make_todo("A"))
        assert db.query_todo(tid).progress == 0

    def test_insert_with_progress(self, db):
        """插入时指定 progress 并持久化"""
        tid = db.insert_todo(_make_todo("A", progress=30))
        assert db.query_todo(tid).progress == 30

    def test_update_progress(self, db):
        """update_todo 改 progress（白名单内）"""
        tid = db.insert_todo(_make_todo("A"))
        assert db.update_todo(tid, {"progress": 60}) is True
        assert db.query_todo(tid).progress == 60

    def test_query_todos_returns_progress(self, db):
        db.insert_todo(_make_todo("A", progress=40))
        rows = db.query_todos(include_drafts=True)
        assert rows[0].progress == 40

    # --- 100% ↔ done 联动（web_api 层） ---

    def test_linkage_progress_100_auto_done(self, db):
        """调进度到 100 自动转 done 并记 completed_at"""
        from src.ui.web_api import BlackboxAPI
        api = BlackboxAPI(_FakeEngine(db))
        tid = db.insert_todo(_make_todo("A", status="pending", progress=20))
        r = api.update_todo(tid, {"progress": 100})
        assert r["ok"] is True
        got = db.query_todo(tid)
        assert got.status == "done"
        assert got.progress == 100
        assert got.completed_at != ""

    def test_linkage_progress_below_100_revert_from_done(self, db):
        """已完成任务调进度到 <100 自动回退 in_progress、清 completed_at"""
        from src.ui.web_api import BlackboxAPI
        api = BlackboxAPI(_FakeEngine(db))
        tid = db.insert_todo(_make_todo("A", status="done", progress=100,
                                        completed_at="2026-08-11T10:00:00"))
        r = api.update_todo(tid, {"progress": 50})
        assert r["ok"] is True
        got = db.query_todo(tid)
        assert got.status == "in_progress"
        assert got.progress == 50
        assert got.completed_at == ""

    def test_linkage_progress_clamped(self, db):
        """progress 越界被夹到 [0,100]，且夹到 100 仍联动 done、夹到 0 触发回退"""
        from src.ui.web_api import BlackboxAPI
        api = BlackboxAPI(_FakeEngine(db))
        tid = db.insert_todo(_make_todo("A", status="pending"))
        api.update_todo(tid, {"progress": 200})  # → 100
        got = db.query_todo(tid)
        assert got.progress == 100
        assert got.status == "done"
        api.update_todo(tid, {"progress": -10})  # → 0，且原 done → 回退
        got = db.query_todo(tid)
        assert got.progress == 0
        assert got.status == "in_progress"

    def test_linkage_status_change_keeps_progress(self, db):
        """纯改 status（拖拽，不传 progress）不动 progress"""
        from src.ui.web_api import BlackboxAPI
        api = BlackboxAPI(_FakeEngine(db))
        tid = db.insert_todo(_make_todo("A", status="pending", progress=40))
        api.update_todo(tid, {"status": "done"})
        got = db.query_todo(tid)
        assert got.status == "done"
        assert got.progress == 40  # 未传 progress，保持原值


class TestTodoMigrate:
    """旧库 schema 迁移（sort_order 回填）"""

    def test_migrate_backfills_sort_order(self, tmp_path):
        """旧库（无 sort_order 列）迁移后按 id 升序回填 1..N"""
        import sqlite3
        db_path = tmp_path / "old.db"
        # 模拟旧库：手动建无 sort_order 的 todos 表并插入数据
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, status TEXT,
                priority TEXT, note TEXT, due_date TEXT, source_type TEXT,
                source_ref TEXT, is_draft INTEGER, created_at TEXT, updated_at TEXT,
                completed_at TEXT
            );
            INSERT INTO todos (title, status, priority, note, due_date, source_type,
                source_ref, is_draft, created_at, updated_at, completed_at)
            VALUES ('A','pending','normal','','','manual','',0,'t','t',''),
                   ('B','pending','normal','','','manual','',0,'t','t','');
        """)
        conn.commit()
        conn.close()
        # 用 Database 打开 → 触发 _migrate_schema 加列 + 回填
        db = Database(db_path)
        db.initialize()
        by_id = sorted(db.query_todos(include_drafts=True), key=lambda t: t.id)
        assert [t.sort_order for t in by_id] == [1.0, 2.0]
        # 迁移同步补 progress 列（默认 0）
        assert all(t.progress == 0 for t in by_id)
        db.close()


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


# ==================== 推进建议 JSON 容错解析（P2 §4.6） ====================

class TestParseAdvicesJson:
    """TodoExtractor.parse_advices_json 容错 + 校验"""
    IDS = {1, 2}

    def test_plain_array(self):
        c = '[{"todo_id":1,"type":"start","reason":"开工"}]'
        r = TodoExtractor.parse_advices_json(c, self.IDS)
        assert len(r) == 1
        assert r[0]["todo_id"] == 1 and r[0]["type"] == "start"

    def test_code_fence_and_extra_text(self):
        """fence 包裹 + 前后多余文字"""
        c = '建议：\n```json\n[{"todo_id":1,"type":"progress","reason":"推进","suggested_progress":60}]\n```\n以上'
        r = TodoExtractor.parse_advices_json(c, self.IDS)
        assert len(r) == 1 and r[0]["suggested_progress"] == 60

    def test_fabricated_todo_id_filtered(self):
        """valid_ids 之外的 todo_id（LLM 编造）被丢弃"""
        c = '[{"todo_id":999,"type":"start","reason":"x"}]'
        assert TodoExtractor.parse_advices_json(c, self.IDS) == []

    def test_invalid_type_dropped(self):
        c = '[{"todo_id":1,"type":"unknown","reason":"x"}]'
        assert TodoExtractor.parse_advices_json(c, self.IDS) == []

    def test_missing_reason_dropped(self):
        c = '[{"todo_id":1,"type":"start"}]'
        assert TodoExtractor.parse_advices_json(c, self.IDS) == []

    def test_progress_requires_valid_suggested_progress(self):
        """progress 类型缺/非数 suggested_progress 丢弃"""
        assert TodoExtractor.parse_advices_json(
            '[{"todo_id":1,"type":"progress","reason":"r"}]', self.IDS) == []
        assert TodoExtractor.parse_advices_json(
            '[{"todo_id":1,"type":"progress","reason":"r","suggested_progress":"abc"}]', self.IDS) == []

    def test_progress_clamped(self):
        c = '[{"todo_id":1,"type":"progress","reason":"r","suggested_progress":150}]'
        r = TodoExtractor.parse_advices_json(c, self.IDS)
        assert r[0]["suggested_progress"] == 100

    def test_non_dict_and_bad_id_skipped(self):
        c = '["str", {"todo_id":"x","type":"start","reason":"r"}, {"todo_id":2,"type":"stall","reason":"卡住"}]'
        r = TodoExtractor.parse_advices_json(c, self.IDS)
        assert len(r) == 1 and r[0]["todo_id"] == 2

    def test_empty_and_invalid_returns_empty(self):
        assert TodoExtractor.parse_advices_json("", self.IDS) == []
        assert TodoExtractor.parse_advices_json("   ", self.IDS) == []
        assert TodoExtractor.parse_advices_json("{}", self.IDS) == []
        assert TodoExtractor.parse_advices_json("[broken", self.IDS) == []

    def test_no_valid_ids_filter(self):
        """valid_ids=None 时不过滤 todo_id"""
        r = TodoExtractor.parse_advices_json('[{"todo_id":999,"type":"start","reason":"x"}]', None)
        assert len(r) == 1

    def test_max_advices_cap(self):
        """超过 _MAX_ADVICES(30) 截断"""
        items = ",".join('{"todo_id":1,"type":"start","reason":"r"}' for _ in range(33))
        r = TodoExtractor.parse_advices_json(f"[{items}]", self.IDS)
        assert len(r) == 30


# ==================== 推进建议 CRUD + 去重 + 联表（P2 §4.6） ====================

def _make_advice(todo_id=1, **kwargs):
    """构造一条推进建议，默认 start 类型 pending"""
    defaults = dict(
        todo_id=todo_id, suggestion_type="start", reason="今日有相关活动",
        suggested_status="in_progress", suggested_progress=None,
        status="pending", source_date="2026-08-11",
        created_at="2026-08-11T18:00:00", updated_at="2026-08-11T18:00:00",
    )
    defaults.update(kwargs)
    return TodoAdvice(**defaults)


class TestTodoAdvicesCRUD:
    """todo_advices 表 CRUD + 去重 + 联表查询"""

    def test_insert_and_query(self, db):
        t = db.insert_todo(_make_todo("A"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t, reason="r1"))
        assert aid > 0
        rows = db.query_todo_advices(status="pending")
        assert len(rows) == 1
        assert rows[0]["todo_id"] == t
        assert rows[0]["todo_title"] == "A"
        assert rows[0]["suggestion_type"] == "start"
        assert rows[0]["reason"] == "r1"

    def test_dedup_same_todo_pending(self, db):
        """同 todo_id 已有 pending → 第二次 insert 返回 0（去重）"""
        t = db.insert_todo(_make_todo("A"))
        assert db.insert_todo_advice(_make_advice(todo_id=t)) > 0
        assert db.insert_todo_advice(_make_advice(todo_id=t)) == 0
        assert len(db.query_todo_advices()) == 1

    def test_dedup_released_after_applied(self, db):
        """apply 后该 todo 可再生成新 pending 建议"""
        t = db.insert_todo(_make_todo("A"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t))
        assert db.update_advice_status(aid, "applied") is True
        assert db.insert_todo_advice(_make_advice(todo_id=t)) > 0

    def test_query_left_join_deleted_todo(self, db):
        """关联 todo 已删除 → 标题回退（待办已删除）"""
        t = db.insert_todo(_make_todo("A"))
        db.insert_todo_advice(_make_advice(todo_id=t))
        db.delete_todo(t)
        rows = db.query_todo_advices()
        assert rows[0]["todo_title"] == "（待办已删除）"

    def test_query_advice_single(self, db):
        t = db.insert_todo(_make_todo("A"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t))
        got = db.query_advice(aid)
        assert got is not None and got["todo_id"] == t
        assert got["suggestion_type"] == "start"
        assert db.query_advice(99999) is None

    def test_update_status_dismissed(self, db):
        t = db.insert_todo(_make_todo("A"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t))
        assert db.update_advice_status(aid, "dismissed") is True
        assert db.query_advice(aid)["status"] == "dismissed"

    def test_query_filters_by_status(self, db):
        """query_todo_advices(status=) 只返回对应状态"""
        t = db.insert_todo(_make_todo("A"))
        a1 = db.insert_todo_advice(_make_advice(todo_id=t, reason="p1"))
        db.update_advice_status(a1, "applied")
        db.insert_todo_advice(_make_advice(todo_id=t, reason="p2"))  # a1 已 applied，去重放行
        pending = db.query_todo_advices(status="pending")
        applied = db.query_todo_advices(status="applied")
        assert len(pending) == 1 and pending[0]["reason"] == "p2"
        assert len(applied) == 1 and applied[0]["reason"] == "p1"


# ==================== 推进建议采纳联动（P2 §4.6） ====================

class TestApplyTodoAdvice:
    """web_api.apply_todo_advice / dismiss_todo_advice 采纳与忽略"""

    def test_apply_start_sets_in_progress(self, db):
        from src.ui.web_api import BlackboxAPI
        t = db.insert_todo(_make_todo("任务", status="pending"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t, suggestion_type="start",
                                                  suggested_status="in_progress"))
        api = BlackboxAPI(_FakeEngine(db))
        r = api.apply_todo_advice(aid)
        assert r["ok"] is True and r["applied_type"] == "start"
        assert db.query_todo(t).status == "in_progress"
        assert db.query_advice(aid)["status"] == "applied"

    def test_apply_progress_triggers_linkage(self, db):
        """progress 类型采纳 → 推进度到 100 联动 done"""
        from src.ui.web_api import BlackboxAPI
        t = db.insert_todo(_make_todo("任务", status="in_progress", progress=20))
        aid = db.insert_todo_advice(_make_advice(todo_id=t, suggestion_type="progress",
                                                  suggested_progress=100, suggested_status=""))
        api = BlackboxAPI(_FakeEngine(db))
        r = api.apply_todo_advice(aid)
        assert r["ok"] is True
        got = db.query_todo(t)
        assert got.progress == 100 and got.status == "done"

    def test_apply_stall_keeps_todo(self, db):
        """stall 类型采纳不动待办，只标 applied"""
        from src.ui.web_api import BlackboxAPI
        t = db.insert_todo(_make_todo("任务", status="pending", progress=10))
        aid = db.insert_todo_advice(_make_advice(todo_id=t, suggestion_type="stall", suggested_status=""))
        api = BlackboxAPI(_FakeEngine(db))
        r = api.apply_todo_advice(aid)
        assert r["ok"] is True and r["applied_type"] == "stall"
        got = db.query_todo(t)
        assert got.status == "pending" and got.progress == 10
        assert db.query_advice(aid)["status"] == "applied"

    def test_apply_invalid_id(self, db):
        from src.ui.web_api import BlackboxAPI
        api = BlackboxAPI(_FakeEngine(db))
        r = api.apply_todo_advice(99999)
        assert r["ok"] is False

    def test_apply_already_processed(self, db):
        """已 applied 的建议再次采纳失败"""
        from src.ui.web_api import BlackboxAPI
        t = db.insert_todo(_make_todo("任务"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t))
        api = BlackboxAPI(_FakeEngine(db))
        assert api.apply_todo_advice(aid)["ok"] is True
        assert api.apply_todo_advice(aid)["ok"] is False

    def test_dismiss(self, db):
        from src.ui.web_api import BlackboxAPI
        t = db.insert_todo(_make_todo("任务"))
        aid = db.insert_todo_advice(_make_advice(todo_id=t, suggestion_type="stall", suggested_status=""))
        api = BlackboxAPI(_FakeEngine(db))
        r = api.dismiss_todo_advice(aid)
        assert r["ok"] is True
        assert db.query_advice(aid)["status"] == "dismissed"
        # 待办不受影响
        assert db.query_todo(t).status == "pending"


# ==================== 待办提醒去重（P3 §4.9） ====================

class TestTodoNotify:
    """todo_notify_log 去重：每任务每日每类最多通知一次"""

    def test_record_first_time_true(self, db):
        t = db.insert_todo(_make_todo("A", due_date="2026-08-01"))
        assert db.record_todo_notify(t, "2026-08-11", "overdue") is True

    def test_same_day_same_type_dedup(self, db):
        """同 todo + 同日 + 同类第二次返回 False（去重）"""
        t = db.insert_todo(_make_todo("A", due_date="2026-08-01"))
        assert db.record_todo_notify(t, "2026-08-11", "overdue") is True
        assert db.record_todo_notify(t, "2026-08-11", "overdue") is False

    def test_different_type_same_day_allowed(self, db):
        """同 todo + 同日 + 不同类型各自独立（overdue / upcoming 不互斥）"""
        t = db.insert_todo(_make_todo("A"))
        assert db.record_todo_notify(t, "2026-08-11", "overdue") is True
        assert db.record_todo_notify(t, "2026-08-11", "upcoming") is True

    def test_different_day_resets(self, db):
        """跨天重新允许通知"""
        t = db.insert_todo(_make_todo("A"))
        assert db.record_todo_notify(t, "2026-08-11", "overdue") is True
        assert db.record_todo_notify(t, "2026-08-12", "overdue") is True


class TestTodoJsonBackup:
    """P4 §4.10 待办 JSON 全量备份 / 导入恢复"""

    def test_export_json_full_fields(self, db, tmp_path):
        """导出 JSON 含全字段（status/priority/progress/due_date 等原始值不翻译）"""
        from src.storage.data_exporter import DataExporter

        db.insert_todo(_make_todo("任务A", status="in_progress", priority="high", progress=40, due_date="2026-08-15"))
        db.insert_todo(_make_todo("任务B", is_draft=True))
        out = tmp_path / "backup.json"
        DataExporter(db).export_todos_json(db.query_todos(include_drafts=True), output_path=out)

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["todo_count"] == 2
        a = next(t for t in data["todos"] if t["title"] == "任务A")
        assert a["status"] == "in_progress"
        assert a["priority"] == "high"
        assert a["progress"] == 40
        assert a["due_date"] == "2026-08-15"
        assert a["is_draft"] is False

    def test_import_append_to_empty(self, db, tmp_path):
        """导入到空库：全部新增，字段无损保留"""
        from src.storage.data_exporter import DataExporter

        db.insert_todo(_make_todo("任务A", status="done", priority="urgent", progress=100))
        db.insert_todo(_make_todo("任务B"))
        out = tmp_path / "backup.json"
        DataExporter(db).export_todos_json(db.query_todos(include_drafts=True), output_path=out)

        new_db = Database(tmp_path / "new.db")
        new_db.initialize()
        try:
            r = DataExporter(new_db).import_todos_json(out, mode="append")
            assert r["ok"]
            assert r["imported"] == 2 and r["skipped"] == 0
            todos = {t.title: t for t in new_db.query_todos(include_drafts=True)}
            assert todos["任务A"].status == "done"
            assert todos["任务A"].priority == "urgent"
            assert todos["任务A"].progress == 100
        finally:
            new_db.close()

    def test_import_append_dedup(self, db, tmp_path):
        """append 模式：同标题跳过，不重复插入"""
        from src.storage.data_exporter import DataExporter

        db.insert_todo(_make_todo("已存在任务"))
        out = tmp_path / "backup.json"
        DataExporter(db).export_todos_json(db.query_todos(include_drafts=True), output_path=out)

        r = DataExporter(db).import_todos_json(out, mode="append")
        assert r["ok"]
        assert r["skipped"] == 1 and r["imported"] == 0
        assert len(db.query_todos(include_drafts=True)) == 1

    def test_import_merge_updates(self, db, tmp_path):
        """merge 模式：同标题更新内容字段（status/priority/progress）"""
        from src.storage.data_exporter import DataExporter

        db.insert_todo(_make_todo("任务A", status="pending", priority="normal", progress=0))
        payload = {"version": 1, "todos": [
            {"title": "任务A", "status": "done", "priority": "urgent", "progress": 100,
             "note": "", "due_date": "", "source_type": "manual", "source_ref": "",
             "is_draft": False, "created_at": "2026-08-11T10:00:00", "updated_at": "",
             "completed_at": "2026-08-11T12:00:00"}
        ]}
        p = tmp_path / "merge.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        r = DataExporter(db).import_todos_json(p, mode="merge")
        assert r["ok"] and r["updated"] == 1
        t = next(t for t in db.query_todos(include_drafts=True) if t.title == "任务A")
        assert t.status == "done"
        assert t.priority == "urgent"
        assert t.progress == 100

    def test_import_accepts_dict(self, db):
        """import 接受已解析的 dict（不必是文件路径）"""
        from src.storage.data_exporter import DataExporter

        payload = {"version": 1, "todos": [{"title": "直接传入", "status": "pending"}]}
        r = DataExporter(db).import_todos_json(payload)
        assert r["imported"] == 1
        assert any(t.title == "直接传入" for t in db.query_todos())

    def test_import_invalid_format(self, db):
        """非法 JSON 结构（无 todos 数组）返回 ok=False"""
        from src.storage.data_exporter import DataExporter

        r = DataExporter(db).import_todos_json({"not_todos": 1})
        assert r["ok"] is False
        assert "todos" in r["error"]

    def test_import_empty_title_skipped(self, db):
        """空标题条目记入 errors，不插入"""
        from src.storage.data_exporter import DataExporter

        payload = {"todos": [{"title": "   ", "status": "pending"}, {"title": "有效", "status": "pending"}]}
        r = DataExporter(db).import_todos_json(payload)
        assert r["imported"] == 1
        assert len(r["errors"]) == 1
