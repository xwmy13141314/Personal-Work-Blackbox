"""洞察速记测试（v5.4）：收件箱落盘 + 速记标签 CRUD + API 桥接

覆盖合并进来的本地 v4.5「洞察速记」能力，落在 v5.3 的 notes 速记体系之上：
1. insight_capture：收件箱 Markdown 落盘 / 标签归一化 / 目录状态探测 / 优雅降级
2. database：notes 标签写入、标签精确筛选、标签云统计、速记统计
3. web_api：速记双写（入库 + 落盘）、收件箱配置保存与热生效
"""

import sqlite3
from datetime import date, timedelta

import pytest

from src.storage.database import Database
from src.storage.insight_capture import (
    count_inbox_files,
    inbox_status,
    normalize_tags,
    save_to_inbox,
    split_tags,
)


# ==================== Fixtures ====================

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_insight.db"
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "00_收件箱"
    d.mkdir()
    return d


# ==================== 收件箱落盘 ====================

class TestSaveToInbox:

    def test_writes_markdown_with_frontmatter(self, inbox):
        path = save_to_inbox("竞品定价普遍上浮，三防市场接受度在提高",
                             "竞品,定价", "2026-09-20T18:30:00", inbox)
        assert path != ""
        text = open(path, encoding="utf-8").read()
        assert "type: 洞察" in text
        assert "created: 2026-09-20T18:30:00" in text
        assert "tags: [竞品, 定价]" in text
        assert "# 2026-09-20 18:30 洞察" in text
        assert "竞品定价普遍上浮" in text

    def test_filename_collision_suffix(self, inbox):
        """同一分钟两条 → 第二条自动加序号，互不覆盖"""
        p1 = save_to_inbox("第一条", "", "2026-09-20T18:30:00", inbox)
        p2 = save_to_inbox("第二条", "", "2026-09-20T18:30:00", inbox)
        assert p1 != p2
        assert "第一条" in open(p1, encoding="utf-8").read()
        assert "第二条" in open(p2, encoding="utf-8").read()

    def test_creates_missing_directory(self, tmp_path):
        """收件箱目录不存在时自动创建"""
        target = tmp_path / "nested" / "00_收件箱"
        path = save_to_inbox("内容", "", "2026-09-20T18:30:00", target)
        assert path != "" and target.is_dir()

    def test_invalid_timestamp_falls_back(self, inbox):
        """非法时间戳回退当前时间，不抛异常"""
        path = save_to_inbox("内容", "", "not-a-time", inbox)
        assert path != ""

    def test_unwritable_dir_returns_empty(self, tmp_path):
        """目录不可写（路径被同名文件占用）→ 返回空串（不阻断速记入库）"""
        blocker = tmp_path / "file.md"
        blocker.write_text("占位文件", encoding="utf-8")
        path = save_to_inbox("内容", "", "2026-09-20T18:30:00", blocker / "sub")
        assert path == ""

    def test_empty_inbox_dir_skips(self):
        """收件箱留空 → 不落盘、不报错"""
        assert save_to_inbox("内容", "", "2026-09-20T18:30:00", "") == ""


class TestNormalizeTags:

    def test_none(self):
        assert normalize_tags(None) == ""

    def test_string_with_chinese_comma(self):
        assert normalize_tags("竞品，定价, 复盘") == "竞品,定价,复盘"

    def test_list_input(self):
        assert normalize_tags(["竞品", "定价"]) == "竞品,定价"

    def test_dedup_and_strip(self):
        assert normalize_tags(" 竞品 , 定价 ,竞品,") == "竞品,定价"

    def test_split_tags(self):
        assert split_tags("竞品,定价") == ["竞品", "定价"]
        assert split_tags("") == []


class TestInboxStatus:

    def test_unconfigured(self):
        st = inbox_status("")
        assert st["configured"] is False and st["count"] == 0

    def test_configured_and_counting(self, inbox):
        save_to_inbox("a", "", "2026-09-20T18:30:00", inbox)
        save_to_inbox("b", "", "2026-09-20T18:31:00", inbox)
        st = inbox_status(inbox)
        assert st["configured"] is True
        assert st["exists"] is True and st["writable"] is True
        assert st["count"] == 2
        assert count_inbox_files(inbox) == 2

    def test_missing_directory_not_created_by_status(self, tmp_path):
        """状态探测不应有副作用（不创建目录）"""
        target = tmp_path / "not_there"
        st = inbox_status(target)
        assert st["configured"] is True and st["exists"] is False
        assert not target.exists()


