import pytest

from src.processor.tencent_doc import TencentDocError, _html_to_text, extract_todo_table, validate_tencent_doc_url


def test_accepts_public_tencent_doc_url():
    url = "https://docs.qq.com/doc/DWk5zWm5yV3Zx"
    assert validate_tencent_doc_url(url) == url


@pytest.mark.parametrize("url", [
    "http://docs.qq.com/doc/D123",
    "https://evil.example/docs.qq.com/doc/D123",
    "https://docs.qq.com.evil.example/doc/D123",
    "https://docs.qq.com",
])
def test_rejects_non_public_tencent_doc_url(url):
    with pytest.raises(TencentDocError):
        validate_tencent_doc_url(url)


def test_html_text_excludes_scripts_and_styles():
    html = "<h1>项目计划</h1><p>完成发布</p><script>secret()</script><style>.x{}</style>"
    assert _html_to_text(html) == "项目计划\n完成发布"


def test_html_table_keeps_column_boundaries():
    html = "<table><tr><th>任务</th><th>状态</th></tr><tr><td>提交方案</td><td>进行中</td></tr></table>"
    assert _html_to_text(html) == "任务\t状态\n提交方案\t进行中"


def test_extracts_structured_todos_from_table_headers():
    text = "任务\t状态\t优先级\t截止日期\t备注\n提交方案\t进行中\t高\t2026/08/20\t发给客户\n归档旧资料\t已完成\t低\t\t"
    todos, diagnostics = extract_todo_table(text)
    assert todos == [{
        "title": "提交方案", "priority": "high", "due_date": "2026-08-20",
        "note": "状态：进行中\n备注：发给客户", "contact_person": "",
    }]
    assert diagnostics["recognized_columns"] == ["任务", "状态", "优先级", "截止日期", "备注"]
    assert diagnostics["skipped_completed"] == 1


def test_does_not_treat_non_table_text_as_structured_todos():
    todos, diagnostics = extract_todo_table("项目计划\n后续安排")
    assert todos == []
    assert diagnostics["recognized_columns"] == []
