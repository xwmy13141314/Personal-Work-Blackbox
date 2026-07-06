"""数据导出器测试"""
import pytest
import json
import csv
from pathlib import Path

from src.storage.database import Database
from src.storage.models import SessionRecord, TextSegmentRecord
from src.storage.data_exporter import DataExporter


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    # 插入测试数据
    session = SessionRecord(
        start_time="2026-07-06T10:00:00",
        end_time="2026-07-06T11:00:00",
        process_name="chrome.exe",
        window_title="Google",
        idle_seconds=0,
        active_seconds=3600,
        is_filtered=False,
    )
    seg = TextSegmentRecord(
        session_id=0,
        timestamp="2026-07-06T10:30:00",
        raw_text="hello world",
        source="keyboard",
        is_filtered=False,
        char_count=11,
    )
    db.insert_session_with_segments(session, [seg])
    yield db
    db.close()


def test_export_sessions_csv(db, tmp_path):
    exporter = DataExporter(db)
    path = exporter.export_sessions_csv(date="2026-07-06", output_path=tmp_path / "test.csv")
    assert path.exists()
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert len(rows) == 2  # header + 1 data
    assert "chrome.exe" in rows[1]


def test_export_sessions_json(db, tmp_path):
    exporter = DataExporter(db)
    path = exporter.export_sessions_json(date="2026-07-06", output_path=tmp_path / "test.json")
    assert path.exists()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["process_name"] == "chrome.exe"
    assert len(data["sessions"][0]["text_segments"]) == 1


def test_export_segments_csv(db, tmp_path):
    exporter = DataExporter(db)
    path = exporter.export_text_segments_csv(date="2026-07-06", output_path=tmp_path / "segs.csv")
    assert path.exists()
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert "hello world" in rows[1]