# ==================== 速记（notes）标签与统计 ====================

class TestNoteTagsAndStats:

    def test_insert_note_with_tags(self, db):
        nid = db.insert_note("洞察内容", tags="竞品,定价")
        assert nid > 0
        rows = db.query_notes()
        assert len(rows) == 1
        assert rows[0]["tags"] == "竞品,定价"

    def test_query_by_tag_exact(self, db):
        """标签精确匹配：'竞品' 不误中 '竞品分析'"""
        db.insert_note("a", tags="竞品")
        db.insert_note("b", tags="竞品分析")
        rows = db.query_notes(tag="竞品")
        assert [r["content"] for r in rows] == ["a"]

    def test_update_note_tags(self, db):
        nid = db.insert_note("内容")
        assert db.update_note(nid, {"tags": "复盘"}) is True
        assert db.query_notes()[0]["tags"] == "复盘"

    def test_pinned_first_then_created_desc(self, db):
        a = db.insert_note("先创建")
        b = db.insert_note("后创建")
        # 无置顶时按创建时间倒序
        assert [r["id"] for r in db.query_notes()] == [b, a]
        # 置顶后排最前
        assert db.update_note(a, {"pinned": True}) is True
        assert [r["id"] for r in db.query_notes()] == [a, b]

    def test_list_note_tags_counts(self, db):
        db.insert_note("1", tags="竞品,定价")
        db.insert_note("2", tags="竞品")
        db.insert_note("3", tags="复盘")
        db.insert_note("4", tags="")
        tags = db.list_note_tags()
        assert {t["tag"]: t["count"] for t in tags} == {"竞品": 2, "定价": 1, "复盘": 1}
        # 次数降序：竞品最前
        assert tags[0]["tag"] == "竞品"

    def test_list_note_tags_excludes_deleted(self, db):
        nid = db.insert_note("待删", tags="竞品")
        db.delete_note(nid)
        assert db.list_note_tags() == []

    def test_search_notes_matches_tags(self, db):
        db.insert_note("与关键词无关的内容", tags="供应链")
        assert len(db.search_notes("供应链")) == 1
        assert db.search_notes("查无此词") == []

    def test_get_note_stats(self, db):
        db.insert_note("今天1", tags="竞品")
        db.insert_note("今天2", tags="竞品")
        nid = db.insert_note("待删")
        db.delete_note(nid)
        stats = db.get_note_stats()
        assert stats["total"] == 2
        assert stats["today"] == 2
        assert stats["week"] == 2
        assert stats["pinned"] == 0

    def test_stats_week_window_starts_monday(self, db):
        """本周统计以周一为界：上周日的速记不计入本周"""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        last_sunday = monday - timedelta(days=1)
        db.insert_note("本周一", )  # 今天（必在本周窗口内）
        # 直接构造一条上周日的记录
        with db._cursor() as cur:
            cur.execute(
                "INSERT INTO notes (content, tags, source, source_ref, pinned, created_at, updated_at) "
                "VALUES (?, '', 'manual', '', 0, ?, ?)",
                ("上周日", f"{last_sunday.isoformat()}T09:00:00", f"{last_sunday.isoformat()}T09:00:00"),
            )
        stats = db.get_note_stats()
        assert stats["total"] == 2
        # 上周日不在本周（除非今天就是上周日后一周的首日，此时 monday 与 last_sunday 同周）
        expected_week = 2 if today.weekday() == 6 else 1
        assert stats["week"] == expected_week


# ==================== API 桥接 ====================

class _FakeEngine:
    """add_note 依赖 engine._db + engine._settings"""

    def __init__(self, db, settings):
        self._db = db
        self._settings = settings


@pytest.fixture
def settings(tmp_path):
    from src.config.settings import Settings

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "config.yaml").write_text("", encoding="utf-8")
    return Settings(cfg / "config.yaml")


