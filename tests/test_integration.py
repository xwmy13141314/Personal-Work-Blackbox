"""核心引擎集成测试（冒烟测试）

验证采集层 → 处理管道 → 存储层的端到端数据流转，
以及 BlackboxEngine 的初始化、会话管理、隐私过滤等核心流程。
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.storage.database import Database, HAS_SQLCIPHER
from src.storage.models import SessionRecord, TextSegmentRecord
from src.processor.input_buffer import InputBuffer
from src.processor.privacy_filter import PrivacyFilter
from src.processor.session_manager import SessionManager, Session
from src.collector.keyboard_hook import KeyEvent, KeyEventType
from pynput import keyboard


# ==================== Fixtures ====================

@pytest.fixture
def temp_config(tmp_path):
    """创建临时配置目录"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return tmp_path


@pytest.fixture
def db(tmp_path):
    """临时数据库"""
    db_path = tmp_path / "test_integration.db"
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def privacy_filter():
    """隐私过滤器"""
    return PrivacyFilter({
        "enabled": True,
        "custom_patterns": [],
        "number_min_digits": 8,
    })


@pytest.fixture
def captured_segments():
    """捕获的文本片段列表"""
    return []


@pytest.fixture
def input_buffer(captured_segments):
    """输入缓冲区，提交时将片段存入 captured_segments"""
    return InputBuffer(
        on_commit=lambda text: captured_segments.append((text, "keyboard")),
        max_length=5000,
        timeout=30,
    )


@pytest.fixture
def session_manager(db):
    """会话管理器，会话结束时将数据写入数据库"""
    def on_session_end(session: Session):
        record = SessionRecord(
            start_time=session.start_time.isoformat(),
            end_time=session.end_time.isoformat() if session.end_time else None,
            process_name=session.process_name,
            window_title=session.window_title,
            idle_seconds=session.idle_seconds,
            active_seconds=session.active_seconds,
            is_filtered=session.is_filtered,
        )
        segments = [
            TextSegmentRecord(
                session_id=0,
                timestamp=seg["timestamp"],
                raw_text=seg["text"],
                source=seg.get("source", "keyboard"),
                is_filtered=seg.get("is_filtered", False),
                char_count=len(seg["text"]),
            )
            for seg in session.text_segments
        ]
        db.insert_session_with_segments(record, segments)

    return SessionManager(on_session_end=on_session_end)


# ==================== 测试：引擎初始化 ====================

