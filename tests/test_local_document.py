from pathlib import Path

import pytest

from src.processor.local_document import LocalDocumentError, extract_local_document_text


def test_reads_text_and_removes_empty_lines(tmp_path: Path):
    path = tmp_path / "plan.md"
    path.write_text("# 本周计划\n\n- 完成导入功能\n", encoding="utf-8")

    assert extract_local_document_text(path) == "# 本周计划\n- 完成导入功能"


def test_reads_csv_rows(tmp_path: Path):
    path = tmp_path / "tasks.csv"
    path.write_text("任务,截止日期\n完成测试,2026-08-15\n", encoding="utf-8")

    assert extract_local_document_text(path) == "任务 | 截止日期\n完成测试 | 2026-08-15"


def test_rejects_unsupported_document(tmp_path: Path):
    path = tmp_path / "archive.zip"
    path.write_bytes(b"not used")

    with pytest.raises(LocalDocumentError, match="仅支持"):
        extract_local_document_text(path)