class TestNoteAPI:

    def test_add_note_without_inbox_db_only(self, db, settings):
        from src.ui.web_api import BlackboxAPI

        api = BlackboxAPI(_FakeEngine(db, settings))
        r = api.add_note("无收件箱时的速记", tags="测试")
        assert r["ok"] is True and r["id"] > 0
        assert r["inbox_path"] == ""
        rows = api.get_notes()
        assert len(rows) == 1 and rows[0]["content"] == "无收件箱时的速记"
        assert rows[0]["tags"] == "测试"

    def test_add_note_with_inbox_dual_write(self, db, settings, inbox):
        from src.ui.web_api import BlackboxAPI

        settings.config["insight"]["inbox_dir"] = str(inbox)
        api = BlackboxAPI(_FakeEngine(db, settings))
        r = api.add_note("双写验证", source="hotkey", tags="竞品, 定价")
        assert r["ok"] is True and r["inbox_path"] != ""
        assert "双写验证" in open(r["inbox_path"], encoding="utf-8").read()
        rows = api.get_notes()
        assert rows[0]["tags"] == "竞品,定价"
        assert rows[0]["source"] == "hotkey"

    def test_add_note_rejects_empty(self, db, settings):
        from src.ui.web_api import BlackboxAPI

        api = BlackboxAPI(_FakeEngine(db, settings))
        assert api.add_note("   ")["ok"] is False

    def test_get_notes_by_tag(self, db, settings):
        from src.ui.web_api import BlackboxAPI

        api = BlackboxAPI(_FakeEngine(db, settings))
        api.add_note("A", tags="竞品")
        api.add_note("B", tags="复盘")
        assert [n["content"] for n in api.get_notes(tag="竞品")] == ["A"]

    def test_stats_tags_and_delete(self, db, settings):
        from src.ui.web_api import BlackboxAPI

        api = BlackboxAPI(_FakeEngine(db, settings))
        api.add_note("速记A", tags="竞品")
        api.add_note("速记B", tags="竞品")
        stats = api.get_note_stats()
        assert stats["ok"] is True and stats["total"] == 2 and stats["today"] == 2
        assert {t["tag"]: t["count"] for t in api.get_note_tags()} == {"竞品": 2}

        nid = api.get_notes()[0]["id"]
        assert api.delete_note(nid)["ok"] is True
        assert api.get_note_stats()["total"] == 1

    def test_update_note_normalizes_tags(self, db, settings):
        from src.ui.web_api import BlackboxAPI

        api = BlackboxAPI(_FakeEngine(db, settings))
        nid = api.add_note("内容")["id"]
        assert api.update_note(nid, {"tags": " 竞品 ， 定价 ,竞品"})["ok"] is True
        assert api.get_notes()[0]["tags"] == "竞品,定价"

    def test_insight_config_save_and_hot_reload(self, db, settings, tmp_path, monkeypatch):
        """保存收件箱路径 → config.yaml 落盘 + 内存热更新（新速记立即落盘）"""
        import src.main
        from src.ui.web_api import BlackboxAPI

        app_root = tmp_path / "app"
        (app_root / "config").mkdir(parents=True)
        (app_root / "config" / "config.yaml").write_text("storage: {}\n", encoding="utf-8")
        monkeypatch.setattr(src.main, "get_app_root", lambda: app_root)

        api = BlackboxAPI(_FakeEngine(db, settings))
        inbox_dir = tmp_path / "每日洞察" / "00_收件箱"
        r = api.save_insight_config(str(inbox_dir))
        assert r["ok"] is True and inbox_dir.is_dir()

        import yaml
        saved = yaml.safe_load((app_root / "config" / "config.yaml").read_text(encoding="utf-8"))
        assert saved["insight"]["inbox_dir"] == str(inbox_dir)

        cap = api.add_note("热更新后应落盘")
        assert cap["ok"] is True and cap["inbox_path"] != ""

        cfg = api.get_insight_config()
        assert cfg["ok"] is True
        assert cfg["inbox_dir"] == str(inbox_dir)
        assert cfg["status"]["exists"] is True
        assert cfg["status"]["count"] == 1

    def test_save_insight_config_can_disable(self, db, settings, tmp_path, monkeypatch):
        """收件箱可清空（回到仅入库）"""
        import src.main
        from src.ui.web_api import BlackboxAPI

        app_root = tmp_path / "app"
        (app_root / "config").mkdir(parents=True)
        (app_root / "config" / "config.yaml").write_text("insight:\n  inbox_dir: x\n", encoding="utf-8")
        monkeypatch.setattr(src.main, "get_app_root", lambda: app_root)

        api = BlackboxAPI(_FakeEngine(db, settings))
        r = api.save_insight_config("")
        assert r["ok"] is True and r["inbox_dir"] == ""
        assert api.add_note("仅入库")["inbox_path"] == ""