class TestEngineInitialization:
    """BlackboxEngine 初始化冒烟测试"""

    def test_engine_init_with_temp_config(self, temp_config, monkeypatch):
        """测试引擎可以在临时配置下初始化"""
        # 创建临时配置文件
        config_file = temp_config / "config" / "config.yaml"
        db_path = (temp_config / "data" / "test.db").as_posix()
        logs_path = (temp_config / "data" / "logs").as_posix()
        config_file.write_text(
            "collection:\n"
            "  keyboard_enabled: true\n"
            "  clipboard_enabled: true\n"
            "  window_tracking_enabled: true\n"
            "  idle_threshold: 300\n"
            "  session_timeout: 1800\n"
            "storage:\n"
            f'  db_path: "{db_path}"\n'
            f'  markdown_export_dir: "{logs_path}"\n'
            "  retention_days: 90\n"
            "  auto_archive: true\n"
            "  encryption_enabled: false\n"
            "privacy:\n"
            "  enabled: true\n"
            "  custom_patterns: []\n"
            "  number_min_digits: 8\n"
            "performance:\n"
            "  journal_mode: WAL\n"
            "  input_buffer_max_length: 5000\n"
            "  input_buffer_timeout: 30\n"
            "ai:\n"
            "  provider: none\n"
            "  model: test\n"
            "  base_url: http://localhost\n"
            "  api_key: \"\"\n"
            "  timeout: 30\n"
            "  max_retries: 1\n",
            encoding="utf-8",
        )

        # 切换工作目录
        monkeypatch.chdir(temp_config)

        from src.config.settings import Settings
        # 重置单例
        Settings._instance = None
        Settings._config_path = None

        from src.main import BlackboxEngine
        # Mock AI 层以避免后台线程访问已关闭的数据库
        with patch.object(BlackboxEngine, '_init_ai_layer', lambda self: None):
            engine = BlackboxEngine(config_path=config_file)

        assert engine is not None
        assert engine._db is not None
        assert engine._db.is_connected
        assert engine._session_manager is not None
        assert engine._input_buffer is not None
        assert engine._privacy_filter is not None

        # 清理：先停止引擎（含后台线程），再关闭数据库
        engine.stop()
        engine._db.close()
        Settings._instance = None
        Settings._config_path = None

    def test_engine_init_creates_tables(self, temp_config, monkeypatch):
        """测试引擎初始化后数据库表已创建"""
        config_file = temp_config / "config" / "config.yaml"
        db_path = temp_config / "data" / "test.db"
        db_path_str = db_path.as_posix()
        logs_path = (temp_config / "data" / "logs").as_posix()
        config_file.write_text(
            "collection:\n"
            "  keyboard_enabled: true\n"
            "  clipboard_enabled: true\n"
            "  window_tracking_enabled: true\n"
            "  idle_threshold: 300\n"
            "  session_timeout: 1800\n"
            "storage:\n"
            f'  db_path: "{db_path_str}"\n'
            f'  markdown_export_dir: "{logs_path}"\n'
            "  retention_days: 90\n"
            "  auto_archive: true\n"
            "  encryption_enabled: false\n"
            "privacy:\n"
            "  enabled: true\n"
            "  custom_patterns: []\n"
            "  number_min_digits: 8\n"
            "performance:\n"
            "  journal_mode: WAL\n"
            "  input_buffer_max_length: 5000\n"
            "  input_buffer_timeout: 30\n"
            "ai:\n"
            "  provider: none\n"
            "  model: test\n"
            "  base_url: http://localhost\n"
            "  api_key: \"\"\n"
            "  timeout: 30\n"
            "  max_retries: 1\n",
            encoding="utf-8",
        )

        monkeypatch.chdir(temp_config)
        from src.config.settings import Settings
        Settings._instance = None
        Settings._config_path = None

        from src.main import BlackboxEngine
        with patch.object(BlackboxEngine, '_init_ai_layer', lambda self: None):
            engine = BlackboxEngine(config_path=config_file)
        with engine._db._cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}

        expected_tables = {"sessions", "text_segments", "clipboard_records",
                          "window_events", "daily_reports", "period_reports"}
        assert expected_tables.issubset(tables), f"缺少表: {expected_tables - tables}"

        engine.stop()
        engine._db.close()
        Settings._instance = None
        Settings._config_path = None


# ==================== 测试：键盘事件 → 文本片段 → 数据库 ====================

class TestKeyboardToDatabase:
    """键盘事件 → InputBuffer → SessionManager → Database 集成测试"""

    def test_keyboard_event_to_text_segment(self, input_buffer, captured_segments):
        """测试键盘事件经 InputBuffer 处理后产生文本片段"""
        # 模拟输入 "hello"
        for ch in "hello":
            event = KeyEvent(
                event_type=KeyEventType.PRESS,
                key=ch,
                char=ch,
            )
            input_buffer.process_event(event)

        # 模拟 Enter 提交
        enter_event = KeyEvent(
            event_type=KeyEventType.PRESS,
            key=keyboard.Key.enter,
            char=None,
        )
        input_buffer.process_event(enter_event)

        assert len(captured_segments) == 1
        assert captured_segments[0][0] == "hello"
        assert captured_segments[0][1] == "keyboard"

    def test_ime_composition_to_text_segment(self, input_buffer, captured_segments):
        """测试 IME 组合文本经 InputBuffer 处理后产生文本片段"""
        # 模拟 IME 组合输入 "你好"
        ime_event = KeyEvent(
            event_type=KeyEventType.PRESS,
            key=None,
            char="你好",
            is_ime_composition=True,
        )
        input_buffer.process_event(ime_event)

        # 模拟 Enter 提交
        enter_event = KeyEvent(
            event_type=KeyEventType.PRESS,
            key=keyboard.Key.enter,
            char=None,
        )
        input_buffer.process_event(enter_event)

        assert len(captured_segments) == 1
        assert "你好" in captured_segments[0][0]

    def test_mixed_ime_and_english_input(self, input_buffer, captured_segments):
        """测试中英文混合输入"""
        # 先输入英文
        for ch in "hello ":
            event = KeyEvent(
                event_type=KeyEventType.PRESS,
                key=ch,
                char=ch,
            )
            input_buffer.process_event(event)

        # IME 组合输入中文
        ime_event = KeyEvent(
            event_type=KeyEventType.PRESS,
            key=None,
            char="世界",
            is_ime_composition=True,
        )
        input_buffer.process_event(ime_event)

        # 提交
        enter_event = KeyEvent(
            event_type=KeyEventType.PRESS,
            key=keyboard.Key.enter,
            char=None,
        )
        input_buffer.process_event(enter_event)

        assert len(captured_segments) == 1
        assert "hello" in captured_segments[0][0]
        assert "世界" in captured_segments[0][0]


