"""导出功能测试：报告 HTML 渲染 + 待办 CSV。"""

from __future__ import annotations

import csv
import re

from src.ai.timedist_extractor import TimeDistExtractor, category_stats_to_timedist
from src.storage.data_exporter import DataExporter
from src.storage.models import TodoRecord
from src.storage.report_exporter import render_donut_svg, render_report_html


def _todo(title: str, **kw) -> TodoRecord:
    base = dict(title=title, created_at="2026-08-07T09:00:00", updated_at="2026-08-07T09:00:00")
    base.update(kw)
    return TodoRecord(**base)


# ==================== 报告 HTML ====================


class TestReportHtml:
    def test_renders_headings(self):
        h = render_report_html("# 大标题\n## 二级\n### 三级", "T")
        assert "<h1>大标题</h1>" in h  # h1 保留（Hero 用 div）
        assert "<h2" in h and "二级" in h  # h2 注入 emoji 图标 span
        assert "h2-ico" in h
        assert "<h3>三级</h3>" in h  # h3 不注入图标

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


# ==================== 时间分布环形图 ====================


class TestDonutSvg:
    def test_renders_slices_and_legend(self):
        data = [
            {"category": "开发编码", "minutes": 180, "percent": 45},
            {"category": "沟通会议", "minutes": 80, "percent": 20},
        ]
        svg = render_donut_svg(data)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert svg.count("<circle") == 2  # 两个扇形
        assert "开发编码" in svg  # 图例含类别名
        assert "45%" in svg

    def test_empty_data_returns_empty(self):
        assert render_donut_svg([]) == ""
        assert render_donut_svg(None) == ""

    def test_zero_percent_filtered(self):
        data = [
            {"category": "有值", "minutes": 100, "percent": 50},
            {"category": "零值", "minutes": 0, "percent": 0},
        ]
        svg = render_donut_svg(data)
        assert svg.count("<circle") == 1  # 零占比被过滤
        assert "零值" not in svg

    def test_center_total_duration(self):
        data = [{"category": "工作", "minutes": 90, "percent": 100}]
        svg = render_donut_svg(data)
        assert "1h30m" in svg  # 90 分钟 = 1h30m

    def test_category_escaped(self):
        data = [{"category": "<开发>", "minutes": 60, "percent": 100}]
        svg = render_donut_svg(data)
        assert "<开发>" not in svg  # 已转义，不被当标签
        assert "&lt;开发&gt;" in svg


# ==================== 时间分布提取解析 ====================


class TestTimedistParse:
    def test_plain_json_array(self):
        content = '[{"category":"开发","minutes":120,"percent":50},{"category":"沟通","minutes":120,"percent":50}]'
        result = TimeDistExtractor.parse_timedist_json(content)
        assert len(result) == 2
        assert result[0]["category"] == "开发"
        assert result[0]["minutes"] == 120

    def test_code_fence_wrapped(self):
        content = '```json\n[{"category":"编码","minutes":60,"percent":100}]\n```'
        result = TimeDistExtractor.parse_timedist_json(content)
        assert len(result) == 1
        assert result[0]["category"] == "编码"

    def test_extra_text_around(self):
        content = '好的，这是结果：\n[{"category":"A","minutes":30,"percent":30}]\n以上。'
        result = TimeDistExtractor.parse_timedist_json(content)
        assert len(result) == 1
        assert result[0]["category"] == "A"

    def test_empty_array(self):
        assert TimeDistExtractor.parse_timedist_json("[]") == []

    def test_garbage_returns_empty(self):
        assert TimeDistExtractor.parse_timedist_json("无时间分布信息") == []

    def test_missing_category_dropped(self):
        content = '[{"minutes":60,"percent":100},{"category":"B","minutes":30,"percent":0}]'
        result = TimeDistExtractor.parse_timedist_json(content)
        cats = [r["category"] for r in result]
        assert "B" in cats  # 缺 category 的被丢弃，B 保留

    def test_percent_normalized(self):
        # 总和 200，严重偏离 100，按比例缩放
        content = '[{"category":"A","minutes":100,"percent":100},{"category":"B","minutes":100,"percent":100}]'
        result = TimeDistExtractor.parse_timedist_json(content)
        total = sum(r["percent"] for r in result)
        assert 95 <= total <= 105  # 归一化后接近 100


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


# ==================== DB 分类统计 → 时间分布 ====================


class TestDbTimedist:
    def test_normal_conversion(self):
        items = [
            {"category": "开发工具", "active_seconds": 3600, "icon": "💻"},  # 60min
            {"category": "通讯社交", "active_seconds": 1800, "icon": "💬"},  # 30min
        ]
        result = category_stats_to_timedist(items)
        assert len(result) == 2
        assert result[0]["category"] == "开发工具"
        assert result[0]["minutes"] == 60
        assert result[0]["percent"] == 66.7  # 3600/5400
        total_pct = sum(r["percent"] for r in result)
        assert 99 <= total_pct <= 101  # 归一到 100

    def test_zero_active_filtered(self):
        items = [
            {"category": "有活动", "active_seconds": 600},
            {"category": "零活动", "active_seconds": 0},
        ]
        result = category_stats_to_timedist(items)
        assert len(result) == 1
        assert result[0]["category"] == "有活动"
        assert result[0]["percent"] == 100.0

    def test_empty_input(self):
        assert category_stats_to_timedist([]) == []
        assert category_stats_to_timedist(None) == []

    def test_single_category_100_percent(self):
        items = [{"category": "浏览器", "active_seconds": 7200}]
        result = category_stats_to_timedist(items)
        assert len(result) == 1
        assert result[0]["percent"] == 100.0
        assert result[0]["minutes"] == 120

    def test_short_activity_min_one_minute(self):
        # 30 秒活动 → round(0.5)=0，保底至少 1 分钟显示
        items = [{"category": "短暂", "active_seconds": 30}]
        result = category_stats_to_timedist(items)
        assert result[0]["minutes"] == 1
        assert result[0]["percent"] == 100.0

    def test_all_zero_returns_empty(self):
        items = [
            {"category": "A", "active_seconds": 0},
            {"category": "B", "active_seconds": 0},
        ]
        assert category_stats_to_timedist(items) == []