# ==================== 旧库升级：insights → notes 自动搬移 ====================

class TestLegacyInsightsMigration:
    """v4.5 并行开发线的 `insights` 表在 v5.4 合并后必须能自动搬到 `notes`，
    否则老用户升级后旧速记在新速记页「消失」。"""

    LEGACY_DDL = (
        "CREATE TABLE IF NOT EXISTS insights ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " content TEXT, tags TEXT, source TEXT,"
        " inbox_path TEXT, created_at TEXT, updated_at TEXT)"
    )

    def _make_legacy_db(self, path, rows):
        con = sqlite3.connect(str(path))
        con.execute(self.LEGACY_DDL)
        for r in rows:
            con.execute(
                "INSERT INTO insights (content, tags, source, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                r,
            )
        con.commit()
        con.close()

    def _open(self, path):
        db = Database(path)
        db.initialize()
        return db

    def test_legacy_rows_migrated(self, tmp_path):
        p = tmp_path / "legacy.db"
        self._make_legacy_db(p, [
            ("旧洞察一", "竞品", "hotkey", "2026-09-20T10:00:00", "2026-09-20T10:00:00"),
            ("旧洞察二", "", "manual", "2026-09-21T11:30:00", "2026-09-21T11:30:00"),
        ])
        db = self._open(p)
        try:
            rows = db.query_notes()
            assert len(rows) == 2
            assert sorted(r["content"] for r in rows) == ["旧洞察一", "旧洞察二"]
            got = {r["content"]: r for r in rows}
            assert got["旧洞察一"]["tags"] == "竞品"
            assert got["旧洞察一"]["source"] == "hotkey"
            assert got["旧洞察一"]["created_at"] == "2026-09-20T10:00:00"
        finally:
            db.close()

    def test_migrated_rows_are_searchable_and_counted(self, tmp_path):
        p = tmp_path / "legacy2.db"
        self._make_legacy_db(p, [
            ("供应链比设计更卡节奏", "复盘,供应链", "manual",
             "2026-09-21T09:00:00", "2026-09-21T09:00:00"),
        ])
        db = self._open(p)
        try:
            assert len(db.search_notes("供应链")) == 1
            assert {t["tag"] for t in db.list_note_tags()} == {"复盘", "供应链"}
            assert db.get_note_stats()["total"] == 1
        finally:
            db.close()

    def test_no_duplicate_when_notes_already_has_data(self, tmp_path):
        """notes 非空则不动（幂等，避免每次启动重复导入）"""
        p = tmp_path / "legacy3.db"
        self._make_legacy_db(p, [
            ("旧洞察", "", "manual", "2026-09-20T10:00:00", "2026-09-20T10:00:00"),
        ])
        db = self._open(p)
        try:
            assert len(db.query_notes()) == 1
        finally:
            db.close()
        # 第二次打开：notes 已有 1 条 → 不重复导入
        db2 = self._open(p)
        try:
            assert len(db2.query_notes()) == 1
        finally:
            db2.close()

    def test_legacy_table_without_tags_column(self, tmp_path):
        """旧表没有 tags 列也不能报错（用空标签兜底）"""
        p = tmp_path / "legacy4.db"
        con = sqlite3.connect(str(p))
        con.execute(
            "CREATE TABLE IF NOT EXISTS insights ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, created_at TEXT)"
        )
        con.execute(
            "INSERT INTO insights (content, created_at) VALUES (?, ?)",
            ("无标签旧洞察", "2026-09-20T10:00:00"),
        )
        con.commit()
        con.close()

        db = self._open(p)
        try:
            rows = db.query_notes()
            assert len(rows) == 1
            assert rows[0]["content"] == "无标签旧洞察"
            assert rows[0]["tags"] == ""
            assert rows[0]["source"] == "manual"
        finally:
            db.close()