# ==================== 测试：隐私过滤集成 ====================

class TestPrivacyFilterIntegration:
    """隐私过滤器与数据库的集成测试"""

    def test_filtered_content_marked(self, db, privacy_filter):
        """测试敏感内容被过滤标记"""
        # 创建会话
        session = SessionRecord(
            start_time="2026-07-06T10:00:00",
            end_time="2026-07-06T11:00:00",
            process_name="chrome.exe",
            window_title="Gmail",
            idle_seconds=0,
            active_seconds=3600,
            is_filtered=False,
        )

        # 敏感文本片段（使用隐私过滤器可识别的模式）
        sensitive_texts = [
            "sk-1234567890abcdef1234567890abcdef",  # API key
            "4111111111111111",  # 银行卡号
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0TH",  # JWT
        ]

        segments = []
        for text in sensitive_texts:
            _, was_filtered = privacy_filter.filter_text(text)
            segments.append(TextSegmentRecord(
                session_id=0,
                timestamp="2026-07-06T10:30:00",
                raw_text=text,
                source="keyboard",
                is_filtered=was_filtered,
                char_count=len(text),
            ))

        # 写入数据库
        db.insert_session_with_segments(session, segments)

        # 验证
        with db._cursor() as cur:
            cur.execute("SELECT raw_text, is_filtered FROM text_segments WHERE session_id = ?", (1,))
            rows = cur.fetchall()

        assert len(rows) == 3
        for row in rows:
            text, is_filtered = row
            assert is_filtered == 1, f"文本应被过滤: {text[:20]}..."

    def test_normal_content_not_filtered(self, db, privacy_filter):
        """测试普通内容不被过滤"""
        session = SessionRecord(
            start_time="2026-07-06T10:00:00",
            end_time="2026-07-06T11:00:00",
            process_name="code.exe",
            window_title="main.py",
            idle_seconds=0,
            active_seconds=3600,
            is_filtered=False,
        )

        normal_texts = ["hello world", "def main():", "print('hello')"]

        segments = []
        for text in normal_texts:
            _, was_filtered = privacy_filter.filter_text(text)
            segments.append(TextSegmentRecord(
                session_id=0,
                timestamp="2026-07-06T10:30:00",
                raw_text=text,
                source="keyboard",
                is_filtered=was_filtered,
                char_count=len(text),
            ))

        db.insert_session_with_segments(session, segments)

        with db._cursor() as cur:
            cur.execute("SELECT raw_text, is_filtered FROM text_segments WHERE session_id = ?", (1,))
            rows = cur.fetchall()

        assert len(rows) == 3
        for row in rows:
            text, is_filtered = row
            assert is_filtered == 0, f"文本不应被过滤: {text}"


# ==================== 测试：数据库加密 ====================

class TestDatabaseEncryption:
    """数据库加密功能测试"""

    def test_encryption_key_parameter_accepted(self, tmp_path):
        """测试 Database 接受 encryption_key 参数"""
        db_path = tmp_path / "enc_test.db"
        db = Database(db_path, encryption_key="test_key_123")
        assert db._encryption_key == "test_key_123"

    def test_fallback_to_sqlite_without_key(self, tmp_path):
        """测试无密钥时回退到普通 SQLite"""
        db_path = tmp_path / "plain_test.db"
        db = Database(db_path)
        db.initialize()

        assert db.is_connected
        # 验证可以正常写入
        session = SessionRecord(
            start_time="2026-07-06T10:00:00",
            end_time="2026-07-06T11:00:00",
            process_name="test.exe",
            window_title="test",
            idle_seconds=0,
            active_seconds=3600,
            is_filtered=False,
        )
        sid = db.insert_session(session)
        assert sid > 0
        db.close()

    def test_fallback_when_sqlcipher_unavailable(self, tmp_path):
        """测试 sqlcipher 不可用时优雅降级"""
        db_path = tmp_path / "fallback_test.db"
        # 即使传了 key，如果 sqlcipher 不可用，也应该回退
        db = Database(db_path, encryption_key="test_key")
        db.initialize()

        assert db.is_connected
        # 应该能用普通 sqlite3 打开（说明没有加密）
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute("SELECT count(*) FROM sessions")
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()

        db.close()


# ==================== 测试：原子性写入 ====================

