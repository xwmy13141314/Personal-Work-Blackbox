"""导出功能测试：报告 HTML 渲染 + 待办 CSV。"""

from __future__ import annotations

import csv
import re

from src.storage.data_exporter import DataExporter
from src.storage.models import TodoRecord
from src.storage.report_exporter import render_report_html


def _todo(title: str, **kw) -> TodoRecord:
    base = dict(title=title, created_at="2026-08-07T09:00:00", updated_at="2026-08-07T09:00:00")
    base.update(kw)
    return TodoRecord(**base)


# ==================== 报告 HTML ====================


class TestReportHtml:
    def test_renders_headings(self):
        h = render_report_html("# 大标题\n## 二级\n### 三级", "T")
        assert "<h1>大标题</h1>" in h
        assert "<h2>二级</h2>" in h
        assert "<h3>三级</h3>" in h

    def test_renders_list(self):
        h = render_report_html("- 甲\n- 乙\n- 丙", "T")
        assert "<ul>" in h
        assert "<li>甲</li>" in h
        assert "<li>丙</li>" in h

    def test_renders_table(self):
        md = "| 产品 | 价格 |\n| --- | --- |\n| A | 10 |"
        h = render_report_html(md, "T")
        assert "<table>" in h
        assert "<th>产品</th>" in h
        assert "<td>10</td>" in h

    def test_renders_fenced_code(self):
        h = render_report_html("```\nprint('hi')\n```", "T")
        assert "<pre>" in h
        assert "<code>" in h

    def test_chinese_not_mangled(self):
        h = render_report_html("# 工作日报\n今天处理了待办跟进事项", "T")
        assert "工作日报" in h
        assert "待办跟进" in h

    def test_subtitle_in_meta(self):
        h = render_report_html("# x", "标题", "模型 glm · 生成于 2026-08-07")
        assert 'class="meta"' in h
        assert "模型 glm" in h

    def test_no_subtitle_no_meta(self):
        h = render_report_html("# x", "标题")
        assert 'class="meta"' not in h

    def test_title_escaped(self):
        h = render_report_html("# x", "标题<script>")
        assert "<title>标题&lt;script&gt;</title>" in h
        assert "<script>" not in h  # 未转义的脚本注入

    def test_empty_markdown(self):
        h = render_report_html("", "T")
        assert "<!doctype html>" in h  # 空内容也不崩

    def test_self_contained_no_external(self):
        h = render_report_html("# x", "T")
        assert not re.search(r'src="https?://', h)  # 无外链资源
        assert "<link" not in h  # 无外部样式表


# ==================== 待办 CSV ====================


class TestTodosCsv:
    def test_writes_bom_and_header(self, tmp_path):
        out = tmp_path / "t.csv"
        DataExporter(None).export_todos_csv([_todo("任务一")], output_path=out)
        raw = out.read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"  # utf-8-sig BOM，Excel 中文不乱码
        first_line = raw.decode("utf-8-sig").splitlines()[0]
        assert "标题" in first_line and "状态" in first_line

    def test_status_priority_source_mapping(self, tmp_path):
        out = tmp_path / "t.csv"
        todos = [_todo("A", status="in_progress", priority="urgent", source_type="daily_report")]
        DataExporter(None).export_todos_csv(todos, output_path=out)
        rows = list(csv.reader(out.open(encoding="utf-8-sig")))
        data = dict(zip(rows[0], rows[1]))
        assert data["状态"] == "进行中"
        assert data["优先级"] == "紧急"
        assert data["来源"] == "日报"

    def test_comma_in_title_escaped(self, tmp_path):
        out = tmp_path / "t.csv"
        DataExporter(None).export_todos_csv([_todo("任务一, 含逗号")], output_path=out)
        rows = list(csv.reader(out.open(encoding="utf-8-sig")))
        assert rows[1][0] == "任务一, 含逗号"  # 标题在第一列，逗号被正确引用

    def test_chinese_content(self, tmp_path):
        out = tmp_path / "t.csv"
        DataExporter(None).export_todos_csv([_todo("跟进骨传导耳机样品交付期")], output_path=out)
        assert "骨传导" in out.read_text(encoding="utf-8-sig")

    def test_row_count(self, tmp_path):
        out = tmp_path / "t.csv"
        todos = [_todo(f"任务{i}") for i in range(5)]
        DataExporter(None).export_todos_csv(todos, output_path=out)
        rows = list(csv.reader(out.open(encoding="utf-8-sig")))
        assert len(rows) == 6  # 1 表头 + 5 数据

    def test_draft_and_dates(self, tmp_path):
        out = tmp_path / "t.csv"
        todos = [_todo("草稿任务", is_draft=True, due_date="2026-08-09", source_ref="2026-08-07")]
        DataExporter(None).export_todos_csv(todos, output_path=out)
        rows = list(csv.reader(out.open(encoding="utf-8-sig")))
        data = dict(zip(rows[0], rows[1]))
        assert data["是否草稿"] == "是"
        assert data["截止日期"] == "2026-08-09"
        assert data["来源引用"] == "2026-08-07"