class TestAtomicWrite:
    """原子性批量写入测试"""

    def test_insert_session_with_segments_atomic(self, db):
        """测试会话+片段的原子性写入"""
        session = SessionRecord(
            start_time="2026-07-06T10:00:00",
            end_time="2026-07-06T11:00:00",
            process_name="notepad.exe",
            window_title="test.txt",
            idle_seconds=10,
            active_seconds=3500,
            is_filtered=False,
        )

        segments = [
            TextSegmentRecord(
                session_id=0,
                timestamp="2026-07-06T10:15:00",
                raw_text=f"segment {i}",
                source="keyboard",
                is_filtered=False,
                char_count=10,
            )
            for i in range(5)
        ]

        sid = db.insert_session_with_segments(session, segments)
        assert sid > 0

        # 验证会话
        with db._cursor() as cur:
            cur.execute("SELECT process_name FROM sessions WHERE id = ?", (sid,))
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "notepad.exe"

        # 验证片段
        count = db.count_text_segments(sid)
        assert count == 5

    def test_count_text_segments(self, db):
        """测试文本片段计数方法"""
        session = SessionRecord(
            start_time="2026-07-06T10:00:00",
            end_time="2026-07-06T11:00:00",
            process_name="test.exe",
            window_title="test",
            idle_seconds=0,
            active_seconds=3600,
            is_filtered=False,
        )

        segments = [
            TextSegmentRecord(
                session_id=0,
                timestamp="2026-07-06T10:30:00",
                raw_text=f"text {i}",
                source="keyboard",
                is_filtered=False,
                char_count=6,
            )
            for i in range(3)
        ]

        sid = db.insert_session_with_segments(session, segments)

        # 验证计数
        assert db.count_text_segments(sid) == 3

        # 验证空会话计数为 0
        empty_session = SessionRecord(
            start_time="2026-07-06T12:00:00",
            end_time="2026-07-06T13:00:00",
            process_name="empty.exe",
            window_title="empty",
            idle_seconds=0,
            active_seconds=3600,
            is_filtered=False,
        )
        empty_sid = db.insert_session(empty_session)
        assert db.count_text_segments(empty_sid) == 0


# ==================== 测试：Web API 冒烟 ====================

class TestWebAPISmoke:
    """Web API 冒烟测试（不启动 pywebview）"""

    def test_api_methods_exist(self):
        """测试 BlackboxAPI 类有所有必要的方法"""
        from src.ui.web_api import BlackboxAPI
        api = BlackboxAPI.__new__(BlackboxAPI)

        # 验证生命周期方法
        assert hasattr(api, 'start_recording')
        assert hasattr(api, 'stop_recording')
        assert hasattr(api, 'pause_recording')
        assert hasattr(api, 'resume_recording')
        assert hasattr(api, 'shutdown')

        # 验证数据查询方法
        assert hasattr(api, 'get_status')
        assert hasattr(api, 'get_sessions')
        assert hasattr(api, 'get_session_detail')
        assert hasattr(api, 'get_app_stats')
        assert hasattr(api, 'search_text')

        # 验证报告方法
        assert hasattr(api, 'get_report')
        assert hasattr(api, 'get_reported_dates')
        assert hasattr(api, 'generate_report')

        # 验证配置方法
        assert hasattr(api, 'get_api_config')
        assert hasattr(api, 'save_api_config')
        assert hasattr(api, 'toggle_privacy')

        # 验证隐私同意方法
        assert hasattr(api, 'get_consent_status')
        assert hasattr(api, 'set_consent')


# ==================== 测试：品牌重定位 ====================

class TestBrandRepositioning:
    """验证品牌重定位：面向用户的文案不包含'键盘记录'"""

    def test_readme_no_keyboard_logger(self):
        """README 不包含'键盘记录'"""
        readme_path = Path(__file__).parent.parent / "README.md"
        if readme_path.exists():
            content = readme_path.read_text(encoding="utf-8")
            # 面向用户的描述不应包含"键盘记录"
            # 注意：CHANGELOG 中的历史记录可以保留
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("#") or "changelog" in lines[max(0, i-5):i+5]:
                    continue  # 跳过标题和 CHANGELOG 部分
                assert "键盘记录" not in line, f"README 第 {i+1} 行包含'键盘记录': {line[:50]}"

    def test_pyproject_description_updated(self):
        """pyproject.toml 描述已更新"""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text(encoding="utf-8")
            assert "活动追踪" in content or "AI 工作日志" in content, "pyproject.toml 描述未更新"

    def test_config_no_keyboard_logger(self):
        """config.yaml 注释不包含'键盘记录'"""
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        if config_path.exists():
            content = config_path.read_text(encoding="utf-8")
            assert "键盘记录" not in content, "config.yaml 仍包含'键盘记录'"
